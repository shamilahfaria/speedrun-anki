# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun addition.

Integration test: exercises the Rust transfer-scoring engine through the real
protobuf FFI boundary, not a Python reimplementation of it. Every assertion here
depends on compiled Rust in rslib/src/transfer/ actually running.

The point of this test is the boundary. The scoring maths is unit-tested in Rust;
what is verified here is that a collection built through the ordinary Python API
produces the scores the engine is supposed to produce when called the way the
desktop client calls it.
"""

from anki.scheduler_pb2 import CardAnswer
from tests.shared import getEmptyCol

# The proto rating enum is 0-based (AGAIN=0 .. EASY=3) while the revlog stores
# button_chosen as 1-4. Use the named constants -- passing raw ints silently
# sends the wrong button, which is exactly how the first version of this test
# managed to "pass" every card it meant to fail.
PASS = CardAnswer.GOOD
FAIL = CardAnswer.AGAIN


def _add_card(col, front: str, tags: list[str]):
    note = col.newNote()
    note["Front"] = front
    note["Back"] = "answer"
    note.tags = tags
    col.addNote(note)
    return note.cards()[0]


def _answer(col, card, ease: int):
    """Answer a specific card, going through the real scheduler."""
    # build_answer reads card.timer_started to record time taken.
    card.start_timer()
    states = col._backend.get_scheduling_states(card.id)
    col.sched.answer_card(
        col.sched.build_answer(card=card, states=states, rating=ease)
    )


def _study(col, front_prefix: str, tags: list[str], count: int, passes: int):
    """Create `count` cards and answer each once; the first `passes` pass."""
    for i in range(count):
        card = _add_card(col, f"{front_prefix}-{i}", list(tags))
        _answer(col, card, PASS if i < passes else FAIL)


def _scores(col, min_reviews: int = 20, min_cards: int = 5):
    return col._backend.compute_transfer_scores(
        since_millis=0, min_reviews=min_reviews, min_cards=min_cards
    )


def test_give_up_rule_refuses_thin_evidence():
    """The engine must decline to score, not score with a wide interval."""
    col = getEmptyCol()
    _study(col, "recall", ["speedrun::topic::biochem"], count=3, passes=3)

    out = _scores(col)
    assert len(out.topics) == 1
    memory = out.topics[0].memory
    assert not memory.sufficient
    assert memory.observations == 3
    assert memory.needed_observations == 20
    # A refusal must not carry a renderable number.
    assert memory.point == 0.0
    col.close()


def test_memory_and_performance_are_scored_separately():
    """The product thesis, end to end: strong recall, weak transfer."""
    col = getEmptyCol()
    topic = "speedrun::topic::biochem"
    # 25 plain recall cards, 24 passed -> memory 96%
    _study(col, "recall", [topic], count=25, passes=24)
    # 25 transfer probes, 12 passed -> performance 48%
    _study(col, "probe", [topic, "speedrun::probe"], count=25, passes=12)

    out = _scores(col)
    assert len(out.topics) == 1
    t = out.topics[0]
    assert t.topic == "biochem"

    assert t.memory.sufficient and t.performance.sufficient
    assert abs(t.memory.point - 0.96) < 1e-9
    assert abs(t.performance.point - 0.48) < 1e-9
    assert t.memory.observations == 25
    assert t.performance.observations == 25

    # The gap is the headline the product exists to show.
    assert t.gap_valid
    assert abs(t.gap - 0.48) < 1e-9

    # Wilson interval must bracket the point estimate without claiming certainty.
    assert t.performance.lower < t.performance.point < t.performance.upper
    assert 0.0 <= t.performance.lower and t.performance.upper <= 1.0

    # Readiness draws on probes only.
    assert out.readiness.sufficient
    assert out.readiness.observations == 25
    col.close()


def test_untagged_reviews_are_not_counted():
    """Reviews that cannot be attributed to exam content must not inflate scores."""
    col = getEmptyCol()
    _study(col, "probe", ["speedrun::topic::biochem", "speedrun::probe"], 25, 15)
    # 40 probe reviews with no topic tag at all.
    _study(col, "orphan", ["speedrun::probe"], 40, 40)

    out = _scores(col)
    assert out.readiness.observations == 25
    assert len(out.topics) == 1
    col.close()


def test_manual_reschedules_are_excluded():
    """Only graded answers are evidence; set-due-date entries are not."""
    col = getEmptyCol()
    topic = "speedrun::topic::biochem"
    _study(col, "recall", [topic], count=25, passes=25)

    before = _scores(col).topics[0].memory.observations

    # set_due_date writes revlog rows of kind Manual/Rescheduled with ease 0.
    cids = col.find_cards(f'tag:{topic}')
    col.sched.set_due_date(cids, "5")

    after = _scores(col).topics[0].memory
    assert after.observations == before, (
        "rescheduling is not an answer and must not count as evidence"
    )
    assert after.sufficient
    col.close()
