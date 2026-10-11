"""The subset of the Telegram Bot API `Update` object Serene consumes.

Telegram sends many more fields; unknown ones are ignored (this is transport,
not a kernel contract) but every field Serene reads is strictly typed.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

_CallbackId = Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z_\-]{1,64}$")]


class _Tg(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True, populate_by_name=True)


class TgUser(_Tg):
    id: int
    is_bot: bool = False


class TgChat(_Tg):
    id: int
    type: str


class TgMessage(_Tg):
    message_id: int
    date: int
    chat: TgChat
    from_: TgUser | None = Field(default=None, alias="from")
    text: str | None = Field(default=None, max_length=4096)


class TgCallbackQuery(_Tg):
    id: _CallbackId
    from_: TgUser = Field(alias="from")
    message: TgMessage | None = None
    data: str | None = Field(default=None, max_length=64)


class TgUpdate(_Tg):
    update_id: int = Field(ge=0)
    message: TgMessage | None = None
    callback_query: TgCallbackQuery | None = None
