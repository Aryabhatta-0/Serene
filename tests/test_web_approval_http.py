"""`POST /web/approvals` (issue #84): the authenticated HTTP boundary for web decisions.

Through real WSGI calls: who may call (401/403), what may be sent (origin,
size, type, shape, rate), and that every decision still goes through the
channel and the ledger's admission: GREEN approve and decline move the
lifecycle, RED, a stale digest, an understated class and a too-early AMBER
approval are refused, and a replayed `request_id` is never a second decision.
"""

from __future__ import annotations

import http.server
import io
import json
import logging
import threading
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import ValidationError

from serene.adapters.web import WebApprovalChannel, WebApprovalCommand, WebDecision
from serene.adapters.web.guardians import WebBinding, WebBindings, WebPrincipals
from serene.adapters.web.http import (
    MAX_BODY_BYTES,
    PATH,
    RateLimiter,
    ReplayCache,
    make_approvals_app,
)
from serene.adapters.web.session import SupabaseSessionVerifier
from serene.domain.events import EventType, SafetyClass
from serene.domain.values import ActorKind, ActorRef
from serene.projections.state import ApprovalState, ExperimentStatus
from serene.testing import SyntheticFamily

from .experiments_view_fixture import COMMAND_EXAMPLE, build_fixture, command
from .trust_helpers import C, awaiting_approval, event_types, intervention

ORIGIN = "https://serene.example.org"
PARENT_USER = str(uuid.UUID(int=1))
OTHER_USER = str(uuid.UUID(int=2))
PARENT_TOKEN = "fake-parent.a.b"
TOKENS = {PARENT_TOKEN: PARENT_USER, "fake-other.a.b": OTHER_USER}


class Verifier:
    def verify(self, access_token: str) -> str | None:
        return TOKENS.get(access_token)


class Guardians:
    def __init__(self, rows: set[tuple[str, str]]) -> None:
        self.rows = rows

    def is_parent(self, user_id: str, child_id: str) -> bool:
        return (user_id, child_id) in self.rows


def _rid(n: int) -> str:
    return f"http-request-{n:08d}"


