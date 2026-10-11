"""Baselines A (#42, plain Hermes) and B (#43, Hermes + ordinary memory/RAG).

Both run in the same harness as Serene, against the same `HermesTransport`
(scripted offline, `HttpHermesTransport` live), with the same bounded browser,
the same scripted parent and a budget derived from Serene's own limits
(`MatchedBudget.from_serene`). Neither has the epistemic ladder, Promotion
Gate, lineage governance, controlled investigation loop, independent verifier
or experiment policy: the model decides what to ask, browse and conclude, and
whatever it reads is used as-is.

Baseline B adds ordinary memory: every report, answer and page capture is
stored as text and the top-k items by term overlap are put in each prompt.

Results use the standard `Trajectory` format, so the same deterministic
scorers apply. Offline (scripted) runs only prove the harness mechanics: the
replies are whatever the script says, so they are never reported as a
comparison. Comparative numbers require a live model.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from eval.scorers.runtime_scorers import Acquisition, EvidenceUse, Trajectory
from serene.adapters.browser import HermesBrowser
from serene.adapters.hermes.transport import HermesRequest, HermesTransport, HermesTransportError
from serene.evidence.capture import parse_capture
from serene.evidence.service import DEFAULT_MAX_ACTIONS
from serene.investigation.service import InvestigationBudget
from serene.policies.external_evidence import host_of
from serene.ports.evidence import EvidenceBrowseRequest
from serene.testing import SyntheticFamily

BASELINE_PROMPT_VERSION: Final = "serene-baseline/1"
_WORD: Final = re.compile(r"[a-z0-9]{3,}")


@dataclass(frozen=True)
class MatchedBudget:
    """One budget for all systems, derived from Serene's own limits."""

    max_model_calls: int
    max_questions: int
    max_browse_actions: int
    max_cost_micro_usd: int

    @classmethod
    def from_serene(
        cls, budget: InvestigationBudget | None = None, max_actions: int = DEFAULT_MAX_ACTIONS
    ) -> MatchedBudget:
        b = budget or InvestigationBudget()
        return cls(
            max_model_calls=b.max_model_runs * b.model_steps,
            max_questions=b.max_evidence_rounds,
            max_browse_actions=max_actions * b.max_evidence_rounds,
            max_cost_micro_usd=b.model_cost_micro_usd,
        )


_INSTRUCTIONS: Final = """You are a helpful family assistant. Using the history, answer the
parent's question. You may ask the parent one short question, or read one web page, per turn.
Reply with ONE JSON object:
  {"action": "ask", "question": "...", "fields": ["<what you want to learn>"]}
  {"action": "browse", "goal": "...", "subject": "<topic_tag>", "fields": ["..."]}
  {"action": "answer", "cause": "<the most likely cause>", "hypotheses": ["..."]}"""


@dataclass
class _Memory:
    items: list[tuple[str, str, str]] = field(default_factory=list)  # (ref, kind, text)

    def add(self, ref: str, kind: str, text: str) -> None:
        self.items.append((ref, kind, text))

    def retrieve(self, query: str, k: int = 5) -> list[tuple[str, str, str]]:
        terms = set(_WORD.findall(query.casefold()))
        scored = sorted(
            self.items,
            key=lambda item: (-len(terms & set(_WORD.findall(item[2].casefold()))), item[0]),
        )
        return scored[:k]


