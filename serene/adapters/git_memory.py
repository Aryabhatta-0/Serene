"""Git + Markdown `MemoryRepository` adapter (issues #28, #32).

The repository is a plain Git repo of Markdown files. Reads come from the
committed HEAD tree, never from the working tree, so an out-of-band edit is
never served as memory (and is reported by `serene.memory.committer.audit`).
Writes are two-phase plumbing (hash-object / write-tree / commit-tree, then a
compare-and-set update-ref) with a fixed committer identity and the Clock's
timestamp, so identical inputs produce identical commit SHAs on every machine.
No embeddings, no vector index: search is a deterministic substring scan.

Git runs isolated from user/system configuration (no global hooks, signing,
templates or autocrlf), so behaviour does not depend on the host.
"""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from serene.domain.canonical import sha256_hex
from serene.domain.entities import MemoryOperation, MemoryPatch
from serene.memory.diff import parse_full_diff
from serene.memory.store import (
    COMMITTER_EMAIL,
    COMMITTER_NAME,
    INIT_TRAILER,
    CommitRecord,
    MemoryConflict,
    PreparedCommit,
    StaleHead,
)
from serene.ports.clock import Clock
from serene.ports.memory import CommitAuthorization, CommitReceipt, MemoryDocument

BRANCH: Final = "refs/heads/main"
EMPTY_TREE: Final = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_ZERO: Final = "0" * 40
_TRAILER = re.compile(r"^([A-Z][A-Za-z-]+): (.+)$")


class GitError(RuntimeError):
    pass


def _git_date(when: datetime) -> str:
    return f"{int(when.astimezone(UTC).timestamp())} +0000"


