"""The Markdown memory document format (memory_repo/SCHEMA.md).

The canonical grammar (strict `parse`, canonical `render`) is part of the
authority contract the ledger's admission re-checks, so it lives in
`serene.policies.memory_format`; this module re-exports it for the memory
feature layer.
"""

from __future__ import annotations

from serene.policies.memory_format import (
    DIRECTORY_KIND,
    FENCE,
    MEMORY_FORMAT,
    BodyText,
    MemoryDoc,
    MemoryFormatError,
    MemoryFrontMatter,
    MemoryKind,
    directory_of,
    parse,
    render,
)

__all__ = [
    "DIRECTORY_KIND",
    "FENCE",
    "MEMORY_FORMAT",
    "BodyText",
    "MemoryDoc",
    "MemoryFormatError",
    "MemoryFrontMatter",
    "MemoryKind",
    "directory_of",
    "parse",
    "render",
]
