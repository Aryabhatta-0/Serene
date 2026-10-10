"""The single-writer Memory Committer (issue #32).

Many components may *propose* a `MemoryPatch` (MEMORY_PATCH_PROPOSED by
AGENT / SYSTEM / PARENT). Exactly one component writes `memory_repo/`: this
one, acting as the MEMORY_COMMITTER actor, and only

1. after the deterministic Critic's verdict is in the ledger (MEMORY_PATCH_REVIEWED,
   recomputed by admission) and has passed;
2. after the repository audit shows no out-of-band writes;
3. through a two-phase commit: prepare the Git commit object, record
   MEMORY_PATCH_COMMITTED with its exact SHA (admission re-runs the Critic at the
   current head), then compare-and-set publish the branch.

Every commit carries its patch id, proposal event, review event, ledger head and
authorization digest as trailers, and yields a deterministic receipt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from serene.domain.base import KernelModel, Sha256Hex, ShortText, new_id
from serene.domain.canonical import canonical_digest, sha256_hex
from serene.domain.entities import MemoryOperation, MemoryPatch
from serene.domain.events import (
    DomainEvent,
    EventDraft,
    EventType,
    MemoryPatchCommitted,
    MemoryPatchRejected,
)
from serene.domain.values import ActorKind, ActorRef, SourceKind, SourceRef, VerificationStatus
from serene.ledger.service import AdmissionRejected, EventLedger
from serene.memory import critic
from serene.memory.store import COMMITTER_EMAIL, INIT_TRAILER, MemoryConflict, MemoryStore
from serene.ports.clock import Clock
from serene.ports.memory import CommitAuthorization
from serene.projections.state import KernelState


class MemoryIntegrityError(RuntimeError):
    """memory_repo does not match the ledger (out-of-band write). Fail closed."""

    def __init__(self, findings: list[str]) -> None:
        super().__init__(", ".join(findings))
        self.findings = tuple(findings)


class MemoryCommitReceipt(KernelModel):
    """Deterministic, reproducible record of one commit and the authority behind it."""

    patch_id: ShortText
    target_path: ShortText
    operation: MemoryOperation
    proposal_event_id: ShortText
    review_event_id: ShortText
    commit_event_id: ShortText
    commit_sha: ShortText
    parent_sha: ShortText
    tree_sha: ShortText
    diff_digest: Sha256Hex
    post_digest: Sha256Hex
    authorization_digest: Sha256Hex
    ledger_head: Sha256Hex

    @property
    def digest(self) -> str:
        return canonical_digest(self)


@dataclass(slots=True)
class CommitOutcome:
    patch_id: str
    committed: bool
    reason_codes: tuple[str, ...] = ()
    receipt: MemoryCommitReceipt | None = None
    events: list[DomainEvent] = field(default_factory=list)


def audit(store: MemoryStore, state: KernelState) -> list[str]:
    """Every commit in memory must be a ledger-recorded committer commit, and vice versa."""
    findings: list[str] = []
    if not store.worktree_clean():
        findings.append("DIRTY_WORKTREE")
    recorded = {sha: pid for pid, sha in state.memory_commits.items()}
    seen: set[str] = set()
    for record in store.history():
        seen.add(record.sha)
        if record.parent is None and INIT_TRAILER in record.trailers:
            continue
        patch_id = record.trailers.get("Serene-Patch-Id")
        if record.author_email != COMMITTER_EMAIL:
            findings.append(f"FOREIGN_AUTHOR:{record.sha[:12]}")
        if patch_id is None or recorded.get(record.sha) != patch_id:
            findings.append(f"UNAUTHORIZED_COMMIT:{record.sha[:12]}")
    for patch_id, sha in sorted(state.memory_commits.items()):
        if sha not in seen:
            findings.append(f"UNPUBLISHED_COMMIT:{patch_id}")
    return findings


class MemoryCommitter:
    def __init__(
        self,
        ledger: EventLedger,
        store: MemoryStore,
        clock: Clock,
        *,
        committer: ActorRef,
        policy: ActorRef,
        new_source_id: Callable[[], str] = lambda: new_id("src"),
    ) -> None:
        if committer.kind is not ActorKind.MEMORY_COMMITTER or policy.kind is not ActorKind.POLICY:
            raise ValueError("the committer acts as MEMORY_COMMITTER and reviews as POLICY")
        self._ledger = ledger
        self._store = store
        self._clock = clock
        self._committer = committer
        self._policy = policy
        self._new_source_id = new_source_id

    def _draft(
        self,
        state: KernelState,
        event_type: EventType,
        actor: ActorRef,
        payload: object,
        derived_from: tuple[str, ...],
    ) -> EventDraft:
        assert state.child_id is not None
        return EventDraft(
            event_type=event_type,
            child_id=state.child_id,
            source=SourceRef(kind=SourceKind.KERNEL, source_id=self._new_source_id()),
            actor=actor,
            occurred_at=self._clock.now(),
            derived_from=derived_from,
            verification_status=VerificationStatus.NOT_APPLICABLE,
            payload=payload,  # type: ignore[arg-type]
        )

    def _reject(
        self, state: KernelState, patch_id: str, reasons: tuple[str, ...], derived: tuple[str, ...]
    ) -> CommitOutcome:
        event = self._ledger.append_event(
            self._draft(
                state,
                EventType.MEMORY_PATCH_REJECTED,
                self._committer,
                MemoryPatchRejected(patch_id=patch_id, reason_codes=reasons[:64]),
                derived,
            )
        )
        return CommitOutcome(patch_id, committed=False, reason_codes=reasons, events=[event])

    def review(self, child_id: str, patch_id: str) -> DomainEvent:
        """Record the deterministic Critic verdict (POLICY). Admission recomputes it."""
        state = self._ledger.replay_events(child_id)
        patch: MemoryPatch = state.entities[patch_id].entity
        payload = critic.review_payload(patch, state, self._clock.now())
        return self._ledger.append_event(
            self._draft(
                state,
                EventType.MEMORY_PATCH_REVIEWED,
                self._policy,
                payload,
                (state.entities[patch_id].introduced_by,),
            )
        )

    def process(self, child_id: str, patch_id: str) -> CommitOutcome:
        state = self._ledger.replay_events(child_id)
        if state.memory_patches.get(patch_id) != "PROPOSED":
            raise ValueError(f"patch {patch_id} is not awaiting a decision")
        findings = audit(self._store, state)
        if findings:
            raise MemoryIntegrityError(findings)  # never build on tampered memory

        events: list[DomainEvent] = []
        if patch_id not in state.memory_reviews:
            events.append(self.review(child_id, patch_id))
            state = self._ledger.replay_events(child_id)
        review = state.memory_reviews[patch_id]
        proposal_event = state.entities[patch_id].introduced_by
        lineage = (proposal_event, review.event_id)
        if not review.passed:
            outcome = self._reject(state, patch_id, review.reason_codes, lineage)
            outcome.events[:0] = events
            return outcome

        patch: MemoryPatch = state.entities[patch_id].entity
        authorization = CommitAuthorization(
            patch_id=patch_id, proposal_event_id=proposal_event, ledger_head=state.last_event_hash
        )
        authorization_digest = canonical_digest(authorization)
        try:
            prepared = self._store.prepare_commit(
                patch,
                authorization,
                trailers={
                    "Serene-Patch-Id": patch_id,
                    "Serene-Proposal-Event": proposal_event,
                    "Serene-Review-Event": review.event_id,
                    "Serene-Ledger-Head": state.last_event_hash,
                    "Serene-Authorization": authorization_digest,
                },
                committed_at=self._clock.now(),
            )
        except MemoryConflict as conflict:
            outcome = self._reject(state, patch_id, (conflict.reason_code,), lineage)
            outcome.events[:0] = events
            return outcome

        try:
            committed = self._ledger.append_event(
                self._draft(
                    state,
                    EventType.MEMORY_PATCH_COMMITTED,
                    self._committer,
                    MemoryPatchCommitted(patch_id=patch_id, commit_sha=prepared.commit_sha),
                    lineage,
                )
            )
        except AdmissionRejected as exc:
            # The prepared object is never published: memory is unchanged.
            state = self._ledger.replay_events(child_id)
            outcome = self._reject(state, patch_id, exc.reason_codes, lineage)
            outcome.events[:0] = events
            return outcome
        self._store.publish(prepared)
        receipt = MemoryCommitReceipt(
            patch_id=patch_id,
            target_path=patch.target_path,
            operation=patch.operation,
            proposal_event_id=proposal_event,
            review_event_id=review.event_id,
            commit_event_id=committed.event_id,
            commit_sha=prepared.commit_sha,
            parent_sha=prepared.parent_sha,
            tree_sha=prepared.tree_sha,
            diff_digest=sha256_hex(patch.diff.encode("utf-8")),
            post_digest=prepared.post_digest,
            authorization_digest=authorization_digest,
            ledger_head=state.last_event_hash,
        )
        return CommitOutcome(patch_id, True, ("COMMITTED",), receipt, [*events, committed])
