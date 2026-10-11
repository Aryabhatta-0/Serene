from pathlib import Path

from serene.demo.maya import MayaDemo
from serene.domain.events import EventType
from serene.domain.values import SourceKind


def test_maya_enters_through_real_telegram_and_runtime(tmp_path: Path) -> None:
    demo = MayaDemo(tmp_path / "memory")
    assert demo.say("Synthetic Maya cried at daycare pickup") == "RECORDED_STRUCTURED"
    events = demo.family.ledger.get_events_for_child(demo.family.child_id)
    assert [e.event_type for e in events] == [
        EventType.OBSERVATION_REPORTED,
        EventType.OBSERVATION_STRUCTURED,
    ]
    assert events[0].source.kind is SourceKind.TELEGRAM
    assert demo.family.ledger.verify_hash_chain(demo.family.child_id).ok


def test_maya_competes_and_asks_for_missing_evidence(tmp_path: Path) -> None:
    demo = MayaDemo(tmp_path / "memory")
    inv = demo.open_investigation()
    state = demo.family.state()
    assert len(state.investigation_hypotheses[inv]) == 3
    assert state.investigation_phases[inv].value == "ASKING_HUMAN"
    assert demo.tap(1) == "ANSWER_RECORDED"
