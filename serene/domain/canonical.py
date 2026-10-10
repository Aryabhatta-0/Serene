"""Deterministic canonical JSON used for hashing (issue #4).

Rules (hash_version 1):
- UTF-8, no insignificant whitespace, object keys sorted by code point.
- Allowed scalars: str, int (|n| <= 2**53), bool, None. Floats are rejected:
  their textual form is not stable across languages and Postgres jsonb.
- Datetimes must be timezone-aware and are rendered as UTC
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`.
- Enums render as their value; Pydantic models are dumped in Python mode and
  then normalized by these same rules (so nested datetimes use the format above).
- NUL characters are rejected (Postgres jsonb cannot store them).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

_MAX_SAFE_INT = 2**53


class CanonicalizationError(ValueError):
    pass


def format_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalizationError("naive datetime cannot be canonicalized")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _normalize(value: Any, path: str) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(), path)
    if isinstance(value, Enum):
        return _normalize(value.value, path)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INT:
            raise CanonicalizationError(f"integer out of safe range at {path}")
        return value
    if isinstance(value, float):
        raise CanonicalizationError(f"floats are not canonicalizable (at {path})")
    if isinstance(value, str):
        if "\x00" in value:
            raise CanonicalizationError(f"NUL character at {path}")
        return value
    if isinstance(value, datetime):
        return format_timestamp(value)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"non-string key at {path}")
            out[key] = _normalize(item, f"{path}.{key}")
        return out
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [_normalize(item, f"{path}[{i}]") for i, item in enumerate(value)]
    raise CanonicalizationError(f"unsupported type {type(value).__name__} at {path}")


def to_canonical_data(value: Any) -> Any:
    """Return the JSON-compatible structure that `canonical_json` would serialize."""
    return _normalize(value, "$")


def canonical_json(value: Any) -> bytes:
    normalized = _normalize(value, "$")
    text = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_digest(value: Any) -> str:
    return sha256_hex(canonical_json(value))
