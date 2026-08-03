# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Speedrun addition.
#
# Crash-resilience harness: kill the app mid-review, N times, and require zero
# corrupted collections.
#
# The kill is SIGKILL, not SIGTERM. SIGTERM would let Python run its atexit
# handlers and close the collection cleanly, which would test the shutdown path
# and prove nothing about durability. SIGKILL gives the process no chance to
# flush, commit, or unlock -- the collection is left exactly as SQLite's
# on-disk state happened to be at that instant, which is the situation this
# harness exists to survive.
#
# One collection is carried across all trials rather than a fresh one per
# trial, so damage has somewhere to accumulate. A per-trial collection would
# reset the experiment each time and hide exactly the failure mode worth
# looking for.
#
# Usage:
#   PYTHONPATH=$PWD/out/pylib out/pyenv/bin/python tools/crash_test.py [--trials 20]

from __future__ import annotations

import argparse
import concurrent.futures
import os
import random
import signal
import subprocess
import sys
import tempfile
import time

from anki.collection import Collection

TOPICS = ["biochem", "orgo", "physics", "psych", "socio"]


# -- child ----------------------------------------------------------------


def child_main(path: str, seed: int) -> int:
    """Open the collection and review continuously until killed.

    Every iteration adds a note and immediately answers its card, so the
    process is writing essentially all of the time. That is deliberate: a loop
    that idled between writes would mostly be killed while idle, and a harness
    that mostly kills an idle process is not testing crash-during-write.
    """
    rng = random.Random(seed)
    col = Collection(path)

    # Announce readiness only once the first review is committed, so the parent
    # never starts its kill timer against a process that has not begun work.
    first = True
    i = 0
    while True:
        i += 1
        topic = TOPICS[i % len(TOPICS)]
        tags = [f"speedrun::topic::{topic}"]
        if i % 3 == 0:
            tags.append("speedrun::probe")

        note = col.newNote()
        note["Front"] = f"crash-{seed}-{i}"
        note["Back"] = "answer"
        note.tags = tags
        col.addNote(note)

        card = note.cards()[0]
        card.start_timer()
        states = col._backend.get_scheduling_states(card.id)
        rating = 1 if rng.random() < 0.35 else 3  # AGAIN / GOOD
        col.sched.answer_card(
            col.sched.build_answer(card=card, states=states, rating=rating)
        )

        if first:
            sys.stdout.write("READY\n")
            sys.stdout.flush()
            first = False


# -- parent ---------------------------------------------------------------


def build_collection(path: str) -> int:
    """Seed enough graded reviews that scoring is above the give-up threshold."""
    col = Collection(path)
    for i in range(40):
        topic = TOPICS[i % len(TOPICS)]
        tags = [f"speedrun::topic::{topic}"]
        if i % 3 == 0:
            tags.append("speedrun::probe")
        note = col.newNote()
        note["Front"] = f"seed-{i}"
        note["Back"] = "answer"
        note.tags = tags
        col.addNote(note)
        card = note.cards()[0]
        card.start_timer()
        states = col._backend.get_scheduling_states(card.id)
        col.sched.answer_card(
            col.sched.build_answer(card=card, states=states, rating=3)
        )
    n = col.db.scalar("select count() from revlog")
    col.close()
    return n


def inspect(path: str) -> dict:
    """Reopen after a kill and check every way the collection could be broken."""
    result = {
        "opened": False,
        "integrity": None,
        "fk": None,
        "check_db": None,
        "scores": None,
        "reviews": None,
        "error": None,
    }
    col = None
    try:
        col = Collection(path)
        result["opened"] = True

        # SQLite's own structural check: page/index/btree consistency.
        result["integrity"] = col.db.scalar("pragma integrity_check")
        result["fk"] = col.db.all("pragma foreign_key_check")

        # Anki's semantic check: orphaned cards, missing notetypes, bad decks.
        result["check_db"] = list(col._backend.check_database())

        result["reviews"] = col.db.scalar("select count() from revlog")

        # The Speedrun read path must still produce a report.
        out = col._backend.compute_transfer_scores(
            since_millis=0, min_reviews=20, min_cards=5
        )
        result["scores"] = (len(out.topics), out.readiness.observations)
    except Exception as err:  # noqa: BLE001 - any failure here is a finding
        result["error"] = f"{type(err).__name__}: {err}"
    finally:
        if col is not None and col.db is not None:
            try:
                col.close()
            except Exception as err:  # noqa: BLE001
                result["error"] = result["error"] or f"close: {err}"
    return result


