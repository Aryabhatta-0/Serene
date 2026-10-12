import copy
from typing import Any

import pytest

from scripts.maya_web_state import build_web_state
from serene.demo.maya import MayaDemo
from serene.domain.canonical import canonical_json


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return MayaDemo(tmp_path_factory.mktemp("maya-web") / "memory").run()


def test_adapter_uses_real_canonical_views_without_mutating_report(report: dict[str, Any]) -> None:
    original = canonical_json(report)
    view = build_web_state(report)
    inv = view["investigations"][report["investigation_id"]]
    assert inv["phase"] == "COMPLETE"
    assert len(inv["hypotheses"]) == 3
    assert "COMPETING_EXPLANATIONS" in inv["uncertainty"]
    assert inv["next_action"]["kind"] == "NONE_COMPLETE"
    assert any(
        r["status"] == "OPEN"
        for snapshot in view["snapshots"]
        for i in snapshot["investigations"].values()
        for r in i["evidence_requests"]
    )
    evidence = [e for r in inv["evidence_requests"] for e in r["evidence"]]
    assert {e["verification_status"] for e in evidence} >= {"VERIFIED", "REJECTED"}
    experiment = view["experiments"]["experiments"][0]
    assert experiment["phase"] == "COMPLETED"
    assert experiment["approval"]["state"] == "GRANTED"
    assert experiment["approval"]["decided_via"] == "TELEGRAM"
    assert experiment["approval"]["decision_open"] is False
    assert experiment["outcomes"]
    assert [(p["from_level"], p["to_level"]) for p in view["promotions"]] == [(3, 4), (4, 5)]
    assert {p["status"] for p in view["memory"]["patches"]} == {"COMMITTED", "REJECTED"}
    assert view["memory"]["memories"][0]["revision"] == report["memory_head"]
    assert view["twin_after"] == report["twin_after"]
    assert canonical_json(report) == original


def test_adapter_rejects_corrupt_or_non_demo_reports(report: dict[str, Any]) -> None:
    corrupt = copy.deepcopy(report)
    corrupt["events"][0]["payload"]["text"] = "tampered"
    with pytest.raises(ValueError, match="hash chain"):
        build_web_state(corrupt)
    with pytest.raises(ValueError, match="synthetic"):
        build_web_state({**report, "synthetic": False})
    corrupt = {**report, "twin_after": report["twin_before"]}
    with pytest.raises((ValueError, AssertionError)):
        build_web_state(corrupt)


def test_adapter_projects_complete_twin_provenance_for_both_twins(report: dict[str, Any]) -> None:
    """Issue #75: every Maya edge, before and after, resolves to raw evidence."""
    from serene.causal.provenance import TwinProvenanceView

    view = build_web_state(report)
    for when in ("before", "after"):
        twin = view[f"twin_{when}"]
        provenance = TwinProvenanceView.model_validate_json(
            canonical_json(view[f"twin_provenance_{when}"])
        )
        assert provenance.ledger_head == twin["ledger_head"]
        assert [e.edge_id for e in provenance.edges] == [e["edge_id"] for e in twin["edges"]]
        assert provenance.missing == ()
        for edge, raw in zip(provenance.edges, twin["edges"], strict=True):
            assert edge.lineage.complete
            assert edge.lineage.raw_evidence == tuple(raw["raw_evidence"])
            assert edge.status.value == raw["status"]
    after = TwinProvenanceView.model_validate_json(canonical_json(view["twin_provenance_after"]))
    (learned,) = (e for e in after.edges if e.epistemic_level == 5)
    assert learned.learning is not None and learned.validity is not None
    assert [o.experiment_id for x in learned.experiments for o in x.outcomes] == [
        x.experiment_id for x in learned.experiments
    ]
    text = canonical_json(view["twin_provenance_after"]).decode()
    assert report["twin_after"]["child_id"] not in text


def test_the_canonical_maya_ledger_projects_to_the_live_twin_without_identifiers(
    report: dict[str, Any],
) -> None:
    """The live `causal_twin` row, built from Maya's own events; the report is untouched."""
    import json

    from serene.causal.web import WebCausalTwin, private_identifiers
    from serene.domain.events import DomainEvent
    from serene.projections.views import rebuild_projections

    original = canonical_json(report)
    events = [DomainEvent.model_validate_json(json.dumps(e)) for e in report["events"]]
    twin = rebuild_projections(events)["causal_twin"]
    view = WebCausalTwin.model_validate_json(json.dumps(twin))
    assert private_identifiers(twin) == []
    assert report["twin_after"]["child_id"] not in json.dumps(twin)
    # The same edges and verdicts as the report's canonical twin.
    assert [(e.edge_id, e.status.value) for e in view.edges] == [
        (e["edge_id"], e["status"]) for e in report["twin_after"]["edges"]
    ]
    assert canonical_json(report) == original
