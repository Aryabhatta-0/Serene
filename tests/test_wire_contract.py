"""Model-usable strict wire (issue #53 follow-up): the contract states the schema exactly,
the schema stays strict, and repair feedback names fields without echoing model text.

`tests/fixtures/live_rejected_proposals.json` holds hypothesis-stage replies that a live
model (deepseek-v4.1-flash via Hermes, prompt serene-hermes/1) produced on 2026-10-10 and
the wire rejected. They are verbatim; their scenario text and ids are synthetic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, get_origin

import pytest

from serene.adapters.hermes import HermesAgentRuntime
from serene.adapters.hermes.runtime import PROMPT_VERSION, repair_feedback
from serene.adapters.hermes.scripted import raw_response
from serene.adapters.hermes.wire import (
    PROPOSAL_KINDS,
    SCHEMA_NAMES,
    WireCandidate,
    WireError,
    WireExperiment,
    WireHypothesis,
    WireNeedEvidence,
    WireObservation,
    WirePattern,
    WireProposals,
    parse_wire,
    plan_contract,
    propose_contract,
)
from serene.domain.entities import Burden, InterventionCategory
from serene.domain.events import AcquisitionMode, PredictedAnswer
from tests.runtime_support import Rig, make_rig, structure_reply

FIXTURE = Path(__file__).parent / "fixtures" / "live_rejected_proposals.json"
LIVE = json.loads(FIXTURE.read_text(encoding="utf-8"))["replies"]
FORMING = ("abstain", "hypothesis", "need_evidence", "pattern")


def _strings(value: Any) -> set[str]:
    """Every key and string value a model wrote."""
    if isinstance(value, dict):
        return set(value) | {s for v in value.values() for s in _strings(v)}
    if isinstance(value, list):
        return {s for v in value for s in _strings(v)}
    return {value} if isinstance(value, str) else set()


def _schema_vocabulary() -> set[str]:
    enums = (InterventionCategory, Burden, AcquisitionMode, PredictedAnswer)
    return set(SCHEMA_NAMES) | {v.value for e in enums for v in e} | {"serene-hermes-wire/1"}


# ---------------------------------------------------------------- captured live failures
@pytest.mark.parametrize("reply", LIVE, ids=[r["source"].split("/")[0][:14] for r in LIVE])
def test_captured_live_rejections_stay_rejected(reply: dict[str, Any]) -> None:
    """Strictness is unchanged: each captured reply fails with the same code and issues."""
    with pytest.raises(WireError) as exc:
        parse_wire(reply["output_text"], WireProposals)
    assert exc.value.code == reply["expected_code"]
    assert list(exc.value.issues) == reply["expected_issues"]


@pytest.mark.parametrize("reply", LIVE, ids=[r["source"].split("/")[0][:14] for r in LIVE])
def test_repair_feedback_locates_fields_without_echoing_model_text(reply: dict[str, Any]) -> None:
    with pytest.raises(WireError) as exc:
        parse_wire(reply["output_text"], WireProposals)
    feedback = repair_feedback(exc.value)
    assert exc.value.issues and all(f"- {i}" in feedback for i in exc.value.issues)
    for issue in exc.value.issues:
        assert re.match(r"^(<root>|[a-z_]+|proposals\[\d+\])[\w\[\].<> ?-]*: [a-z_]+", issue)
    written = _strings(json.loads(reply["output_text"])) - _schema_vocabulary()
    leaked = [s for s in written if len(s) >= 4 and s in feedback]
    assert leaked == []


def test_the_live_invented_categories_are_named_by_location_only() -> None:
    reply = next(r for r in LIVE if r["expected_code"] == "SCHEMA:enum")
    invented = {
        p["category"]
        for p in json.loads(reply["output_text"])["proposals"]
        if p.get("kind") == "experiment"
    }
    with pytest.raises(WireError) as exc:
        parse_wire(reply["output_text"], WireProposals)
    feedback = repair_feedback(exc.value)
    assert "experiment.category: enum (allowed ROUTINE_TIMING|" in feedback
    assert not any(c in feedback for c in invented if c not in _schema_vocabulary())


def test_unknown_keys_and_tags_are_never_echoed() -> None:
    text = json.dumps(
        {
            "contract": "serene-hermes-wire/1",
            "proposals": [{"kind": "approval_for_maya", "granted": True}],
            "secret_note_about_maya": 1,
        }
    )
    with pytest.raises(WireError) as exc:
        parse_wire(text, WireProposals)
    feedback = repair_feedback(exc.value)
    assert "maya" not in feedback.lower()
    assert "<unexpected key>: extra_forbidden" in feedback
    assert "proposals[0]: union_tag_invalid (allowed kind observation|" in feedback


# ---------------------------------------------------------------- the contract states the schema
def test_contract_has_no_placeholders_and_lists_every_enum_value() -> None:
    full = propose_contract() + "\n" + plan_contract()
    assert not re.search(r'":\s*[A-Z][A-Z_]{2,}[,}]', full), "unquoted placeholder value"
    assert "CATEGORY" not in full
    for enum in (InterventionCategory, Burden, AcquisitionMode, PredictedAnswer):
        for member in enum:
            assert f'"{member.value}"' in full, member


@pytest.mark.parametrize(
    "model",
    [WireObservation, WirePattern, WireHypothesis, WireExperiment, WireNeedEvidence],
)
def test_contract_states_every_list_bound_the_schema_enforces(model: Any) -> None:
    contract = propose_contract()
    for name, info in model.model_fields.items():
        lo = next((m.min_length for m in info.metadata if hasattr(m, "min_length")), None)
        hi = next((m.max_length for m in info.metadata if hasattr(m, "max_length")), None)
        if get_origin(info.annotation) is tuple and hi is not None:
            assert f'"{name}":[{lo or 0}-{hi} ' in contract, (model.__name__, name)
    assert '"proposals": [0-16 proposals]' in contract
    assert "1-500 characters" in contract and '"max_duration_days":integer 1-365' in contract


def test_plan_contract_states_candidate_bounds() -> None:
    contract = plan_contract()
    meta = WireCandidate.model_fields["requested_fields"].metadata
    hi = next(m.max_length for m in meta if hasattr(m, "max_length"))
    assert f'"requested_fields":[1-{hi} tags]' in contract
    assert '"candidates": [0-8 candidates]' in contract


def test_contract_offers_only_the_task_kinds() -> None:
    forming = propose_contract(FORMING)
    assert '"kind":"experiment"' not in forming and '"kind":"observation"' not in forming
    assert all(f'"kind":"{k}"' in forming for k in FORMING)
    assert set(PROPOSAL_KINDS) == {"observation", "pattern", "hypothesis", "experiment"} | {
        "need_evidence",
        "abstain",
    }


# ---------------------------------------------------------------- through the runtime
@pytest.fixture
def rig() -> Rig:
    return make_rig("wire-contract")


def test_runtime_prompt_lists_only_the_task_kinds(rig: Rig) -> None:
    rig.family.report("Pickup was hard today")
    rig.transport.push("propose", structure_reply("hard pickup"))
    rig.runtime.run(rig.task(proposal_kinds=("observation", "abstain")))
    sent = rig.transport.requests[0].input
    assert '"kind":"observation"' in sent and '"kind":"experiment"' not in sent
    assert PROMPT_VERSION == "serene-hermes/2"


def test_runtime_repairs_a_captured_live_reply_with_field_level_feedback(rig: Rig) -> None:
    rig.family.report("Pickup was hard today")
    live = next(r for r in LIVE if r["expected_code"] == "SCHEMA:too_long")
    rig.transport.push("propose", raw_response(live["output_text"]), structure_reply("hard"))
    result = rig.runtime.run(rig.task())
    assert result.status == "COMPLETED" and len(result.proposals) == 1
    repair = rig.transport.requests[1].input.split("CONTEXT END")[-1]
    assert "proposals[4].need_evidence.requested_fields: too_long (max_length 8)" in repair
    diag = rig.runtime.last_diagnostics
    assert diag.wire_errors == ["WIRE_SCHEMA"]
    assert diag.wire_issues == ["proposals.need_evidence.requested_fields:too_long"]
    (run,) = [a for n, a in rig.sink.records if n == "runtime.run"]
    assert run["validation_issues"] == "proposals.need_evidence.requested_fields:too_long"


def test_a_second_invalid_reply_still_fails_closed(rig: Rig) -> None:
    rig.family.report("Pickup was hard today")
    live = LIVE[0]["output_text"]
    rig.transport.push("propose", raw_response(live), raw_response(live))
    result = rig.runtime.run(rig.task())
    assert result.status == "FAILED" and result.proposals == ()
    assert isinstance(rig.runtime, HermesAgentRuntime)


def test_contract_says_hypothesis_evidence_lists_take_evidence_ids_only() -> None:
    """Live 2026-10-11: two runs lost every hypothesis to ITEM_WRONG_KIND for obs_ ids here."""
    contract = propose_contract(FORMING)
    assert '"supporting_evidence_ids":[0-32 evd ids]' in contract
    assert "evd_ ids only" in contract and "never obs_/pat_/hyp_ ids" in contract
