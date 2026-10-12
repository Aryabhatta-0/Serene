"""Who is calling the web endpoint: a verified Supabase session (issue #84).

The kernel does not trust the web app's word for who is signed in. It asks
Supabase Auth (`GET /auth/v1/user` with the caller's access token), which
checks the token's signature and expiry and that the session still exists,
and takes only the opaque user id from the answer. Any failure means "not
authenticated"; nothing about the token or the user is logged.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Final, Protocol, runtime_checkable

_UUID: Final = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_TOKEN: Final = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
MAX_TOKEN_CHARS: Final = 4096


@runtime_checkable
class SessionVerifier(Protocol):
    def verify(self, access_token: str) -> str | None:
        """The opaque user id of a valid, current session, or None."""
        ...


class SupabaseSessionVerifier:
    def __init__(self, url: str, anon_key: str, *, timeout: float = 5.0) -> None:
        if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise ValueError("Supabase URL must be https (or local http)")
        self._endpoint = url.rstrip("/") + "/auth/v1/user"
        self._anon_key = anon_key
        self._timeout = timeout

    def verify(self, access_token: str) -> str | None:
        if len(access_token) > MAX_TOKEN_CHARS or not _TOKEN.match(access_token):
            return None
        request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            self._endpoint,
            headers={"Authorization": f"Bearer {access_token}", "apikey": self._anon_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                if response.status != 200:
                    return None
                user = json.loads(response.read(65536))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None
        if not isinstance(user, dict) or user.get("aud") != "authenticated":
            return None
        user_id = user.get("id")
        return user_id if isinstance(user_id, str) and _UUID.match(user_id) else None
