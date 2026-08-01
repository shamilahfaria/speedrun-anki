# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun addition.

Guards the one property the display layer can silently destroy: when the engine
declines to score something, the view must say so. Rendering a refusal as 0%, or
as an empty cell that reads like a poor result, would reintroduce the exact
dishonesty the engine refuses to commit -- in the last hundred lines of the
stack, where nobody is looking.

These assert on rendered output, not on the engine, because the engine's own
behaviour is already covered by rslib unit tests and pylib/tests/test_transfer.py.
"""

from __future__ import annotations

import os
import tempfile

from anki.collection import Collection
from anki.scheduler_pb2 import CardAnswer

from aqt.transfer import _render

TOPIC = "speedrun::topic::biochem"
PROBE = "speedrun::probe"


def _collection() -> Collection:
    return Collection(os.path.join(tempfile.mkdtemp(), "t.anki2"))


def _study(col: Collection, prefix: str, tags: list[str], count: int, passes: int):
    for i in range(count):
        note = col.newNote()
        note["Front"] = f"{prefix}-{i}"
        note["Back"] = "answer"
        note.tags = list(tags)
        col.addNote(note)
        card = note.cards()[0]
        card.start_timer()
        states = col._backend.get_scheduling_states(card.id)
        col.sched.answer_card(
            col.sched.build_answer(
                card=card,
                states=states,
                # 0-based proto enum; raw ints send the wrong button.
                rating=CardAnswer.GOOD if i < passes else CardAnswer.AGAIN,
            )
        )


def _scores(col: Collection):
    return col._backend.compute_transfer_scores(
        since_millis=0, min_reviews=20, min_cards=5
    )


def test_refusal_is_shown_as_a_refusal():
    col = _collection()
    _study(col, "recall", [TOPIC], count=3, passes=3)

    html = _render(_scores(col))

    assert "not enough evidence" in html.lower()
    # The shortfall must be named, so the reader knows what would fix it.
    assert "more reviews" in html
    # The anti-requirement: a declined score must never appear as a number.
    assert ">0%<" not in html
    col.close()


def test_three_scores_render_distinctly():
    col = _collection()
    _study(col, "recall", [TOPIC], count=25, passes=24)  # memory 96%
    _study(col, "probe", [TOPIC, PROBE], count=25, passes=12)  # performance 48%

    scores = _scores(col)
    html = _render(scores)

    assert "96%" in html, "memory score missing"
    assert "48%" in html, "performance score missing"
    assert "+48 pts" in html, "the gap is the headline and must be shown"
    assert scores.readiness.sufficient
    col.close()


def test_empty_collection_explains_itself():
    """No data must read as an instruction, not as a score of zero."""
    col = _collection()
    html = _render(_scores(col))
    assert "speedrun::topic::" in html
    assert ">0%<" not in html
    col.close()
