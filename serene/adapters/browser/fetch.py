"""Independent page fetcher for the verifier (issue #16).

A deliberately small https GET used only to re-read a page the browser claims
to have captured. It is the verifier's own observation, not the browser's:

- https on port 443 only, host on the request's allowlist, no credentials in URL;
- the host is resolved once and every address must be globally routable (no
  loopback/private/link-local/metadata); the socket connects to that vetted
  address with SNI + certificate verification for the original host, so DNS
  rebinding between check and connect cannot redirect it;
- no redirects (a 3xx is treated as unreachable), bounded bytes and time;
- the response is reduced to visible text; nothing in it is executed.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urlsplit

from serene.evidence.verifier import FetchedPage
from serene.policies.external_evidence import domain_allowed, host_of

MAX_BYTES: Final = 2_000_000
TIMEOUT_S: Final = 10.0
Resolver = Callable[[str], list[str]]


def _resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS to a pre-vetted IP while verifying the certificate for `host`."""

    def __init__(self, host: str, address: str, *, timeout: float) -> None:
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, 443), timeout=self.timeout)
        context = ssl.create_default_context()
        self.sock = context.wrap_socket(raw, server_hostname=self.host)


class _Text(HTMLParser):
    _SKIP: Final = frozenset({"script", "style", "noscript", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skipping += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skipping:
            self._skipping -= 1

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def visible_text(body: str) -> str:
    parser = _Text()
    parser.feed(body)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


class SafeHttpsFetcher:
    def __init__(
        self,
        *,
        resolver: Resolver = _resolve,
        timeout_s: float = TIMEOUT_S,
        max_bytes: int = MAX_BYTES,
        connection_factory: Callable[[str, str], http.client.HTTPSConnection] | None = None,
    ) -> None:
        self._resolve = resolver
        self._timeout = timeout_s
        self._max_bytes = max_bytes
        self._connect = connection_factory or (
            lambda host, address: _PinnedHTTPSConnection(host, address, timeout=self._timeout)
        )

    def vetted_address(self, url: str, allowed_domains: tuple[str, ...]) -> str | None:
        host = host_of(url)
        if not domain_allowed(host, allowed_domains):
            return None
        assert host is not None
        try:
            addresses = self._resolve(host)
        except OSError:
            return None
        if not addresses:
            return None
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address.split("%", 1)[0])
            except ValueError:
                return None
            if not ip.is_global or ip.is_multicast:
                return None
        return addresses[0]

    def fetch(self, url: str, allowed_domains: tuple[str, ...]) -> FetchedPage | None:
        address = self.vetted_address(url, allowed_domains)
        if address is None:
            return None
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        host = host_of(url)
        assert host is not None
        conn = self._connect(host, address)
        try:
            conn.request("GET", path, headers={"Accept": "text/html,text/plain", "Host": host})
            response = conn.getresponse()
            if response.status != 200:
                return None
            body = response.read(self._max_bytes + 1)
        except (OSError, http.client.HTTPException, ssl.SSLError):
            return None
        finally:
            conn.close()
        if len(body) > self._max_bytes:
            return None
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            text = body.decode(charset, errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        return FetchedPage(url=url, text=visible_text(text))
