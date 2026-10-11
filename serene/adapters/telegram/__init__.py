"""Telegram channel adapter (branch A): authenticated ingress and exact prompts.

Hermes owns the bot transport; this adapter is the Serene-side boundary that
verifies the webhook secret, maps bound Telegram users to opaque principals and
mints `ChannelReceipt`s. It never treats message text as authorization.
"""

from serene.adapters.telegram.bindings import (
    BindingRegistry,
    StaticBindingRegistry,
    TelegramBinding,
    bindings_from_env,
)
from serene.adapters.telegram.channel import ChannelResult, TelegramChannel
from serene.adapters.telegram.prompts import (
    BotApiOutbox,
    InMemoryPromptRegistry,
    PendingPrompt,
    PromptKind,
    RecordingOutbox,
    TelegramOutbox,
    TelegramPrompter,
)

__all__ = [
    "BindingRegistry",
    "BotApiOutbox",
    "ChannelResult",
    "InMemoryPromptRegistry",
    "PendingPrompt",
    "PromptKind",
    "RecordingOutbox",
    "StaticBindingRegistry",
    "TelegramBinding",
    "TelegramChannel",
    "TelegramOutbox",
    "TelegramPrompter",
    "bindings_from_env",
]
