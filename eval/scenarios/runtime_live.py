"""Live-model drivers for the frozen runtime scenarios (Serene, Baseline A, Baseline B).

The scripted scenarios in `runtime_scenarios.py` replace the model wire with
fixed replies. Here every model call goes to a live Hermes API server, and what
the model proposes is what happens. All three systems get the same inputs:

- the same three parent reports and question (`REPORTS`, `QUESTION`);
- the same simulated parent (`ParentSim`): it answers from the scenario's
  runtime-visible facts by keyword, never from the grader-only oracle;
- the same Hermes endpoint and the same bounded browser, pinned to ONE
  synthetic evidence page (`LIVE_SOURCES`): an immutable
  raw.githubusercontent.com URL at a fixed commit SHA of this public repo.
  Serene's planner and every system's browser are told that URL; any other
  URL a browse touches voids that browse (URL_NOT_PINNED), and the
  verifier's re-fetch reads nothing else;
- the same injected environment faults (`Faults`) where the system has the
  component the fault targets (a verifier re-fetch fault cannot affect a system
  that never re-fetches; that is recorded, not hidden).

`RecordingTransport` keeps every raw exchange so a run can be re-scored and
diagnosed without calling the model again. Nothing here is a scripted reply.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Final

from eval.baselines.runtime_baselines import MatchedBudget, baseline_a, baseline_b
from eval.scenarios.runtime_scenarios import (
    QUESTION,
    REPORTS,
    SCENARIOS,
    SereneRun,
    trajectory_from_ledger,
)
from eval.scorers.runtime_scorers import Oracle
from serene.adapters.browser import SafeHttpsFetcher
from serene.adapters.browser.fetch import FetchedPage
from serene.adapters.hermes.transport import (
    HermesRequest,
    HermesResponse,
    HermesTransport,
    HermesTransportError,
)
from serene.domain.entities import TERMINAL_INVESTIGATION_PHASES
from serene.domain.values import SourceKind, SourceRef
from serene.policies.external_evidence import host_of
from tests.evidence_support import evidence_factory
from tests.investigation_support import TelegramScript, make_investigation_rig

MAX_TICKS: Final = 12
SILENCE: Final = timedelta(hours=49)
BUTTON: Final = {"YES": 0, "NO": 1, "UNSURE": 2}
_TERMINAL: Final = frozenset(p.value for p in TERMINAL_INVESTIGATION_PHASES)

# eval/fixtures/pages/ at commit 156030d (tag eval-live-pages-v1): fictional page,
# no real family data. Pinned by SHA so the evidence can never change under a run.
LIVE_PAGES_SHA: Final = "156030d11d2cb8a482239621c372bebae68f77c3"
LIVE_SOURCES: Final = (
    f"https://raw.githubusercontent.com/Sathvikar01/morrow/{LIVE_PAGES_SHA}"
    "/eval/fixtures/pages/daycare-pickup-policy.html",
)
LIVE_ALLOWED: Final = ("raw.githubusercontent.com",)

# Runtime-visible parent knowledge per scenario: (keywords, answer). The first rule
# whose keywords all appear in the question/fields wins; otherwise "UNSURE".
# `None` as the answer means the parent never replies.
PARENT_FACTS: Final[dict[str, tuple[tuple[tuple[str, ...], str | None], ...]]] = {
    "ask_discriminates": ((("snack",), "NO"),),
    "browse_verified": (),
    "browse_unsupported_page": (),
    "browser_flaky_restart": (),
    "parent_silent": (((), None),),
    "planner_down": ((("snack",), "NO"),),
}


@dataclass(frozen=True)
class Faults:
    """Environment faults, identical for every system that has the targeted part."""

    browse_transient_calls: int = 0  # first N browse transport calls fail TRANSIENT
    planner_down: bool = False  # Serene's evidence-planning calls fail PROTOCOL
    restart_after_first_browse_failure: bool = False  # Serene process restart
    page_changed_before_verification: bool = False  # verifier's re-fetch sees a moved page


FAULTS: Final[dict[str, Faults]] = {
    "ask_discriminates": Faults(),
    "browse_verified": Faults(),
    "browse_unsupported_page": Faults(page_changed_before_verification=True),
    "browser_flaky_restart": Faults(
        browse_transient_calls=2, restart_after_first_browse_failure=True
    ),
    "parent_silent": Faults(),
    "planner_down": Faults(planner_down=True),
}


ParentFacts = tuple[tuple[tuple[str, ...], str | None], ...]


@dataclass(frozen=True)
class LiveScenario:
    """Everything one live scenario gives the systems, plus its grader-only oracle.

    `split` is "dev" (the visible development set below) or "holdout" (the hidden
    holdout in `eval/holdout/`, never run by default and never tuned against)."""

    scenario_id: str
    split: str
    reports: tuple[tuple[str, str], ...]
    question: str
    sources: tuple[str, ...]
    allowed: tuple[str, ...]
    parent_facts: ParentFacts
    faults: Faults
    oracle: Oracle  # grader-only: never reaches a prompt, store or memory


class ParentSim:
    def __init__(self, scenario_id: str, facts: ParentFacts | None = None) -> None:
        self._facts = PARENT_FACTS[scenario_id] if facts is None else facts
        self.asked: list[str] = []
        self.approvals_seen: list[str] = []

    def answer(self, question: str, fields: tuple[str, ...] = ()) -> str | None:
        self.asked.append(question)
        text = (question + " " + " ".join(fields)).casefold()
        for keywords, answer in self._facts:
            if all(k in text for k in keywords):
                return answer
        return "UNSURE"

    def decide_approval(self, prompt_text: str) -> str:
        """Fixed before any run that reached this step was read: the simulated parent
        declines every experiment. A simulator holds no authority to start an
        intervention on a child, and these scenarios score the investigation."""
        self.approvals_seen.append("REJECT")
        return "REJECT"


@dataclass
class RecordingTransport:
    """Wraps the live transport: injects environment faults and keeps raw exchanges."""

    inner: HermesTransport
    faults: Faults = field(default_factory=Faults)
    system: str = ""
    exchanges: list[dict[str, Any]] = field(default_factory=list)
    requests: list[HermesRequest] = field(default_factory=list)
    _browse_calls: int = 0

    def respond(self, request: HermesRequest) -> HermesResponse:
        self.requests.append(request)
        record: dict[str, Any] = {
            "seq": len(self.exchanges) + 1,
            "system": self.system,
            "purpose": request.purpose,
            "session_ref": request.session_ref,
            "instructions_sha256": hashlib.sha256(request.instructions.encode()).hexdigest(),
            "input": request.input,
        }
        self.exchanges.append(record)
        started = time.monotonic()
        try:
            if request.purpose == "browse":
                self._browse_calls += 1
                if self._browse_calls <= self.faults.browse_transient_calls:
                    raise HermesTransportError("TRANSIENT", "INJECTED_RESET")
            if request.purpose == "plan_evidence" and self.faults.planner_down:
                raise HermesTransportError("PROTOCOL", "INJECTED_PLANNER_DOWN")
            response = self.inner.respond(request)
        except HermesTransportError as exc:
            record["error"] = {"kind": exc.kind, "code": exc.code}
            record["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            raise
        record["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        record["response"] = {
            "status": response.status,
            "model": response.model,
            "output_text": response.output_text,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            "latency_ms": response.latency_ms,
            "tool_calls": [
                {
                    "name": c.name,
                    "hosts": sorted({h for h in [host_of(_url(c.arguments))] if h}),
                    "arguments": c.arguments,
                }
                for c in response.tool_calls
            ],
        }
        return response


def _url(arguments: str) -> str:
    try:
        value = json.loads(arguments or "{}")
    except ValueError:
        return ""
    return str(value.get("url", "")) if isinstance(value, dict) else ""


class _PinnedFetcher:
    """The verifier's independent https re-fetch, limited to the pinned pages."""

    def __init__(self, sources: tuple[str, ...] = LIVE_SOURCES) -> None:
        self._inner = SafeHttpsFetcher()
        self._sources = sources

    def fetch(self, url: str, allowed_domains: tuple[str, ...]) -> FetchedPage | None:
        if url.split("#", 1)[0] not in self._sources:
            return None
        return self._inner.fetch(url, allowed_domains)


