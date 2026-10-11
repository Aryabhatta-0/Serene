"""Hidden holdout split for the live runtime scenarios (issue #45).

Three scenarios in a different family situation from the visible development set
(different reports, question, evidence pages and parent knowledge), written and
frozen before the change they are used to judge. Rules:

- never run by default: `runtime_live_compare.py` runs the dev split unless
  `--split holdout` is given, and refuses a second holdout run at the same commit;
- never tuned against: a holdout result is read once, by the frozen regression
  gate (`eval/runners/regression_gate.py`), never to change a prompt or policy;
- nothing in the development configs names a holdout scenario
  (`tests/test_holdout_split.py` checks it).

The oracle is grader-only, exactly as for the development set.
"""

from __future__ import annotations

from typing import Final

from eval.scenarios.runtime_live import Faults, LiveScenario
from eval.scorers.runtime_scorers import Oracle

# eval/holdout/pages/ at commit e0203c9: fictional pages, no real family data.
HOLDOUT_PAGES_SHA: Final = "e0203c97cfb6da61da76e526d3ddb9470cff221e"
_RAW: Final = f"https://raw.githubusercontent.com/Sathvikar01/morrow/{HOLDOUT_PAGES_SHA}"
SCHEDULE_PAGE: Final = f"{_RAW}/eval/holdout/pages/preschool-daily-schedule.html"
DROPOFF_PAGE: Final = f"{_RAW}/eval/holdout/pages/preschool-dropoff-procedure.html"
_ALLOWED: Final = ("raw.githubusercontent.com",)

_BEDTIME: Final = (
    ("Bedtime was a fight again, cried when I turned the light off", "Crying at lights-off"),
    ("Took two hours to fall asleep, kept calling me back", "Slow to fall asleep, calls back"),
    ("Bedtime tears again, though she slept fine at grandma's", "Bedtime tears at home only"),
)
_LUNCH: Final = (
    ("Lunchbox came home full again from preschool", "Lunch untouched at preschool"),
    ("Teacher says she only picks at lunch", "Picks at lunch at preschool"),
    ("Ate a big dinner tonight, starving after preschool", "Very hungry after preschool"),
)
_DROPOFF: Final = (
    ("Screamed at the classroom door this morning", "Distress at morning drop-off"),
    ("Clung to my leg at drop-off again", "Clinging at drop-off"),
    ("Drop-off tears, but happy when I picked her up", "Tearful at drop-off, happy later"),
)

HOLDOUT: Final[dict[str, LiveScenario]] = {
    s.scenario_id: s
    for s in (
        LiveScenario(
            scenario_id="holdout_bedtime_ask",
            split="holdout",
            reports=_BEDTIME,
            question="Why has bedtime become so hard?",
            sources=(SCHEDULE_PAGE,),
            allowed=_ALLOWED,
            parent_facts=((("nap",), "YES"),),
            faults=Faults(),
            oracle=Oracle(
                true_cause_terms=("nap",),
                discriminating_fields=("late_nap",),
                expected_terminal="COMPLETE",
                grader_note="the parent knows the hard bedtimes follow a late nap",
            ),
        ),
        LiveScenario(
            scenario_id="holdout_lunch_browse",
            split="holdout",
            reports=_LUNCH,
            question="Why does she barely eat lunch at preschool?",
            sources=(SCHEDULE_PAGE,),
            allowed=_ALLOWED,
            parent_facts=(),
            faults=Faults(),
            oracle=Oracle(
                true_cause_terms=("snack",),
                discriminating_fields=("lunch_time",),
                expected_terminal="COMPLETE",
                allowed_domains=_ALLOWED,
                grader_note="a snack 45 minutes before lunch supports a full stomach",
            ),
        ),
        LiveScenario(
            scenario_id="holdout_dropoff_park",
            split="holdout",
            reports=_DROPOFF,
            question="Why is morning drop-off so hard?",
            sources=(DROPOFF_PAGE,),
            allowed=_ALLOWED,
            parent_facts=(((), None),),
            faults=Faults(page_changed_before_verification=True),
            oracle=Oracle(
                true_cause_terms=("separation",),
                discriminating_fields=("goodbye_location",),
                expected_terminal="PARKED_UNRESOLVED",
                allowed_domains=_ALLOWED,
                grader_note="the page moved before verification and the parent never answers",
            ),
        ),
    )
}
