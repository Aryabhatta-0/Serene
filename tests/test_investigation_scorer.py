"""Investigation Success scorer (#49), runtime-scorers/2: what a question is worth must not
depend on what the system called its field.

runtime-scorers/1 matched the system's field labels against the grader's
`Oracle.discriminating_fields`; the first test pins that defect. runtime-scorers/2 reads
only the system's own recorded acquisitions: whether the predictions stated when a
request was made tell competing hypotheses apart, whether its outcome is decisive, and
whether a question repeats one already asked or information already obtained.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from eval.baselines.runtime_baselines import baseline_a
from eval.scenarios.runtime_scenarios import QUESTION, REPORTS, SCENARIOS
from eval.scorers.runtime_scorers import (
    Acquisition,
    Oracle,
    Trajectory,
    report_row,
    score_investigation,
    score_investigation_v1,
    told_apart,
)
from serene.adapters.hermes import ScriptedHermesTransport
from serene.adapters.hermes.scripted import raw_response

ORACLE = Oracle(
    true_cause_terms=("transition",),
    discriminating_fields=("calm_after_snack",),  # grader tag (read by v1 only)
    expected_terminal="COMPLETE",
)
HYPS = ("hyp_transition", "hyp_hunger")
SPLIT = (("hyp_hunger", "YES"), ("hyp_transition", "NO"))


def ask(
    fields: tuple[str, ...] = ("calm_after_snack",),
    question: str = "Was pickup calmer on days with a snack just before?",
    outcome: str = "NO",
    competing: tuple[str, ...] = HYPS,
    predictions: tuple[tuple[str, str], ...] = SPLIT,
) -> Acquisition:
    return Acquisition("ASK_PARENT", fields, question, competing, predictions, outcome)


def browse(
    fields: tuple[str, ...] = ("pickup_window",),
    outcome: str = "VERIFIED",
    predictions: tuple[tuple[str, str], ...] = SPLIT,
) -> Acquisition:
    return Acquisition("BROWSE", fields, "", HYPS, predictions, outcome)


def run(*acquisitions: Acquisition, terminal: str = "COMPLETE") -> Trajectory:
    return Trajectory(
        system="unit",
        scenario_id="unit",
        questions=tuple(a.fields for a in acquisitions if a.mode == "ASK_PARENT"),
        acquisitions=acquisitions,
        hypotheses_retained=("The abrupt transition at pickup",),
        terminal=terminal,
    )


def dims(t: Trajectory, oracle: Oracle = ORACLE) -> dict[str, float]:
    return score_investigation(t, oracle).dimensions


# ---------------------------------------------------------------- the v1 defect
def test_v1_scores_the_same_question_differently_under_another_field_label() -> None:
    """Confirmed evaluation bug: one question, one answer, two labels, two scores."""
    graders_label = run(ask(fields=("calm_after_snack",)))
    own_label = run(ask(fields=("snack_before_pickup_effect",)))
    v1_a = score_investigation_v1(graders_label, ORACLE)
    v1_b = score_investigation_v1(own_label, ORACLE)
    assert v1_a.dimensions["high_value"] == 1.0 and v1_a.dimensions["burden"] == 1.0
    assert v1_b.dimensions["high_value"] == 0.0 and v1_b.dimensions["burden"] == 0.0
    assert v1_a.value != v1_b.value
    # runtime-scorers/2: the label is irrelevant.
    assert score_investigation(graders_label, ORACLE) == score_investigation(own_label, ORACLE)
    assert dims(own_label) == {
        "retention": 1.0,
        "high_value": 1.0,
        "resolution": 1.0,
        "burden": 1.0,
    }


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    labels=st.lists(
        st.from_regex(r"[a-z][a-z_]{0,20}", fullmatch=True), min_size=3, max_size=3, unique=True
    ),
    renamed=st.lists(
        st.from_regex(r"[a-z][a-z_]{0,20}", fullmatch=True), min_size=3, max_size=3, unique=True
    ),
    outcomes=st.lists(
        st.sampled_from(["YES", "NO", "UNSURE", "NO_RESPONSE"]), min_size=3, max_size=3
    ),
)
def test_renaming_fields_never_changes_the_v2_score(
    labels: list[str], renamed: list[str], outcomes: list[str]
) -> None:
    def trajectory(names: list[str]) -> Trajectory:
        return run(
            ask(fields=(names[0],), question="First?", outcome=outcomes[0]),
            browse(fields=(names[1],), outcome="REJECTED"),
            ask(fields=(names[0],), question="First, again?", outcome=outcomes[1]),
            ask(fields=(names[2],), question="Third?", outcome=outcomes[2], predictions=()),
        )

    assert score_investigation(trajectory(labels), ORACLE) == score_investigation(
        trajectory(renamed), ORACLE
    )


def test_v2_never_reads_the_graders_field_tags() -> None:
    t = run(ask(fields=("anything",)), browse())
    for tags in ((), ("calm_after_snack",), ("anything",), ("x", "y")):
        oracle = dataclasses.replace(ORACLE, discriminating_fields=tags)
        assert score_investigation(t, oracle) == score_investigation(t, ORACLE)


# ---------------------------------------------------------------- discrimination
def test_discriminating_vs_non_discriminating_questions() -> None:
    assert told_apart(ask()) == {frozenset(HYPS)}
    same = (("hyp_hunger", "YES"), ("hyp_transition", "YES"))
    one = (("hyp_hunger", "YES"),)
    contradictory = (("hyp_hunger", "YES"), ("hyp_hunger", "NO"), ("hyp_transition", "NO"))
    stranger = (("hyp_hunger", "YES"), ("hyp_formed_later", "NO"))
    for predictions in ((), same, one, contradictory, stranger):
        q = ask(predictions=predictions)
        assert told_apart(q) == frozenset(), predictions
        score = score_investigation(run(q), ORACLE)
        assert score.dimensions["burden"] == 0.0
        assert score.dimensions["high_value"] == 0.0
        assert "NON_DISCRIMINATING:1" in score.notes


def test_predictions_about_hypotheses_formed_after_the_request_do_not_count() -> None:
    """No hindsight: only hypotheses live when the request was made can be told apart."""
    late = ask(competing=("hyp_hunger",), predictions=SPLIT)
    assert told_apart(late) == frozenset()
    assert dims(run(late))["high_value"] == 0.0


# ---------------------------------------------------------------- obtained evidence
def test_high_value_needs_a_decisive_outcome_on_a_discriminating_request() -> None:
    for outcome in ("YES", "NO"):
        assert dims(run(ask(outcome=outcome)))["high_value"] == 1.0
    for outcome in ("UNSURE", "NO_RESPONSE", "ANSWERED", "REJECTED"):
        assert dims(run(ask(outcome=outcome)))["high_value"] == 0.0, outcome
    assert dims(run(browse(outcome="VERIFIED")))["high_value"] == 1.0
    for outcome in ("REJECTED", "UNVERIFIED", "NOT_ACQUIRED"):
        assert dims(run(browse(outcome=outcome)))["high_value"] == 0.0, outcome
    # verified, but nothing it could tell apart
    assert dims(run(browse(predictions=())))["high_value"] == 0.0


def test_a_browse_never_counts_as_parent_burden() -> None:
    assert dims(run(browse(), browse(fields=("menu",), predictions=())))["burden"] == 1.0


# ---------------------------------------------------------------- burden
def test_repeating_a_question_is_burden_whatever_its_labels() -> None:
    first = ask(outcome="UNSURE")
    same_text_new_label = ask(fields=("snack_effect",), outcome="UNSURE")
    same_label_new_text = ask(question="Did a snack help at pickup?", outcome="UNSURE")
    for again in (same_text_new_label, same_label_new_text):
        score = score_investigation(run(first, again), ORACLE)
        assert score.dimensions["burden"] == 0.5
        assert "REPEATED:1" in score.notes


def test_asking_for_information_already_obtained_is_burden() -> None:
    page = browse(fields=("pickup_window",))
    q = ask(fields=("pickup_window",), question="When is pickup?", outcome="YES")
    score = score_investigation(run(page, q), ORACLE)
    assert score.dimensions["burden"] == 0.0 and "REPEATED:1" in score.notes
    # ...but not when the page was rejected: then asking the parent is the fallback.
    rejected = browse(fields=("pickup_window",), outcome="REJECTED")
    assert dims(run(rejected, q))["burden"] == 1.0


def test_a_question_that_only_tells_apart_what_is_already_told_apart_is_burden() -> None:
    """Semantic repetition without any shared wording or label."""
    settled = ask(outcome="NO")
    reworded = ask(fields=("tired_at_four",), question="Is he tired by four?", outcome="YES")
    score = score_investigation(run(settled, reworded), ORACLE)
    assert score.dimensions["burden"] == 0.5 and "ALREADY_TOLD_APART:1" in score.notes
    # An undecided first question leaves the pair open, so the second one is needed.
    assert dims(run(ask(outcome="UNSURE"), reworded))["burden"] == 1.0


def test_an_acquisition_record_that_misses_questions_fails_closed() -> None:
    t = dataclasses.replace(run(ask()), acquisitions=())
    score = score_investigation(t, ORACLE)
    assert score.dimensions["burden"] == 0.0 and score.dimensions["high_value"] == 0.0
    assert "ACQUISITIONS_INCOMPLETE" in score.notes


# ---------------------------------------------------------------- determinism
def test_scoring_is_deterministic_and_survives_a_json_round_trip() -> None:
    t = run(ask(outcome="UNSURE"), browse(), ask(fields=("nap",), question="Nap?"))
    first = json.dumps(report_row(t, ORACLE), sort_keys=True)
    assert first == json.dumps(report_row(t, ORACLE), sort_keys=True)
    restored = Trajectory.from_json(t.to_json())
    assert restored == t
    assert json.dumps(report_row(restored, ORACLE), sort_keys=True) == first


# ---------------------------------------------------------------- reducers
def test_serene_ledger_records_what_v2_needs() -> None:
    t = SCENARIOS["ask_discriminates"].run_serene()
    (snack,) = t.acquisitions
    assert snack.mode == "ASK_PARENT" and snack.outcome == "NO"
    assert len(snack.competing) == 2 and told_apart(snack) == {frozenset(snack.competing)}
    assert Trajectory.from_json(t.to_json()) == t
    assert SCENARIOS["parent_silent"].run_serene().acquisitions[0].outcome == "NO_RESPONSE"
    page = SCENARIOS["browse_unsupported_page"].run_serene().acquisitions[0]
    assert page.mode == "BROWSE" and page.outcome == "REJECTED"
    assert SCENARIOS["browse_verified"].run_serene().acquisitions[0].outcome == "VERIFIED"
    assert SCENARIOS["planner_down"].run_serene().acquisitions == ()


def test_a_baseline_states_no_predictions_so_its_questions_claim_no_discrimination() -> None:
    transport = ScriptedHermesTransport()
    say: Any = {"action": "ask", "question": "Calmer after a snack?", "fields": ["snack"]}
    transport.push(
        "propose",
        raw_response(json.dumps(say)),
        raw_response(json.dumps({"action": "answer", "cause": "Transition", "hypotheses": []})),
    )
    t = baseline_a(transport).run(
        SCENARIOS["ask_discriminates"],
        tuple(text for text, _ in REPORTS),
        QUESTION,
        seed="unit",
        parent=lambda question, fields: "NO",
    )
    (q,) = t.acquisitions
    assert (q.mode, q.question, q.outcome, q.predictions) == (
        "ASK_PARENT",
        "Calmer after a snack?",
        "NO",
        (),
    )
    assert "NON_DISCRIMINATING:1" in score_investigation(t, ORACLE).notes