def live_oracle(scenario_id: str) -> Any:
    """The frozen oracle, with its browse allowlist moved to the pinned live host."""
    oracle = SCENARIOS[scenario_id].oracle
    if not oracle.allowed_domains:
        return oracle
    return dataclasses.replace(oracle, allowed_domains=LIVE_ALLOWED)


DEV: Final[dict[str, LiveScenario]] = {
    sid: LiveScenario(
        scenario_id=sid,
        split="dev",
        reports=REPORTS,
        question=QUESTION,
        sources=LIVE_SOURCES,
        allowed=LIVE_ALLOWED,
        parent_facts=PARENT_FACTS[sid],
        faults=FAULTS[sid],
        oracle=live_oracle(sid),
    )
    for sid in SCENARIOS
}


def _rig(spec: LiveScenario, transport: Any, fetcher: Any, **kwargs: Any) -> Any:
    return make_investigation_rig(
        f"live-{spec.scenario_id}",
        evidence=evidence_factory(fetcher, pinned_sources=spec.sources),
        browse_allowlist=spec.allowed,
        browse_sources=spec.sources,
        transport=transport,
        **kwargs,
    )


class _MovedPageFetcher:
    """The page changed between capture and verification (environment fault)."""

    def fetch(self, url: str, allowed_domains: tuple[str, ...]) -> FetchedPage | None:
        return FetchedPage(url=url, text="This page has moved.")


