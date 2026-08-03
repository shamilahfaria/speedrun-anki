# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Speedrun addition.

Undo and no-corruption proof for the Rust transfer-scoring engine.

TransferService is read-only by construction, which is a *reason* to expect it
is safe -- it is not evidence that it is. This file supplies the evidence, by
measuring the things a write would disturb:

  * the undo queue (name and step counter) across a scoring call
  * undo itself, exercised after scoring, checked to return the right op
  * the scores themselves, which must track an undone review down
  * a full backend database check after scoring
  * a byte-level digest of every row of every table, plus col.mod and col.usn

The last test in this file is a control. It runs the same no-mutation
machinery around an operation that genuinely writes, and asserts the machinery
notices. Without it, every assertion above could be passing because it measures
nothing. A proof whose instrument is never shown to deflect is not a proof.
"""

from __future__ import annotations

import hashlib

from anki.collection import Collection
from anki.scheduler_pb2 import CardAnswer
from tests.shared import getEmptyCol

PASS = CardAnswer.GOOD
FAIL = CardAnswer.AGAIN

TOPIC = "speedrun::topic::biochem"

# The undo name the backend gives a graded answer. Asserted rather than
# accepted: undo() returning *something* is not the same as undo() reverting
# the review that was just made.
ANSWER_CARD = "Answer Card"


def _add_card(col: Collection, front: str, tags: list[str]):
    note = col.newNote()
    note["Front"] = front
    note["Back"] = "answer"
    note.tags = tags
    col.addNote(note)
    return note.cards()[0]


def _answer(col: Collection, card, ease: int) -> None:
    card.start_timer()
    states = col._backend.get_scheduling_states(card.id)
    col.sched.answer_card(
        col.sched.build_answer(card=card, states=states, rating=ease)
    )


def _study(col: Collection, count: int, passes: int, tags: list[str] | None = None):
    """Add all cards, then answer them all.

    Order matters for this file specifically. Interleaving adds and answers
    leaves an undo stack of add/answer/add/answer, so two consecutive undos
    would revert a note rather than a second review. Adding first puts `count`
    consecutive "Answer Card" entries on top of the stack, which is what the
    multi-undo assertions below need.
    """
    tags = tags if tags is not None else [TOPIC]
    cards = [_add_card(col, f"card-{i}", list(tags)) for i in range(count)]
    for i, card in enumerate(cards):
        _answer(col, card, PASS if i < passes else FAIL)
    return cards


def _scores(col: Collection, min_reviews: int = 20, min_cards: int = 5):
    return col._backend.compute_transfer_scores(
        since_millis=0, min_reviews=min_reviews, min_cards=min_cards
    )


def _observations(col: Collection) -> int:
    out = _scores(col)
    assert len(out.topics) == 1
    return out.topics[0].memory.observations


# -- no-mutation instrument ------------------------------------------------
#
# Used by the read-only tests and by the control test at the bottom.


def _user_tables(col: Collection) -> list[str]:
    return sorted(
        str(name)
        for name in col.db.list(
            "select name from sqlite_master where type='table'"
            " and name not like 'sqlite_%'"
        )
    )


def _snapshot(col: Collection) -> dict[str, object]:
    """Everything a write could plausibly disturb, in one comparable value."""
    digest = hashlib.sha256()
    per_table = {}
    for table in _user_tables(col):
        h = hashlib.sha256()
        # Sorted in Python, not SQL. `config` is a WITHOUT ROWID table, so
        # `order by rowid` raises there, and the tables have no single column
        # name in common to order by instead. Sorting the rendered rows makes
        # the digest independent of storage order, which is what we want: this
        # must detect a changed *value*, not a vacuumed page layout.
        for row in sorted(col.db.all(f"select * from {table}"), key=repr):
            h.update(repr(row).encode())
        per_table[table] = h.hexdigest()
        digest.update(table.encode())
        digest.update(h.digest())
    return {
        "tables": per_table,
        "digest": digest.hexdigest(),
        "mod": col.mod,
        "usn": col.db.scalar("select usn from col"),
        "scm": col.db.scalar("select scm from col"),
        "undo": col.undo_status().undo,
        "redo": col.undo_status().redo,
        "last_step": col.undo_status().last_step,
    }


def _differences(before: dict, after: dict) -> list[str]:
    diffs = []
    for key in ("mod", "usn", "scm", "undo", "redo", "last_step", "digest"):
        if before[key] != after[key]:
            diffs.append(f"{key}: {before[key]!r} -> {after[key]!r}")
    for table, digest in before["tables"].items():
        if after["tables"].get(table) != digest:
            diffs.append(f"table {table} changed")
    return diffs


# -- undo queue ------------------------------------------------------------


def test_scoring_does_not_push_an_undo_entry():
    """Scoring must not consume a slot in the user's undo history.

    Anki's undo queue is bounded. An op that silently pushes an entry every
    time a report is refreshed would evict the user's real work -- the review
    they wanted back would be gone, with nothing appearing to have gone wrong.
    """
    col = getEmptyCol()
    _study(col, count=25, passes=25)

    before = col.undo_status()
    assert before.undo == ANSWER_CARD, "precondition: an answer is on the stack"

    for _ in range(5):
        _scores(col)

    after = col.undo_status()
    assert after.undo == before.undo
    assert after.redo == before.redo
    assert after.last_step == before.last_step, (
        "compute_transfer_scores added an undo step; the undo queue must be "
        "untouched by a read"
    )
    col.close()


def test_undo_after_scoring_returns_the_answer_op():
    """Undo must still work, and must revert the review -- not just succeed."""
    col = getEmptyCol()
    cards = _study(col, count=25, passes=25)
    last = cards[-1]

    _scores(col)

    reps_before = col.get_card(last.id).reps
    revlog_before = col.db.scalar("select count() from revlog")

    out = col.undo()
    assert out.operation == ANSWER_CARD, (
        f"undo returned {out.operation!r}, expected {ANSWER_CARD!r}"
    )
    assert out.changes.card, "undo of an answer must report a card change"
    assert out.changes.study_queues, "undo of an answer must refresh the queues"

    assert col.get_card(last.id).reps == reps_before - 1
    assert col.db.scalar("select count() from revlog") == revlog_before - 1
    # Redo must be offered afterwards, i.e. the undo entry became a redo entry
    # rather than being discarded.
    assert col.undo_status().redo == ANSWER_CARD
    col.close()


def test_scores_track_undone_and_redone_reviews():
    """A withdrawn review is withdrawn evidence.

    If the engine kept a cache or read a stale snapshot, this is where it would
    show: the number would not move when the review behind it was taken back.
    """
    col = getEmptyCol()
    _study(col, count=25, passes=25)

    assert _observations(col) == 25

    for expected in (24, 23, 22):
        assert col.undo().operation == ANSWER_CARD
        assert _observations(col) == expected, (
            "observation count did not drop after an answer was undone"
        )

    # Undo far enough and the engine must fall back to refusing to score,
    # rather than reporting a number from thin evidence.
    for _ in range(3):
        col.undo()
    out = _scores(col)
    memory = out.topics[0].memory
    assert memory.observations == 19
    assert not memory.sufficient
    assert memory.point == 0.0

    # Redo puts the evidence back.
    for _ in range(6):
        assert col.redo().operation == ANSWER_CARD
    assert _observations(col) == 25
    assert _scores(col).topics[0].memory.sufficient
    col.close()


def test_undo_redo_interleaved_with_scoring_stays_consistent():
    """Hammer the two together; the scores must agree with the revlog every time."""
    col = getEmptyCol()
    _study(col, count=30, passes=30)

    for _ in range(10):
        _scores(col)
        col.undo()
        _scores(col)
        col.redo()
        _scores(col)

    graded = col.db.scalar(
        "select count() from revlog where ease > 0 and type not in (4, 5)"
    )
    assert graded == 30
    assert _observations(col) == graded
    assert not list(col._backend.check_database())
    col.close()


# -- corruption ------------------------------------------------------------


def test_database_check_is_clean_after_scoring():
    """The backend's own integrity check, run after the engine has read."""
    col = getEmptyCol()
    _study(col, count=25, passes=20)
    _study(col, count=25, passes=12, tags=[TOPIC, "speedrun::probe"])

    for _ in range(10):
        _scores(col)

    problems = list(col._backend.check_database())
    assert problems == [], f"database check reported problems: {problems}"

    # sqlite's own structural check, which check_database does not run.
    assert col.db.scalar("pragma integrity_check") == "ok"
    assert col.db.all("pragma foreign_key_check") == []

    # And the higher-level Python wrapper agrees.
    _, ok = col.fix_integrity()
    assert ok
    col.close()


