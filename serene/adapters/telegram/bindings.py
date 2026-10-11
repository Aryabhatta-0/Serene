"""Telegram identity -> Serene principal bindings.

A Telegram user id is only meaningful to Serene if an operator bound it to one
child and one opaque actor (PARENT or CAREGIVER). Unbound senders are ignored.
Telegram ids never enter the ledger; only the bound `act_` id does.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, Self, runtime_checkable

from pydantic import model_validator

from serene.domain.base import ChildId, KernelModel
from serene.domain.values import HUMAN_ACTORS, ActorRef


class TelegramBinding(KernelModel):
    telegram_user_id: int
    child_id: ChildId
    actor: ActorRef

    @model_validator(mode="after")
    def _human_principal(self) -> Self:
        if self.actor.kind not in HUMAN_ACTORS:
            raise ValueError("only PARENT or CAREGIVER actors can be bound to Telegram")
        return self


@runtime_checkable
class BindingRegistry(Protocol):
    def lookup(self, telegram_user_id: int) -> TelegramBinding | None: ...

    def for_actor(self, actor_id: str) -> TelegramBinding | None: ...

    def for_child(self, child_id: str) -> tuple[TelegramBinding, ...]: ...


@dataclass(frozen=True, slots=True)
class StaticBindingRegistry:
    bindings: tuple[TelegramBinding, ...]

    def __post_init__(self) -> None:
        ids = [b.telegram_user_id for b in self.bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("a Telegram user may be bound to only one principal")

    @classmethod
    def of(cls, bindings: Iterable[TelegramBinding]) -> StaticBindingRegistry:
        return cls(tuple(bindings))

    def lookup(self, telegram_user_id: int) -> TelegramBinding | None:
        return next((b for b in self.bindings if b.telegram_user_id == telegram_user_id), None)

    def for_actor(self, actor_id: str) -> TelegramBinding | None:
        return next((b for b in self.bindings if b.actor.actor_id == actor_id), None)

    def for_child(self, child_id: str) -> tuple[TelegramBinding, ...]:
        return tuple(b for b in self.bindings if b.child_id == child_id)


def bindings_from_env() -> StaticBindingRegistry:
    """`SERENE_TELEGRAM_BINDINGS`: JSON list of {telegram_user_id, child_id, actor}."""
    raw = os.environ.get("SERENE_TELEGRAM_BINDINGS", "")
    if not raw.strip():
        return StaticBindingRegistry(())
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("SERENE_TELEGRAM_BINDINGS must be a JSON list")
    return StaticBindingRegistry.of(
        TelegramBinding.model_validate_json(json.dumps(item)) for item in items
    )