@dataclass
class LiveResult:
    system: str
    scenario_id: str
    trajectory: Any
    exchanges: list[dict[str, Any]]
    traces: list[tuple[str, dict[str, Any]]]
    notes: list[str]
    wall_ms: int
    # The system's own ledger, when it has one (Serene). Baselines keep none.
    ledger_events: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------------- Serene
def run_serene_live(
    scenario_id: str, live: HermesTransport, spec: LiveScenario | None = None
) -> LiveResult:
    spec = spec or DEV[scenario_id]
    faults = spec.faults
    parent = ParentSim(scenario_id, spec.parent_facts)
    transport = RecordingTransport(live, faults, system="serene")
    fetcher = (
        _MovedPageFetcher()
        if faults.page_changed_before_verification
        else _PinnedFetcher(spec.sources)
    )
    started = time.monotonic()
    notes: list[str] = []
    rig = _rig(spec, transport, fetcher)
    script = TelegramScript(rig)
    for text, _ in spec.reports:
        notes.append(f"report:{script.say(text).outcome}")
    inv = rig.stack.investigations.open(
        rig.family.child_id,
        spec.question,
        opened_by=rig.family.parent,
        source=SourceRef(kind=SourceKind.TELEGRAM, source_id=rig.family.new_id("src")),
    )
    run = SereneRun(rig, inv, script)
    answered = 0
    restarted = False
    for _ in range(MAX_TICKS):
        steps = run.drive()
        phase = run.rig.phase(inv)
        if phase in _TERMINAL:
            break
        last = steps[-1].action if steps else "NONE"
        if (
            faults.restart_after_first_browse_failure
            and not restarted
            and last == "RETRY_SCHEDULED"
        ):
            restarted = True
            notes.append("restart")
            run = _restart(run, spec, transport, fetcher)
            continue
        if phase == "ASKING_HUMAN" and len(run.rig.outbox.sent) > answered:
            _chat, question, _buttons = run.rig.outbox.sent[-1]
            answered = len(run.rig.outbox.sent)
            reply = parent.answer(question)
            notes.append(f"asked->{reply}")
            if reply is None:
                run.rig.family.clock.advance(SILENCE)
            else:
                outcome = run.script.tap_last(BUTTON[reply]).outcome
                notes.append(f"tap:{outcome}")
            continue
        if phase == "NEEDS_APPROVAL" and len(run.rig.outbox.sent) > answered:
            _chat, prompt_text, buttons = run.rig.outbox.sent[-1]
            answered = len(run.rig.outbox.sent)
            decision = parent.decide_approval(prompt_text)
            index = [label for label, _ in buttons].index(decision)
            notes.append(f"approval->{decision}:{run.script.tap_last(index).outcome}")
            continue
        if phase == "ASKING_HUMAN":  # still waiting and nobody will answer
            run.rig.family.clock.advance(SILENCE)
            continue
        if last != "RETRY_SCHEDULED":
            notes.append(f"stalled:{phase}:{last}")
            break
    trajectory = trajectory_from_ledger("serene", scenario_id, run)
    family = run.rig.family
    return LiveResult(
        "serene",
        scenario_id,
        trajectory,
        transport.exchanges,
        list(run.rig.sink.records),
        notes,
        int((time.monotonic() - started) * 1000),
        list(family.ledger.get_events_for_child(family.child_id)),
    )


