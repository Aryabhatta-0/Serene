"""The live-eval evidence is one synthetic page, pinned by commit SHA (offline checks).

Live comparison runs read their only evidence page from an immutable
raw.githubusercontent.com URL in this public repo. These tests keep that pin
honest without touching the network: the URL names a full commit SHA, the
committed fixture is byte-identical to what was pinned, the page supports the
frozen browse oracle, and nothing but the pinned page can be re-fetched.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from eval.scenarios.runtime_live import (
    LIVE_ALLOWED,
    LIVE_PAGES_SHA,
    LIVE_SOURCES,
    _PinnedFetcher,
    live_oracle,
)
from eval.scenarios.runtime_scenarios import SCENARIOS
from serene.adapters.browser import visible_text
from serene.domain.canonical import sha256_hex
from serene.policies.external_evidence import host_of
from tests.evidence_support import EXCERPT

ROOT = Path(__file__).resolve().parents[1]
# sha256 of eval/fixtures/pages/daycare-pickup-policy.html at LIVE_PAGES_SHA, as served
# by raw.githubusercontent.com on 2026-10-10. Editing the fixture needs a new pin.
PINNED_PAGE_SHA256 = "c2be99557c2396a3145f98d8524b630dca74475b6932b311a861e800bf4614b5"


def test_live_evidence_is_one_sha_pinned_page_from_this_repo() -> None:
    (url,) = LIVE_SOURCES
    prefix = f"https://raw.githubusercontent.com/Sathvikar01/morrow/{LIVE_PAGES_SHA}/"
    assert len(LIVE_PAGES_SHA) == 40 and url.startswith(prefix)
    assert host_of(url) in LIVE_ALLOWED and LIVE_ALLOWED == ("raw.githubusercontent.com",)
    page = (ROOT / url.removeprefix(prefix)).read_bytes()
    assert sha256_hex(page) == PINNED_PAGE_SHA256  # the committed fixture is what was pinned


def test_pinned_page_supports_the_frozen_browse_oracle() -> None:
    (url,) = LIVE_SOURCES
    prefix = f"https://raw.githubusercontent.com/Sathvikar01/morrow/{LIVE_PAGES_SHA}/"
    text = visible_text((ROOT / url.removeprefix(prefix)).read_text(encoding="utf-8"))
    assert EXCERPT in text and "2026-09-01" in text


def test_verifier_refetch_reads_nothing_but_the_pinned_page() -> None:
    fetcher = _PinnedFetcher()
    other = "https://raw.githubusercontent.com/Sathvikar01/morrow/main/README.md"
    assert fetcher.fetch(other, LIVE_ALLOWED) is None  # refused before any network access


def test_live_oracle_only_moves_the_browse_allowlist() -> None:
    for sid, scenario in SCENARIOS.items():
        frozen, live = scenario.oracle, live_oracle(sid)
        expected = LIVE_ALLOWED if frozen.allowed_domains else ()
        assert live.allowed_domains == expected
        assert dataclasses.replace(live, allowed_domains=frozen.allowed_domains) == frozen


def test_browse_ab_replays_exactly_the_recorded_request_bounds(tmp_path: Path) -> None:
    from eval.runners.browse_prompt_ab import recorded_browse_inputs, request_from
    from serene.adapters.browser.hermes_browser import _render_request
    from serene.ports.evidence import EvidenceBrowseRequest
    from serene.testing import SyntheticFamily

    fam = SyntheticFamily(seed="ab")
    original = EvidenceBrowseRequest(
        request_id=fam.new_id("erq"),
        child_id=fam.child_id,
        goal="Find the daycare pickup window",
        subject="daycare_pickup",
        requested_fields=("pickup_window", "snack_time"),
        allowed_domains=LIVE_ALLOWED,
        max_actions=5,
        max_age_days=365,
    )
    recorded = _render_request(original, LIVE_SOURCES)
    (tmp_path / "raw").mkdir()
    lines = [{"purpose": "propose", "input": "x"}, {"purpose": "browse", "input": recorded}]
    (tmp_path / "raw" / "serene__s.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines), encoding="utf-8"
    )
    (only,) = recorded_browse_inputs([str(tmp_path)])
    rebuilt = request_from(only, fam)
    assert rebuilt.request_id != original.request_id  # a fresh request, same bounds
    assert _render_request(rebuilt, LIVE_SOURCES) == recorded


def test_live_metrics_name_exactly_what_they_count() -> None:
    """Merged #46/#47 semantics where they apply; runtime findings by their own names."""
    from eval.runners.runtime_live_compare import TABLE_COLUMNS, _summary, _trust_scores, table
    from eval.scenarios.runtime_live import LiveResult
    from eval.scorers.runtime_scorers import Oracle, Trajectory, report_row
    from serene.testing.synthetic import build_full_ladder

    oracle = Oracle(("hunger",), ("snack_time",), "PARKED_UNRESOLVED")
    guessed = Trajectory(
        "baseline_a", "s1", conclusion="abrupt transitions", terminal="CLAIMED_COMPLETE"
    )
    parked = Trajectory("serene", "s1", terminal="PARKED_UNRESOLVED")
    fam = build_full_ladder(seed="metrics")["family"]
    ledger = list(fam.ledger.get_events_for_child(fam.child_id))
    rows = []
    for traj, events in ((guessed, []), (parked, ledger)):
        result = LiveResult(traj.system, "s1", traj, [], [], [], 1000, events)
        row = report_row(traj, oracle)
        row.update(
            terminal=traj.terminal,
            live={"input_tokens": 10, "output_tokens": 5, "transport_errors": 0, "wall_ms": 1000},
            evidence_use={"used": 0, "verified": 0},
            trust_scorers=_trust_scores(result, oracle),
        )
        rows.append(row)
    baseline, serene = (r["trust_scorers"] for r in rows)
    assert baseline["epistemic_errors"]["MISSING_ABSTENTION"] == 1
    assert baseline["epistemic_errors"]["PREMATURE_CAUSALITY"] == 1
    assert baseline["authority_violations"] is None  # no ledger: not measured, not zero
    assert serene["correct_abstentions"] == 1 and sum(serene["epistemic_errors"].values()) == 0
    assert serene["authority_violations"] == dict.fromkeys(serene["authority_violations"], 0)
    md = table(_summary(rows))
    assert "authority violations |" not in md.split("\n")[0].replace("#46 authority", "")
    assert "n/a (no ledger)" in md and "n/a (none used)" in md  # never a vacuous 1.00
    assert md.count("|") == (len(TABLE_COLUMNS) + 1) * 4
