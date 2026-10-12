"""Which opaque PARENT actor a verified web user is, for one child (issue #84).

Two things must agree before a web decision can be attempted:

1. guardianship, from the #8 registry (`serene.child_guardians`, the same rows
   RLS uses to decide what the web app may read), and
2. an operator binding of that Supabase user, for that child, to the opaque
   `act_` PARENT actor approval requests are addressed to
   (`SERENE_WEB_BINDINGS`, like `SERENE_TELEGRAM_BINDINGS`).

Supabase user ids never reach the ledger; only the bound `act_` id does.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, Self, runtime_checkable
from uuid import UUID

from pydantic import model_validator

from serene.domain.base import ChildId, KernelModel
from serene.domain.values import ActorKind, ActorRef


class WebBinding(KernelModel):
    user_id: UUID
    child_id: ChildId
    actor: ActorRef

    @model_validator(mode="after")
    def _parent_only(self) -> Self:
        if self.actor.kind is not ActorKind.PARENT:
            raise ValueError("only PARENT actors can decide approvals from the web")
        return self


@dataclass(frozen=True, slots=True)
class WebBindings:
    bindings: tuple[WebBinding, ...]

    def __post_init__(self) -> None:
        keys = [(b.user_id, b.child_id) for b in self.bindings]
        if len(keys) != len(set(keys)):
            raise ValueError("a web user may be bound once per child")

    @classmethod
    def of(cls, bindings: Iterable[WebBinding]) -> WebBindings:
        return cls(tuple(bindings))

    def actor_for(self, user_id: str, child_id: str) -> ActorRef | None:
        return next(
            (
                b.actor
                for b in self.bindings
                if str(b.user_id) == user_id and b.child_id == child_id
            ),
            None,
        )


def web_bindings_from_env() -> WebBindings:
    """`SERENE_WEB_BINDINGS`: JSON list of {user_id, child_id, actor}."""
    raw = os.environ.get("SERENE_WEB_BINDINGS", "")
    if not raw.strip():
        return WebBindings(())
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("SERENE_WEB_BINDINGS must be a JSON list")
    return WebBindings.of(WebBinding.model_validate_json(json.dumps(i)) for i in items)


@runtime_checkable
class GuardianRegistry(Protocol):
    def is_parent(self, user_id: str, child_id: str) -> bool: ...


class PostgresGuardianRegistry:
    """`serene.child_guardians`, read with the service-role connection."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def is_parent(self, user_id: str, child_id: str) -> bool:
        import psycopg

        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "select 1 from serene.child_guardians "
                "where user_id = %s and child_id = %s and role = 'PARENT'",
                (user_id, child_id),
            ).fetchone()
        return row is not None


@dataclass(frozen=True, slots=True)
class WebPrincipals:
    guardians: GuardianRegistry
    bindings: WebBindings

    def parent(self, user_id: str, child_id: str) -> ActorRef | None:
        """The bound PARENT actor, only if the registry also says this user is the parent."""
        actor = self.bindings.actor_for(user_id, child_id)
        if actor is None or not self.guardians.is_parent(user_id, child_id):
            return None
        return actor