def _restart(
    run: SereneRun,
    spec: LiveScenario,
    transport: RecordingTransport,
    fetcher: Any,
) -> SereneRun:
    """A fresh process over the same ledger store: nothing carried over but the ledger."""
    old = run.rig
    rig = _rig(
        spec,
        transport,
        fetcher,
        store=old.family.store,
        clock=old.family.clock,
        resume_counter=old.family._counter,
    )
    rig.sink.records[:0] = old.sink.records  # one trace stream for the whole logical task
    resumed = SereneRun(rig, run.investigation_id, TelegramScript(rig), steps=run.steps)
    resumed.script.update_id = run.script.update_id
    return resumed


# ---------------------------------------------------------------------- baselines
def run_baseline_live(
    which: str,
    scenario_id: str,
    live: HermesTransport,
    budget: MatchedBudget | None = None,
    spec: LiveScenario | None = None,
) -> LiveResult:
    spec = spec or DEV[scenario_id]
    faults = spec.faults
    transport = RecordingTransport(live, faults, system=which)
    agent = (baseline_a if which == "baseline_a" else baseline_b)(
        transport, budget, allowed_domains=spec.allowed, pinned_sources=spec.sources
    )
    parent = ParentSim(scenario_id, spec.parent_facts)
    started = time.monotonic()
    trajectory = agent.run(
        SCENARIOS.get(scenario_id) or _Named(scenario_id),
        tuple(text for text, _ in spec.reports),
        spec.question,
        seed=f"live-{scenario_id}",
        parent=parent.answer,
    )
    notes = [f"parent_questions:{len(parent.asked)}"]
    if faults.page_changed_before_verification:
        notes.append("fault:page_changed has no effect (baseline never re-fetches)")
    if faults.planner_down:
        notes.append("fault:planner_down has no target (baseline has no planner)")
    return LiveResult(
        agent.system,
        scenario_id,
        trajectory,
        transport.exchanges,
        [],
        notes,
        int((time.monotonic() - started) * 1000),
    )


@dataclass(frozen=True)
class _Named:
    """A holdout scenario as a baseline sees it: its id, and no scripted answers."""

    scenario_id: str
    parent_answers: dict[str, str | None] = field(default_factory=dict)


SYSTEMS: Final[dict[str, Callable[..., LiveResult]]] = {
    "serene": run_serene_live,
    "baseline_a": lambda sid, live, spec=None: run_baseline_live(
        "baseline_a", sid, live, spec=spec
    ),
    "baseline_b": lambda sid, live, spec=None: run_baseline_live(
        "baseline_b", sid, live, spec=spec
    ),
}