class Rig:
    def __init__(self, fam: SyntheticFamily, **kwargs: Any) -> None:
        self.fam = fam
        self.guardians = Guardians({(PARENT_USER, fam.child_id)})
        self.bindings = WebBindings.of(
            [WebBinding(user_id=uuid.UUID(PARENT_USER), child_id=fam.child_id, actor=fam.parent)]
        )
        self.replays = kwargs.pop("replays", ReplayCache())
        self.app = make_approvals_app(
            WebApprovalChannel(fam.ledger, fam.clock, new_source_id=lambda: fam.new_id("src")),
            Verifier(),
            WebPrincipals(self.guardians, self.bindings),
            allowed_origins=frozenset({ORIGIN}),
            replays=self.replays,
            **kwargs,
        )

    def call(
        self,
        body: bytes | dict[str, Any] | None = None,
        *,
        token: str | None = PARENT_TOKEN,
        origin: str | None = ORIGIN,
        method: str = "POST",
        path: str = PATH,
        content_type: str = "application/json",
        length: int | None = None,
    ) -> tuple[int, dict[str, Any]]:
        raw = body if isinstance(body, bytes) else json.dumps(body or {}).encode()
        env: dict[str, Any] = {
            "PATH_INFO": path,
            "REQUEST_METHOD": method,
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(len(raw) if length is None else length),
            "wsgi.input": io.BytesIO(raw),
        }
        if token is not None:
            env["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        if origin is not None:
            env["HTTP_ORIGIN"] = origin
        status: list[str] = []
        out = b"".join(self.app(env, lambda s, _h: status.append(s)))
        return int(status[0].split()[0]), json.loads(out)

    def decide(self, cmd: WebApprovalCommand, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        body = {"child_id": self.fam.child_id, "command": cmd.model_dump(mode="json")}
        return self.call(body, **kwargs)


@pytest.fixture
def green() -> tuple[Rig, Any, str]:
    fam = SyntheticFamily(seed="http-green")
    exp, apr = awaiting_approval(fam)
    return Rig(fam), exp, apr


# ------------------------------------------------------------------ who may call
def test_no_valid_session_is_401_and_nothing_is_appended(green: tuple[Rig, Any, str]) -> None:
    rig, exp, apr = green
    cmd = command(rig.fam, exp, WebDecision.APPROVE, _rid(1))
    before = len(event_types(rig.fam))
    for token in (None, "", "forged.a.b"):
        assert rig.decide(cmd, token=token) == (401, {"error": "NOT_AUTHENTICATED"})
    env_basic = rig.call({}, token=None)
    assert env_basic[0] == 401
    assert len(event_types(rig.fam)) == before
    assert rig.fam.state().approvals[apr].state is ApprovalState.PENDING


def test_a_non_guardian_or_unbound_user_is_403(green: tuple[Rig, Any, str]) -> None:
    rig, exp, apr = green
    cmd = command(rig.fam, exp, WebDecision.APPROVE, _rid(1))
    # Signed in, but the parent of a different child.
    assert rig.decide(cmd, token="fake-other.a.b") == (403, {"error": "NOT_THIS_CHILDS_PARENT"})
    # Guardianship removed from the registry: the binding alone is not enough.
    rig.guardians.rows.clear()
    assert rig.decide(cmd)[0] == 403
    # The registry alone is not enough either: no bound actor for this user.
    rig.guardians.rows.add((OTHER_USER, rig.fam.child_id))
    assert rig.decide(cmd, token="fake-other.a.b")[0] == 403
    # Another child's id in the body.
    other = {"child_id": "chd_" + "f" * 32, "command": cmd.model_dump(mode="json")}
    assert rig.call(other)[0] == 403
    assert rig.fam.state().approvals[apr].state is ApprovalState.PENDING


def test_only_a_parent_can_be_bound_for_web_decisions() -> None:
    fam = SyntheticFamily(seed="http-bind")
    with pytest.raises(ValidationError):
        WebBinding(user_id=uuid.UUID(PARENT_USER), child_id=fam.child_id, actor=fam.caregiver)


def test_the_body_can_never_name_the_actor(green: tuple[Rig, Any, str]) -> None:
    rig, exp, apr = green
    cmd = command(rig.fam, exp, WebDecision.APPROVE, _rid(1)).model_dump(mode="json")
    for forged in (
        {"child_id": rig.fam.child_id, "command": cmd, "actor": rig.fam.parent.model_dump()},
        {"child_id": rig.fam.child_id, "command": cmd | {"actor_id": rig.fam.parent.actor_id}},
    ):
        assert rig.call(forged) == (400, {"error": "MALFORMED_REQUEST"})
    assert rig.fam.state().approvals[apr].state is ApprovalState.PENDING


# ------------------------------------------------------------------ what may be sent
def test_cross_site_origin_size_type_method_and_path_are_refused(
    green: tuple[Rig, Any, str],
) -> None:
    rig, exp, apr = green
    cmd = command(rig.fam, exp, WebDecision.APPROVE, _rid(1))
    assert rig.decide(cmd, origin="https://evil.example.com") == (
        403,
        {"error": "ORIGIN_NOT_ALLOWED"},
    )
    assert rig.call(b"x" * (MAX_BODY_BYTES + 1))[0] == 413
    assert rig.call(b"{}", length=MAX_BODY_BYTES + 1)[0] == 413  # refused before reading
    assert rig.call(b"{}", length=-5)[0] == 413
    assert rig.call({}, content_type="text/plain")[0] == 415
    assert rig.call({}, method="GET")[0] == 405
    assert rig.call({}, path="/web/approvals/")[0] == 404
    assert rig.call(b"{not json")[0] == 400
    assert rig.fam.state().approvals[apr].state is ApprovalState.PENDING
    # A server-to-server call (no Origin header) from the web app's route is fine.
    assert rig.decide(cmd, origin=None)[0] == 200


def test_requests_are_rate_limited_per_user(green: tuple[Rig, Any, str]) -> None:
    rig, exp, _apr = green
    clock = [0.0]
    limited = Rig(rig.fam, limiter=RateLimiter(limit=3, window=60, now=lambda: clock[0]))
    for _ in range(3):
        assert limited.call({"child_id": rig.fam.child_id})[0] == 400  # counted, then malformed
    assert limited.call({}) == (429, {"error": "RATE_LIMITED"})
    assert limited.call({}, token="fake-other.a.b")[0] == 400  # another user is unaffected
    clock[0] = 61.0
    assert limited.decide(command(rig.fam, exp, WebDecision.APPROVE, _rid(9)))[0] == 200


# ------------------------------------------------------------------ the decision
def test_green_approve_over_http_moves_the_lifecycle(green: tuple[Rig, Any, str]) -> None:
    rig, exp, apr = green
    status, answer = rig.decide(command(rig.fam, exp, WebDecision.APPROVE, _rid(1)))
    assert status == 200 and answer["outcome"] == "APPROVAL_GRANTED"
    assert answer["reason_codes"] == [] and len(answer["event_ids"]) == 1
    state = rig.fam.state()
    assert state.experiments[exp.experiment_id].status is ExperimentStatus.APPROVED
    assert state.approvals[apr].decided_via == "WEB_APP"
    event = rig.fam.ledger.get_events_for_child(rig.fam.child_id)[-1]
    assert event.actor == rig.fam.parent  # the bound act_ id, never the Supabase user id
    assert PARENT_USER not in event.model_dump_json()


def test_decline_over_http_abandons_the_experiment(green: tuple[Rig, Any, str]) -> None:
    rig, exp, _apr = green
    status, answer = rig.decide(command(rig.fam, exp, WebDecision.DECLINE, _rid(1)))
    assert (status, answer["outcome"]) == (200, "APPROVAL_REJECTED")
    assert rig.fam.state().experiments[exp.experiment_id].status is ExperimentStatus.ABANDONED


def test_red_stale_and_understated_decisions_are_refused(green: tuple[Rig, Any, str]) -> None:
    rig, exp, apr = green
    red = command(rig.fam, exp, WebDecision.APPROVE, _rid(1)).model_copy(
        update={"shown_safety_class": SafetyClass.RED}
    )
    assert rig.decide(red)[1] == {
        "outcome": "REFUSED",
        "event_ids": [],
        "reason_codes": ["RED_CANNOT_BE_APPROVED"],
    }
    stale = command(rig.fam, exp, WebDecision.APPROVE, _rid(2)).model_copy(
        update={"shown_intervention_digest": "0" * 64}
    )
    assert "INTERVENTION_DIGEST_MISMATCH" in rig.decide(stale)[1]["reason_codes"]
    assert rig.fam.state().approvals[apr].state is ApprovalState.PENDING

    fam = SyntheticFamily(seed="http-amber")
    amber, amber_apr = awaiting_approval(fam, intervention(C.SLEEP_SCHEDULE, "Earlier nap"))
    amber_rig = Rig(fam)
    understated = command(fam, amber, WebDecision.APPROVE, _rid(3)).model_copy(
        update={"shown_safety_class": SafetyClass.GREEN}
    )
    assert "SAFETY_CLASS_NOT_ACKNOWLEDGED" in amber_rig.decide(understated)[1]["reason_codes"]
    early = amber_rig.decide(command(fam, amber, WebDecision.APPROVE, _rid(4)))[1]
    assert early["outcome"] == "REFUSED"
    assert "AMBER_DELIBERATION_TOO_SHORT" in early["reason_codes"]
    assert fam.state().approvals[amber_apr].state is ApprovalState.PENDING


def test_a_replayed_request_id_is_never_a_second_decision(green: tuple[Rig, Any, str]) -> None:
    rig, exp, _apr = green
    cmd = command(rig.fam, exp, WebDecision.APPROVE, _rid(1))
    first = rig.decide(cmd)
    assert first[1]["outcome"] == "APPROVAL_GRANTED"
    assert rig.decide(cmd) == first  # a retried request gets the same answer
    declined = cmd.model_copy(update={"decision": WebDecision.DECLINE})
    assert rig.decide(declined) == (409, {"error": "REQUEST_ID_REUSED"})
    # After a restart (empty cache) the ledger's receipt check still holds.
    restarted = Rig(rig.fam, replays=ReplayCache())
    again = restarted.decide(cmd)
    assert again[1]["outcome"] == "REFUSED"
    assert event_types(rig.fam).count(EventType.APPROVAL_GRANTED) == 1
    assert EventType.APPROVAL_REJECTED not in event_types(rig.fam)


def test_the_web_apps_command_example_round_trips_over_http() -> None:
    built = build_fixture()
    rig = Rig(built.fam)
    example = json.loads(COMMAND_EXAMPLE.read_text(encoding="utf-8"))
    status, answer = rig.call({"child_id": built.fam.child_id, "command": example})
    assert (status, answer["outcome"]) == (200, "APPROVAL_GRANTED"), answer
    status_of = built.fam.state().experiments[built.awaiting_green.experiment_id].status
    assert status_of is ExperimentStatus.APPROVED


def test_no_user_or_child_id_is_logged_or_echoed(
    green: tuple[Rig, Any, str], caplog: pytest.LogCaptureFixture
) -> None:
    rig, exp, _apr = green
    caplog.set_level(logging.DEBUG)
    replies = [
        rig.decide(command(rig.fam, exp, WebDecision.APPROVE, _rid(1))),
        rig.decide(command(rig.fam, exp, WebDecision.APPROVE, _rid(2)), token="fake-other.a.b"),
        rig.call({"child_id": rig.fam.child_id, "command": {"bad": True}}),
    ]
    text = caplog.text + json.dumps(replies)
    for secret in (PARENT_USER, OTHER_USER, rig.fam.child_id, "fake-parent"):
        assert secret not in text


# ------------------------------------------------------------------ Supabase Auth
class _AuthStub(http.server.BaseHTTPRequestHandler):
    answers: dict[str, tuple[int, dict[str, Any]]] = {}

    def do_GET(self) -> None:
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        ok = self.path == "/auth/v1/user" and self.headers.get("apikey") == "anon-key"
        status, body = self.answers.get(token, (401, {})) if ok else (400, {})
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def auth_stub() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _AuthStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_sessions_are_verified_by_supabase_auth(auth_stub: str) -> None:
    _AuthStub.answers = {
        "good.jwt.token": (200, {"id": PARENT_USER, "aud": "authenticated"}),
        "anon.jwt.token": (200, {"id": PARENT_USER, "aud": "anon"}),
        "weird.jwt.token": (200, {"id": "not-a-uuid", "aud": "authenticated"}),
    }
    verifier = SupabaseSessionVerifier(auth_stub, "anon-key")
    assert verifier.verify("good.jwt.token") == PARENT_USER
    assert verifier.verify("anon.jwt.token") is None
    assert verifier.verify("weird.jwt.token") is None
    assert verifier.verify("expired.jwt.token") is None  # Supabase says 401
    assert verifier.verify("not a token") is None
    assert verifier.verify("a." * 3000 + "b") is None
    assert (
        SupabaseSessionVerifier("http://127.0.0.1:9", "anon-key").verify("good.jwt.token") is None
    )
    with pytest.raises(ValueError):
        SupabaseSessionVerifier("http://serene.example.org", "anon-key")


# ------------------------------------------------------------------ Postgres
@pytest.mark.postgres
def test_an_http_decision_reaches_the_projection_the_web_app_reads(pg_dsn: str) -> None:
    from serene.adapters.postgres import (
        PostgresEventStore,
        PostgresProjectionStore,
        postgres_ledger,
    )

    fam = SyntheticFamily(seed="http-pg", store=PostgresEventStore(pg_dsn))
    fam.ledger = postgres_ledger(pg_dsn, fam.clock)
    exp, apr = awaiting_approval(fam)
    assert apr in PostgresProjectionStore(pg_dsn).load(fam.child_id)["pending_approvals"]
    status, answer = Rig(fam).decide(command(fam, exp, WebDecision.APPROVE, _rid(1)))
    assert (status, answer["outcome"]) == (200, "APPROVAL_GRANTED")
    # The lifecycle the web app sees moved only because the kernel recorded it.
    assert PostgresProjectionStore(pg_dsn).load(fam.child_id)["pending_approvals"] == {}


def test_a_bound_principal_is_resolved_only_with_registry_agreement() -> None:
    fam = SyntheticFamily(seed="http-principals")
    bindings = WebBindings.of(
        [WebBinding(user_id=uuid.UUID(PARENT_USER), child_id=fam.child_id, actor=fam.parent)]
    )
    agree = WebPrincipals(Guardians({(PARENT_USER, fam.child_id)}), bindings)
    assert agree.parent(PARENT_USER, fam.child_id) == fam.parent
    assert WebPrincipals(Guardians(set()), bindings).parent(PARENT_USER, fam.child_id) is None
    assert agree.parent(OTHER_USER, fam.child_id) is None
    assert ActorRef(kind=ActorKind.PARENT, actor_id=fam.parent.actor_id) == fam.parent