def inspect_off_main_thread(path: str) -> dict:
    """Run inspect() on a worker thread.

    Not cosmetic. anki._backend._run_command prints a warning and a full stack
    trace whenever a backend call blocks the *main* thread for over 200ms, and
    check_database on a collection that has grown across twenty trials takes
    around 450ms. Left on the main thread, that watchdog interleaves multi-line
    tracebacks with the results table and makes the output unreadable.

    Moving the work to a worker thread is what a GUI would do anyway, and it
    does not weaken a single check -- the same queries run against the same
    file, on a thread the watchdog is not asked to police.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(inspect, path).result()


def verdict(res: dict, reviews_before: int) -> tuple[bool, str]:
    if res["error"]:
        return False, res["error"]
    if not res["opened"]:
        return False, "could not reopen"
    if res["integrity"] != "ok":
        return False, f"integrity_check={res['integrity']!r}"
    if res["fk"]:
        return False, f"foreign_key_check={res['fk']!r}"
    if res["check_db"]:
        return False, f"check_database={res['check_db']!r}"
    if res["scores"] is None:
        return False, "scores not computable"
    if res["reviews"] < reviews_before:
        # Committed reviews must survive. Losing the transaction that was
        # in flight at the instant of the kill is correct; losing reviews
        # committed before it is data loss.
        return False, f"lost committed reviews: {reviews_before} -> {res['reviews']}"
    return True, "ok"


def run(trials: int, seed: int, min_delay: float, max_delay: float) -> int:
    rng = random.Random(seed)
    workdir = tempfile.mkdtemp(prefix="speedrun-crash-")
    path = os.path.join(workdir, "crash.anki2")

    print(f"collection: {path}")
    reviews = build_collection(path)
    print(f"seeded {reviews} graded reviews\n")

    header = (
        f"{'#':>3}  {'pid':>7}  {'kill@ms':>8}  {'exit':>6}  {'reviews':>8}  "
        f"{'new':>5}  {'integ':>6}  {'dbchk':>6}  {'score':>7}  verdict"
    )
    print(header)
    print("-" * len(header))

    failures = []
    for trial in range(1, trials + 1):
        before = reviews
        delay = rng.uniform(min_delay, max_delay)

        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--child", path,
             "--seed", str(rng.randrange(1 << 30))],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for the child to commit its first review before timing the kill.
        ready_line = proc.stdout.readline()
        if ready_line.strip() != "READY":
            proc.kill()
            out, err = proc.communicate()
            failures.append(trial)
            print(f"{trial:>3}  {proc.pid:>7}  {'-':>8}  {'-':>6}  {'-':>8}  "
                  f"{'-':>5}  {'-':>6}  {'-':>6}  {'-':>7}  "
                  f"CHILD NEVER STARTED: {err.strip()[:120]}")
            continue

        time.sleep(delay)

        # SIGKILL: uncatchable, unmaskable. No cleanup runs.
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()

        killed_cleanly = proc.returncode == -signal.SIGKILL

        res = inspect_off_main_thread(path)
        ok, why = verdict(res, before)
        if not killed_cleanly:
            ok, why = False, f"exit {proc.returncode} was not SIGKILL"

        after = res["reviews"] if res["reviews"] is not None else -1
        if after >= 0:
            reviews = after

        integ = "ok" if res["integrity"] == "ok" else "BAD"
        dbchk = "clean" if res["check_db"] == [] else "BAD"
        score = "ok" if res["scores"] else "BAD"
        exit_s = f"-{signal.SIGKILL}" if killed_cleanly else str(proc.returncode)

        print(f"{trial:>3}  {proc.pid:>7}  {delay * 1000:>8.0f}  {exit_s:>6}  "
              f"{after:>8}  {after - before:>5}  {integ:>6}  {dbchk:>6}  "
              f"{score:>7}  {'PASS' if ok else 'FAIL: ' + why}")

        if not ok:
            failures.append(trial)

    print()
    print(f"trials: {trials}   corrupted: {len(failures)}")
    if failures:
        print(f"FAIL -- corruption in trials {failures}")
        return 1
    print(f"PASS -- {trials}/{trials} unclean SIGKILLs mid-review, "
          f"zero corrupted collections, scores computable after every one")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--child", metavar="COL_PATH",
                    help="internal: run the reviewing child process")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20250803)
    ap.add_argument("--min-delay", type=float, default=0.02,
                    help="earliest kill, seconds after first committed review")
    ap.add_argument("--max-delay", type=float, default=0.40)
    args = ap.parse_args()

    if args.child:
        return child_main(args.child, args.seed)
    return run(args.trials, args.seed, args.min_delay, args.max_delay)


if __name__ == "__main__":
    raise SystemExit(main())