class BaselineAgent:
    def __init__(
        self,
        system: str,
        transport: HermesTransport,
        *,
        memory_rag: bool,
        budget: MatchedBudget,
        allowed_domains: tuple[str, ...],
        pinned_sources: tuple[str, ...] = (),
    ) -> None:
        self.system = system
        self._transport = transport
        self._rag = memory_rag
        self.budget = budget
        self._allowed = allowed_domains
        self._pinned = pinned_sources  # same pages Serene's planner/browser are given

    def run(
        self,
        scenario: Any,
        reports: tuple[str, ...],
        question: str,
        seed: str,
        parent: Callable[[str, tuple[str, ...]], str | None] | None = None,
    ) -> Any:
        """`parent` answers a question (live runs share one simulated parent with Serene);
        without it the scenario's per-field answers are used."""
        fam = SyntheticFamily(seed=f"baseline-{seed}")
        browser = HermesBrowser(
            self._transport,
            clock=fam.clock,
            observer=fam.system,
            new_entity_id=fam.new_id,
            pinned_sources=self._pinned,
        )
        sources = f"BROWSE SOURCES: {json.dumps(list(self._pinned))}\n" if self._pinned else ""
        memory = _Memory()
        for i, text in enumerate(reports):
            memory.add(f"report-{i}", "REPORT", text)
        transcript: list[str] = [f"PARENT REPORT: {r}" for r in reports]
        questions: list[tuple[str, ...]] = []
        evidence: list[Any] = []
        # A baseline keeps no hypothesis set and states no predictions while it acts,
        # and never verifies a capture, so it records no discrimination claim.
        acquisitions: list[Any] = []
        calls = actions = 0
        terminal, conclusion, hypotheses = "BUDGET_EXHAUSTED", None, ()
        while calls < self.budget.max_model_calls:
            calls += 1
            context = list(transcript)
            if self._rag:
                retrieved = memory.retrieve(question)
                context = [f"MEMORY[{ref}] ({kind}): {text}" for ref, kind, text in retrieved]
                context += transcript[len(reports) :]
                for ref, kind, _ in retrieved:
                    if kind == "EXTERNAL":
                        continue  # already counted when it was browsed
                    evidence.append(EvidenceUse(ref, kind, "UNVERIFIED", None, False, True))
            try:
                reply = self._transport.respond(
                    HermesRequest(
                        purpose="propose",
                        instructions=_INSTRUCTIONS,
                        input=f"QUESTION: {question}\n" + sources + "\n".join(context),
                        session_ref=f"{self.system}-{seed}-{calls}",
                    )
                )
                action = json.loads(reply.output_text)
            except (HermesTransportError, ValueError):
                terminal = "FAILED"
                break
            kind = action.get("action") if isinstance(action, dict) else None
            if kind == "answer":
                terminal = "CLAIMED_COMPLETE"
                conclusion = str(action.get("cause") or "") or None
                hypotheses = tuple(str(h) for h in action.get("hypotheses") or ())
                break
            fields = tuple(str(f) for f in action.get("fields") or ())[:4] or ("unspecified",)
            if kind == "ask" and len(questions) < self.budget.max_questions:
                questions.append(fields)
                asked = str(action.get("question") or "")
                if parent is not None:
                    said = parent(asked, fields)
                else:
                    answers = [scenario.parent_answers.get(f) for f in fields]
                    said = ", ".join(a for a in answers if a) or None
                acquisitions.append(
                    Acquisition("ASK_PARENT", fields, asked, outcome=_answer_outcome(said))
                )
                transcript.append(f"PARENT ANSWER: {said or '(no reply)'}")
                if said:
                    memory.add(f"answer-{len(questions)}", "ANSWER", said)
                    evidence.append(
                        EvidenceUse(
                            f"answer-{len(questions)}",
                            "ANSWER",
                            "UNVERIFIED",
                            "telegram",
                            False,
                            True,
                            fields,
                        )
                    )
            elif kind == "browse" and actions < self.budget.max_browse_actions:
                result = browser.acquire(
                    EvidenceBrowseRequest(
                        request_id=fam.new_id("erq"),
                        child_id=fam.child_id,
                        goal=str(action.get("goal") or question)[:500],
                        allowed_domains=self._allowed,
                        requested_fields=fields,
                        max_actions=min(
                            DEFAULT_MAX_ACTIONS, self.budget.max_browse_actions - actions
                        ),
                        subject=str(action.get("subject") or "topic")[:64],
                    )
                )
                actions += result.actions_used
                acquisitions.append(
                    Acquisition(
                        "BROWSE",
                        fields,
                        outcome="UNVERIFIED" if result.evidence else "NOT_ACQUIRED",
                    )
                )
                for ev in result.evidence:
                    text = parse_capture(ev.content).excerpt
                    transcript.append(f"WEB PAGE {ev.source.uri}: {text}")
                    memory.add(ev.evidence_id, "EXTERNAL", text)
                    evidence.append(
                        EvidenceUse(
                            ev.evidence_id,
                            "EXTERNAL",
                            "UNVERIFIED",
                            host_of(ev.source.uri),
                            False,
                            True,
                            fields,
                        )
                    )
            else:
                transcript.append("TOOL REFUSED: budget or unknown action")
        return Trajectory(
            system=self.system,
            scenario_id=scenario.scenario_id,
            questions=tuple(questions),
            evidence=tuple(_dedupe(evidence)),
            acquisitions=tuple(acquisitions),
            hypotheses_retained=hypotheses,
            conclusion=conclusion,
            terminal=terminal,
            steps_used=calls,
            step_budget=self.budget.max_model_calls,
            model_calls=calls,
            browse_actions=actions,
        )


def _answer_outcome(said: str | None) -> str:
    if not said:
        return "NO_RESPONSE"
    value = said.strip().upper()
    return value if value in {"YES", "NO", "UNSURE"} else "ANSWERED"


def _dedupe(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item.ref not in seen:
            seen.add(item.ref)
            out.append(item)
    return out


def baseline_a(
    transport: HermesTransport,
    budget: MatchedBudget | None = None,
    *,
    allowed_domains: tuple[str, ...] = ("example.org",),
    pinned_sources: tuple[str, ...] = (),
) -> BaselineAgent:
    return BaselineAgent(
        "baseline_a_plain_hermes",
        transport,
        memory_rag=False,
        budget=budget or MatchedBudget.from_serene(),
        allowed_domains=allowed_domains,
        pinned_sources=pinned_sources,
    )


def baseline_b(
    transport: HermesTransport,
    budget: MatchedBudget | None = None,
    *,
    allowed_domains: tuple[str, ...] = ("example.org",),
    pinned_sources: tuple[str, ...] = (),
) -> BaselineAgent:
    return BaselineAgent(
        "baseline_b_hermes_memory_rag",
        transport,
        memory_rag=True,
        budget=budget or MatchedBudget.from_serene(),
        allowed_domains=allowed_domains,
        pinned_sources=pinned_sources,
    )