def test_scoring_leaves_every_byte_of_the_collection_alone():
    """The read-only claim, measured rather than asserted.

    Digest of every row of every table, plus mod time, USN and schema time.
    Nothing may move.
    """
    col = getEmptyCol()
    _study(col, count=25, passes=20)
    _study(col, count=25, passes=12, tags=[TOPIC, "speedrun::probe"])

    before = _snapshot(col)
    for _ in range(10):
        out = _scores(col)
    # Guard against the vacuous version of this test: the engine must actually
    # have produced a report while we were watching.
    assert out.topics and out.topics[0].memory.sufficient
    after = _snapshot(col)

    assert _differences(before, after) == [], (
        f"compute_transfer_scores modified the collection: "
        f"{_differences(before, after)}"
    )
    # mod is the field Anki syncs on; call it out by name so a failure reads
    # clearly rather than as an opaque digest mismatch.
    assert after["mod"] == before["mod"]
    assert after["usn"] == before["usn"]
    col.close()


# -- control ---------------------------------------------------------------


def test_the_no_mutation_instrument_actually_deflects():
    """Control for every assertion above.

    Runs the same snapshot/undo-queue checks around operations that really do
    write, and requires that they be detected. If this test ever passes while
    reporting no differences, the tests above are measuring nothing and their
    green is meaningless.
    """
    col = getEmptyCol()
    _study(col, count=25, passes=25)

    # 1. A write op must move the digest, the mod time and the undo queue.
    before = _snapshot(col)
    col.set_config("speedrunCanary", 1)
    after = _snapshot(col)
    diffs = _differences(before, after)
    assert diffs, "snapshot did not notice a config write"
    assert any(d.startswith("mod:") for d in diffs), f"mod not tracked: {diffs}"
    assert any(d.startswith("digest:") for d in diffs), f"digest not tracked: {diffs}"
    assert any(d.startswith("last_step:") for d in diffs), (
        f"undo step counter not tracked: {diffs}"
    )

    # 2. A card write must move the digest too -- config lives in its own
    #    table, so on its own it would not prove row-level sensitivity.
    before = _snapshot(col)
    col.sched.set_due_date(col.find_cards(f"tag:{TOPIC}")[:1], "5")
    after = _snapshot(col)
    diffs = _differences(before, after)
    assert any(d == "table cards changed" for d in diffs), (
        f"snapshot did not notice a card write: {diffs}"
    )

    # 3. The observation counter must be able to go down, or the
    #    undone-review assertions prove nothing.
    #
    #    The set_due_date above is now the top of the undo stack, so it has to
    #    come off first. Naming both ops rather than undoing blindly: an undo
    #    that happens to revert something else would drop the count too, and
    #    would prove nothing about reviews.
    assert col.undo().operation == "Set Due Date"
    obs_before = _observations(col)
    assert col.undo().operation == ANSWER_CARD
    assert _observations(col) == obs_before - 1
    col.close()
