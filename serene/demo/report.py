"""Judge-readable evidence derived from the canonical Maya ledger."""

from __future__ import annotations

import json
from html import escape
from typing import Any

from serene.domain.events import DomainEvent
from serene.lineage.chain import verify_hash_chain

# A beat carries the ledger sequence that proves it; repeated beats may share an event.
BEATS = (
    ("Telegram input", "OBSERVATION_REPORTED"),
    ("Investigation opens", "INVESTIGATION_OPENED"),
    ("Fatigue vs hunger vs transition hypotheses", "HYPOTHESIS_PROPOSED"),
    ("Missing evidence", "EVIDENCE_REQUESTED"),
    ("Parent question and answer", "OBSERVATION_REPORTED"),
    ("Browser evidence acquisition", "EVIDENCE_ACQUIRED"),
    ("Injected acquisition failure", "EVIDENCE_ACQUISITION_FAILED"),
    ("Retry and recovery", "EVIDENCE_ACQUIRED"),
    ("Verifier rejects unsuitable excerpt", "EVIDENCE_REJECTED"),
    ("Recovery to admissible evidence", "EVIDENCE_VERIFIED"),
    ("Green experiment proposal", "EXPERIMENT_CLASSIFIED"),
    ("Parent approval", "APPROVAL_GRANTED"),
    ("Experiment outcome", "OUTCOME_REPORTED"),
    ("Promotion Gate", "PROMOTION_GRANTED"),
    ("Dream run", "MEMORY_DREAM_STAGE_RECORDED"),
    ("Dream patch accepted", "MEMORY_PATCH_COMMITTED"),
    ("Dream patch rejected with reason", "MEMORY_PATCH_REJECTED"),
    ("Causal Twin update", "LEARNING_RECORDED"),
)


def verify_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Revalidate evidence, not a caller's success flag. Raise on an incomplete demo."""
    events = [DomainEvent.model_validate_json(json.dumps(e)) for e in report["events"]]
    if not verify_hash_chain(events).ok:
        raise ValueError("Invalid Maya hash chain")
    by_type: dict[str, list[DomainEvent]] = {}
    for event in events:
        by_type.setdefault(event.event_type.value, []).append(event)
    missing = {kind for _, kind in BEATS} - set(by_type)
    if missing:
        raise ValueError(f"Missing Maya events: {sorted(missing)}")
    failed = by_type["EVIDENCE_ACQUISITION_FAILED"]
    acquired = by_type["EVIDENCE_ACQUIRED"]
    rejected, verified = by_type["EVIDENCE_REJECTED"], by_type["EVIDENCE_VERIFIED"]
    approvals, starts = by_type["APPROVAL_GRANTED"], by_type["EXPERIMENT_STARTED"]
    assert len(failed) == len(rejected) == len(verified) == 1
    assert failed[0].payload["retryable"] and failed[0].payload["attempt"] == 1
    assert failed[0].payload["failure"] == "TRANSIENT"
    assert report["retry_action"] == "RETRY_SCHEDULED" and report["browser_calls"] == 3
    assert acquired[0].payload["request_id"] == failed[0].payload["request_id"]
    assert failed[0].sequence < acquired[0].sequence < rejected[0].sequence
    assert rejected[0].sequence < acquired[1].sequence < verified[0].sequence
    assert rejected[0].payload["reason_codes"] == ["EXCERPT_NOT_ON_SOURCE"]
    assert rejected[0].payload["evidence_id"] != verified[0].payload["evidence_id"]
    checks = verified[0].payload["checks_passed"]
    assert isinstance(checks, list) and len(checks) == 6
    assert verified[0].sequence < by_type["EXPERIMENT_PROPOSED"][0].sequence
    assert by_type["EXPERIMENT_CLASSIFIED"][0].payload["safety_class"] == "GREEN"
    assert (
        approvals[0].actor.kind.value == "PARENT" and approvals[0].source.kind.value == "TELEGRAM"
    )
    assert approvals[0].sequence < starts[0].sequence < by_type["OUTCOME_REPORTED"][0].sequence
    assert by_type["OUTCOME_REPORTED"][0].sequence < by_type["PROMOTION_GRANTED"][0].sequence
    assert [
        (e.payload["from_level"], e.payload["to_level"]) for e in by_type["PROMOTION_GRANTED"]
    ] == [(3, 4), (4, 5)]
    assert [e.payload["stage"] for e in by_type["MEMORY_DREAM_STAGE_RECORDED"]] == [
        "ORIENT",
        "CONSOLIDATE",
        "REFLECT",
        "CHALLENGE",
        "VERIFY",
        "PROPOSE_PATCH",
    ]
    assert report["dream_rejections"] == [["INSUFFICIENT_EVIDENCE:OBSERVATION_BELOW_PATTERN"]]
    assert list(report["memory"]) == ["learnings/maya-pickup.md"]
    assert len(by_type["HYPOTHESIS_PROPOSED"]) == 3
    assert all(e["status"] == "CANDIDATE" for e in report["twin_before"]["edges"])
    supported = [e for e in report["twin_after"]["edges"] if e["status"] == "SUPPORTED"]
    assert len(supported) == 1 and supported[0]["epistemic_level"] == 5
    assert supported[0]["experiments"] and supported[0]["validity"]
    assert report["phase"] == "COMPLETE" and report["synthetic"] is True
    rows: list[dict[str, Any]] = [
        {"beat": i, "title": title, "sequences": [e.sequence for e in by_type[kind]]}
        for i, (title, kind) in enumerate(BEATS, 1)
    ]
    # The answer is the report bound to an evidence request, not the initial input.
    rows[4]["sequences"] = [
        e.sequence for e in by_type["OBSERVATION_REPORTED"] if e.payload.get("request_id")
    ]
    assert rows[4]["sequences"]
    return rows


def render_html(report: dict[str, Any]) -> str:
    rows = verify_report(report)
    timeline = "".join(
        f"<li><b>{escape(r['title'])}</b> — ledger #{r['sequences']}</li>" for r in rows
    )
    edges = "".join(
        f"<tr><td>{escape(e['relationship'])}</td><td>{e['status']}</td>"
        f"<td>{e['epistemic_level']}</td></tr>"
        for e in report["twin_after"]["edges"]
    )
    ledger = "".join(
        f"<tr><td>{e['sequence']}</td><td>{e['event_type']}</td>"
        f"<td>{escape(str(e['payload'].get('reason_codes', '')))}</td></tr>"
        for e in report["events"]
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<title>Serene · Synthetic Maya demo</title><style>
body{{font:17px system-ui;max-width:1080px;margin:40px auto;padding:24px;color:#183d36}}
li{{margin:12px 0}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #ddd}}
table{{width:100%;border-collapse:collapse}}small{{color:#52635e}}</style>
<h1>Serene · Maya daycare pickup</h1>
<p>Synthetic data only · deterministic offline model/browser I/O · production domain services</p>
<p>Fatigue vs hunger vs transition difficulty. Hash chain verified. All 18 beats passed.</p>
<ol>{timeline}</ol><h2>Causal Twin after the experiment</h2>
<table><tr><th>Hypothesis</th><th>Status</th><th>Level</th></tr>{edges}</table>
<p>One scoped synthetic experiment supports transition assistance.
Competitors remain hypotheses.</p>
<h2>Dream rejection</h2><p>{escape(str(report["dream_rejections"]))}</p>
<h2>Ledger evidence</h2><table>
<tr><th>Sequence</th><th>Event</th><th>Reason</th></tr>{ledger}</table>
<p><small>Seed: {escape(report["seed"])}
· Memory commit: {report["memory_head"]}</small></p></html>"""