class GitMemoryRepository:
    """Implements `serene.ports.memory.MemoryRepository` and `serene.memory.store.MemoryStore`."""

    def __init__(self, root: str | Path, *, clock: Clock | None = None) -> None:
        self._root = Path(root)
        self._clock = clock
        if not (self._root / ".git").is_dir():
            raise GitError("NOT_A_MEMORY_REPOSITORY")

    # ------------------------------------------------------------------ plumbing
    @staticmethod
    def _env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
            }
        )
        if extra:
            env.update(extra)
        return env

    @classmethod
    def _run(
        cls,
        cwd: Path,
        *args: str,
        stdin: bytes | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(  # noqa: S603 - fixed executable, no shell
            ["git", *args],  # noqa: S607
            cwd=cwd,
            input=stdin,
            capture_output=True,
            env=cls._env(env),
            check=False,
        )
        if check and result.returncode != 0:
            raise GitError(f"GIT_COMMAND_FAILED: exit={result.returncode}")
        return result

    def _git(self, *args: str, **kwargs: object) -> bytes:
        return self._run(self._root, *args, **kwargs).stdout  # type: ignore[arg-type]

    @classmethod
    def _ident(cls, when: datetime) -> dict[str, str]:
        date = _git_date(when)
        return {
            "GIT_AUTHOR_NAME": COMMITTER_NAME,
            "GIT_AUTHOR_EMAIL": COMMITTER_EMAIL,
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_NAME": COMMITTER_NAME,
            "GIT_COMMITTER_EMAIL": COMMITTER_EMAIL,
            "GIT_COMMITTER_DATE": date,
        }

    @classmethod
    def init(
        cls, root: str | Path, *, created_at: datetime, clock: Clock | None = None
    ) -> GitMemoryRepository:
        """Create (or open) a memory repo whose root commit is deterministic for `created_at`."""
        path = Path(root)
        if (path / ".git").is_dir():
            return cls(path, clock=clock)
        path.mkdir(parents=True, exist_ok=True)
        cls._run(path, "init", "-q", "-b", "main", ".")
        for key, value in (
            ("core.autocrlf", "false"),
            ("core.safecrlf", "false"),
            ("commit.gpgsign", "false"),
            ("core.hooksPath", ".git/serene-no-hooks"),
        ):
            cls._run(path, "config", key, value)
        (path / ".git" / "info").mkdir(exist_ok=True)
        (path / ".git" / "info" / "attributes").write_bytes(b"* -text\n")
        message = f"memory: initialise Serene memory repo\n\n{INIT_TRAILER}: memory-repo/1\n"
        sha = (
            cls._run(
                path,
                "commit-tree",
                EMPTY_TREE,
                "-F",
                "-",
                stdin=message.encode(),
                env=cls._ident(created_at),
            )
            .stdout.decode()
            .strip()
        )
        cls._run(path, "update-ref", BRANCH, sha, _ZERO)
        return cls(path, clock=clock)

    # ------------------------------------------------------------------ reads (HEAD tree only)
    def head(self) -> str:
        return self._git("rev-parse", "--verify", BRANCH).decode().strip()

    def _exists(self, path: str) -> bool:
        return bool(self._git("ls-tree", "--name-only", BRANCH, "--", path).strip())

    def revision_of(self, path: str) -> str | None:
        if not self._exists(path):
            return None
        return self._git("log", "-1", "--format=%H", BRANCH, "--", path).decode().strip()

    def read(self, path: str) -> MemoryDocument | None:
        if not self._exists(path):
            return None
        content = self._git("cat-file", "blob", f"{BRANCH}:{path}").decode("utf-8")
        return MemoryDocument(
            path=path,
            revision=self.revision_of(path) or self.head(),
            content=content,
            content_digest=sha256_hex(content.encode("utf-8")),
        )

    def list_paths(self, prefix: str) -> Sequence[str]:
        names = self._git("ls-tree", "-r", "--name-only", BRANCH).decode().splitlines()
        return tuple(sorted(n for n in names if n.startswith(prefix)))

    def search(self, needle: str, prefix: str = "") -> Sequence[str]:
        """Deterministic, case-insensitive substring search over committed documents."""
        lowered = needle.lower()
        hits = []
        for path in self.list_paths(prefix):
            doc = self.read(path)
            if doc is not None and lowered in doc.content.lower():
                hits.append(path)
        return tuple(hits)

    # ------------------------------------------------------------------ two-phase write
    def prepare_commit(
        self,
        patch: MemoryPatch,
        authorization: CommitAuthorization,
        *,
        trailers: Mapping[str, str],
        committed_at: datetime,
    ) -> PreparedCommit:
        if authorization.patch_id != patch.patch_id:
            raise ValueError("authorization does not cover this patch")
        parsed = parse_full_diff(patch.diff)
        if parsed.path != patch.target_path:
            raise MemoryConflict("DIFF_PATH_MISMATCH")
        head = self.head()
        current = self.read(patch.target_path)
        if patch.operation is MemoryOperation.CREATE:
            if current is not None:
                raise MemoryConflict("TARGET_ALREADY_EXISTS")
        else:
            if current is None:
                raise MemoryConflict("TARGET_MISSING")
            if current.revision != patch.base_revision:
                raise MemoryConflict("STALE_BASE_REVISION")
            if current.content != parsed.pre:
                raise MemoryConflict("PRE_IMAGE_MISMATCH")

        post = parsed.post.encode("utf-8")
        blob = self._git("hash-object", "-w", "--stdin", stdin=post).decode().strip()
        index = self._root / ".git" / f"serene-index-{uuid.uuid4().hex}"
        try:
            idx = {"GIT_INDEX_FILE": str(index)}
            self._git("read-tree", head, env=idx)
            self._git(
                "update-index",
                "--add",
                "--cacheinfo",
                f"100644,{blob},{patch.target_path}",
                env=idx,
            )
            tree = self._git("write-tree", env=idx).decode().strip()
        finally:
            index.unlink(missing_ok=True)
        lines = [f"memory: {patch.operation.value} {patch.target_path}", ""]
        lines += [f"{key}: {value}" for key, value in trailers.items()]
        commit = (
            self._git(
                "commit-tree",
                tree,
                "-p",
                head,
                "-F",
                "-",
                stdin=("\n".join(lines) + "\n").encode(),
                env=self._ident(committed_at),
            )
            .decode()
            .strip()
        )
        return PreparedCommit(
            commit_sha=commit,
            parent_sha=head,
            tree_sha=tree,
            path=patch.target_path,
            post_digest=sha256_hex(post),
        )

    def publish(self, prepared: PreparedCommit) -> None:
        moved = self._run(
            self._root, "update-ref", BRANCH, prepared.commit_sha, prepared.parent_sha, check=False
        )
        if moved.returncode != 0:
            raise StaleHead(f"memory head moved; {prepared.commit_sha[:12]} not published")
        # Bring index + working tree to the new head for human readers; never overwrites
        # local edits (two-tree merge refuses), which the audit then reports.
        self._run(
            self._root,
            "read-tree",
            "-m",
            "-u",
            prepared.parent_sha,
            prepared.commit_sha,
            check=False,
        )

    def commit(self, patch: MemoryPatch, authorization: CommitAuthorization) -> CommitReceipt:
        """Port method. Only the Memory Committer may call it (enforced by tests and audit)."""
        prepared = self.prepare_commit(
            patch,
            authorization,
            trailers={
                "Serene-Patch-Id": patch.patch_id,
                "Serene-Proposal-Event": authorization.proposal_event_id,
                "Serene-Ledger-Head": authorization.ledger_head,
            },
            committed_at=self._clock.now() if self._clock else datetime.now(UTC),
        )
        self.publish(prepared)
        return CommitReceipt(patch_id=patch.patch_id, commit_sha=prepared.commit_sha)

    # ------------------------------------------------------------------ audit support
    def history(self) -> Sequence[CommitRecord]:
        raw = self._git("log", "--format=%H%x1f%P%x1f%ae%x1f%B%x1e", BRANCH).decode("utf-8")
        records = []
        for entry in raw.split("\x1e"):
            entry = entry.strip("\n")
            if not entry:
                continue
            sha, parent, email, body = entry.split("\x1f", 3)
            trailers = {}
            for line in body.splitlines():
                match = _TRAILER.match(line.strip())
                if match:
                    trailers[match.group(1)] = match.group(2)
            records.append(CommitRecord(sha, parent or None, email, trailers))
        return tuple(records)

    def worktree_clean(self) -> bool:
        status = self._git("status", "--porcelain=v1", "--untracked-files=all")
        return status.strip() == b""

    def has_commit(self, sha: str) -> bool:
        return (
            self._run(self._root, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode
            == 0
        )
