"""The committed neatlogs upload path, against an offline fake ingest server (#52).

The fake server mirrors what the real edge did on 2026-10-10: bodies over 8 KiB get
an HTML 403. Nothing here touches the network beyond 127.0.0.1.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any

import pytest

from serene.adapters.neatlogs_sink import (
    MAX_BODY_BYTES,
    NeatlogsSink,
    build_sink,
    build_telemetry,
    endpoint_allowed,
)
from serene.ledger import EventLedger
from serene.observability import SafeTelemetry
from serene.testing import SyntheticFamily

EDGE_LIMIT = 8 * 1024
KEY = "test-not-a-real-key"


@dataclass
class Ingest:
    """A fake /v1/trace: records accepted bodies, refuses large ones like the edge."""

    status: int = 200
    redirect_to: str = ""
    bodies: list[dict[str, Any]] = field(default_factory=list)
    keys: list[str | None] = field(default_factory=list)
    url: str = ""


@pytest.fixture
def ingest() -> Iterator[Ingest]:
    yield from _serve(Ingest())


def _serve(state: Ingest) -> Iterator[Ingest]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            state.keys.append(self.headers.get("x-api-key"))
            if state.redirect_to:
                self.send_response(302)
                self.send_header("Location", state.redirect_to)
                self.end_headers()
                return
            if len(body) > EDGE_LIMIT:
                self.send_response(403)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>403 Forbidden</html>")
                return
            state.bodies.append(json.loads(body))
            self.send_response(state.status)
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_address[1]}/v1/trace"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def _sink(url: str, **kwargs: Any) -> NeatlogsSink:
    return NeatlogsSink("serene-test", api_key=KEY, endpoint=url, **{"timeout_s": 5, **kwargs})


def _records(n: int) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "runtime.call",
            {
                "task_id": f"task-{i}",
                "event_id": f"evt_{i:032x}",
                "status": "OK" if i % 7 else "FAILED",
                "input_tokens": 1200 + i,
                "output_tokens": 30,
                "duration_ms": 900,
                "tool": "none",
            },
        )
        for i in range(n)
    ]


def test_a_large_run_is_one_session_in_batches_the_edge_accepts(ingest: Ingest) -> None:
    sink = _sink(ingest.url, session_id="compare-20261011T000000Z__serene__browse_verified")
    records = _records(300)
    for name, attrs in records:
        sink.emit(name, attrs)
    report = sink.flush()
    assert report.ok and report.spans == 300 and report.batches == len(ingest.bodies) > 1
    assert report.batches_sent == report.batches and report.errors == ()
    assert all(k == KEY for k in ingest.keys)
    sessions = {b["attributes"]["neatlogs.session.id"] for b in ingest.bodies}
    assert sessions == {"compare-20261011T000000Z__serene__browse_verified"}
    assert [b["attributes"]["serene.batch.index"] for b in ingest.bodies] == list(
        range(report.batches)
    )
    assert {b["attributes"]["serene.batch.count"] for b in ingest.bodies} == {report.batches}
    sent = [c["attributes"]["serene.task_id"] for b in ingest.bodies for c in b["children"]]
    assert sent == [a["task_id"] for _, a in records]  # nothing lost, nothing reordered
    for body in ingest.bodies:
        assert len(json.dumps(body, separators=(",", ":"))) <= MAX_BODY_BYTES
    first = ingest.bodies[0]["children"][0]
    assert first["kind"] == "LLM" and first["status"] == "ERROR"  # i == 0 is FAILED
    assert first["tokens"] == {"prompt": 1200, "completion": 30} and first["tool_name"] == "none"
    assert sink.pending == 0


def test_an_oversized_body_is_reported_as_the_edge_403_not_swallowed(ingest: Ingest) -> None:
    sink = _sink(ingest.url, max_body_bytes=40_000)  # misconfigured above the edge limit
    for name, attrs in _records(300):
        sink.emit(name, attrs)
    report = sink.flush()
    assert not report.ok and "HTTP_403" in report.errors
    assert report.batches_sent < report.batches


def test_a_redirect_is_refused_and_the_key_never_follows_it(ingest: Ingest) -> None:
    other = Ingest()
    for target in _serve(other):
        ingest.redirect_to = target.url
        sink = _sink(ingest.url)
        sink.emit("runtime.call", {"status": "OK"})
        report = sink.flush()
        assert report.errors == ("REDIRECT_REFUSED",) and not report.ok
        assert other.keys == [] and other.bodies == []


def test_unreachable_ingest_is_an_explicit_failure_never_an_exception() -> None:
    sink = _sink("http://127.0.0.1:9/v1/trace", timeout_s=2)  # discard port: nothing listens
    sink.emit("runtime.call", {"status": "OK"})
    report = sink.flush()
    assert not report.ok and report.batches_sent == 0
    assert report.errors and report.errors[0].startswith(("NETWORK_", "TIMEOUT"))


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://ingest.neatlogs.com/v1/trace",  # plaintext off loopback would expose the key
        "https://user:pw@example.com/v1/trace",
        "https://ingest.neatlogs.com:abc/v1/trace",
        "ftp://ingest.neatlogs.com/v1/trace",
    ],
)
def test_unsafe_endpoints_are_refused_before_any_request(endpoint: str) -> None:
    calls: list[Any] = []
    sink = NeatlogsSink(
        "t", api_key=KEY, endpoint=endpoint, opener=lambda r, t: calls.append(r) or 200
    )
    sink.emit("runtime.call", {"status": "OK"})
    report = sink.flush()
    assert report.errors == ("ENDPOINT_REJECTED",) and calls == [] and report.dropped_spans == 1
    assert not endpoint_allowed(endpoint)


def test_the_sink_reapplies_central_redaction(ingest: Ingest) -> None:
    child = "chd_" + "7" * 32
    sink = _sink(ingest.url, session_id="has spaces so it is dropped", end_user_id="Maya Smith")
    sink.emit(
        "ledger.append",
        {
            "child_id": child,  # raw child id: no pseudonym key in the sink, so dropped
            "statement": "Maya cried at the daycare door",  # not allow-listed
            "decision": "Maya cried at pickup",  # allow-listed key, prose value
            "reason_codes": ("LEVEL_SKIP",),
            "api_key": KEY,
        },
    )
    assert sink.flush().ok
    blob = json.dumps(ingest.bodies)
    for leaked in (child, "Maya", "cried", "daycare", KEY, "has spaces"):
        assert leaked not in blob
    (body,) = ingest.bodies
    assert body["children"][0]["attributes"] == {"serene.reason_codes": "LEVEL_SKIP"}
    assert "neatlogs.session.id" not in body["attributes"]


def test_pending_spans_are_bounded_and_overflow_is_counted() -> None:
    sink = NeatlogsSink("t", api_key=KEY, max_pending_spans=10, opener=lambda r, t: 200)
    for name, attrs in _records(15):
        sink.emit(name, attrs)
    report = sink.flush()
    assert report.spans == 10 and report.dropped_spans == 5 and not report.ok


def test_without_a_key_nothing_is_sent_and_telemetry_is_a_noop(monkeypatch: Any) -> None:
    monkeypatch.delenv("NEATLOGS_API_KEY", raising=False)
    assert not isinstance(build_sink("t"), NeatlogsSink)
    sink = NeatlogsSink("t", api_key="", opener=lambda r, t: pytest.fail("no request"))
    sink.emit("runtime.call", {"status": "OK"})
    assert sink.flush().errors == ("NO_API_KEY",)


def test_a_dead_ingest_never_changes_ledger_outcomes() -> None:
    """Same ledger hashes with telemetry going to an unreachable neatlogs as with none."""
    dead = NeatlogsSink("t", api_key=KEY, endpoint="http://127.0.0.1:9/v1/trace", timeout_s=1)
    families = []
    for telemetry in (SafeTelemetry(), SafeTelemetry(dead, pseudonym_key=b"k")):
        fam = SyntheticFamily(seed="neatlogs-dead")
        fam.ledger = EventLedger(
            fam.store, fam.clock, telemetry=telemetry, new_event_id=lambda f=fam: f.new_id("evt")
        )
        fam.observe("fine day", day=0)
        families.append(fam)
    hashes = [[e.event_hash for e in f.ledger.get_events_for_child(f.child_id)] for f in families]
    assert hashes[0] == hashes[1]
    assert dead.pending > 0 and not dead.flush().ok


def test_build_telemetry_uses_the_http_sink_when_keyed(monkeypatch: Any, ingest: Ingest) -> None:
    monkeypatch.setenv("NEATLOGS_API_KEY", KEY)
    monkeypatch.setenv("NEATLOGS_ENDPOINT", ingest.url)
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "neatlogs.verification.marker=marker-123")
    sink = build_sink("serene-live-eval", session_id="run-1")
    assert isinstance(sink, NeatlogsSink)
    sink.emit("evidence.requested", {"acquisition_mode": "BROWSE"})
    assert sink.flush().ok
    (body,) = ingest.bodies
    assert body["name"] == "serene-live-eval"
    assert body["attributes"]["neatlogs.session.id"] == "run-1"
    assert body["attributes"]["neatlogs.verification.marker"] == "marker-123"
    assert build_telemetry("x") is not None


def test_the_live_runner_reports_the_flush_outcome(monkeypatch: Any, ingest: Ingest) -> None:
    from eval.runners import runtime_live_compare as runner

    monkeypatch.setenv("NEATLOGS_API_KEY", KEY)
    monkeypatch.setenv("NEATLOGS_ENDPOINT", ingest.url)
    traces = _records(200)
    out = runner._neatlogs("run-7", SimpleNamespace(traces=traces))  # type: ignore[arg-type]
    assert out["sent"] is True and out["session_id"] == "run-7" and out["spans"] == 200
    assert out["batches"] == out["batches_sent"] == len(ingest.bodies) > 1
    assert out["errors"] == [] and out["dropped_spans"] == 0
    monkeypatch.delenv("NEATLOGS_API_KEY")
    assert runner._neatlogs("run-8", SimpleNamespace(traces=traces)) == {  # type: ignore[arg-type]
        "sent": False,
        "reason": "NEATLOGS_API_KEY unset",
    }
