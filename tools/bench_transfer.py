# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Speedrun addition.
#
# Benchmarks compute_transfer_scores against the stated budget: the transfer
# report must load in under 1s and refresh in under 500ms on a 50,000-card
# collection.
#
# This exists to check a claim made in rslib/src/transfer/mod.rs -- that scoring
# is a scan-and-reduce belonging next to SQLite. If that argument is right the
# numbers below hold; if it is wrong, this is where it shows up.
#
# Usage: python tools/bench_transfer.py [--cards 50000] [--reviews-per-card 8]

from __future__ import annotations

import argparse
import os
import statistics
import tempfile
import time

from anki.collection import Collection

TOPICS = [
    "biochem", "orgo", "physics", "psych", "socio",
    "bio", "gen_chem", "cars", "logic", "quant",
]


def build_collection(path: str, n_cards: int, reviews_per_card: int) -> Collection:
    """Populate directly via SQL.

    Going through the note/scheduler API for 50k cards would take many minutes
    and would benchmark the writer, not the reader. The read path under test is
    identical either way: revlog JOIN cards JOIN notes.
    """
    col = Collection(path)
    nid_base = 1_600_000_000_000
    now_ms = int(time.time() * 1000)

    notes, cards, revlog = [], [], []
    for i in range(n_cards):
        nid = nid_base + i
        cid = nid
        topic = TOPICS[i % len(TOPICS)]
        # Every third card is a transfer probe.
        tags = f" speedrun::topic::{topic} "
        if i % 3 == 0:
            tags = f" speedrun::topic::{topic} speedrun::probe "
        notes.append((nid, f"g{i}", 1, now_ms // 1000, -1, tags, f"front{i}\x1fback{i}",
                      f"front{i}", 0, 0, ""))
        cards.append((cid, nid, 1, 0, now_ms // 1000, -1, 0, 0, i, 0, 2500, 0, 0, 0, 0, 0, 0, ""))
        for r in range(reviews_per_card):
            rid = now_ms - (i * 1000 + r)
            # Probes fail more often than recall cards -- the pattern the
            # product exists to detect.
            ease = 1 if (r == 0 and i % 3 == 0) else 3
            revlog.append((rid, cid, -1, ease, 100, 50, 2500, 3000, 1))

    db = col.db
    db.executemany(
        "insert or replace into notes (id,guid,mid,mod,usn,tags,flds,sfld,csum,flags,data)"
        " values (?,?,?,?,?,?,?,?,?,?,?)", notes)
    db.executemany(
        "insert or replace into cards (id,nid,did,ord,mod,usn,type,queue,due,ivl,factor,"
        "reps,lapses,left,odue,odid,flags,data) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        cards)
    db.executemany(
        "insert or replace into revlog (id,cid,usn,ease,ivl,lastIvl,factor,time,type)"
        " values (?,?,?,?,?,?,?,?,?)", revlog)
    col.save()
    return col


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", type=int, default=50_000)
    ap.add_argument("--reviews-per-card", type=int, default=8)
    ap.add_argument("--runs", type=int, default=10)
    args = ap.parse_args()

    path = os.path.join(tempfile.mkdtemp(), "bench.anki2")
    print(f"building {args.cards:,} cards x {args.reviews_per_card} reviews ...")
    t0 = time.perf_counter()
    col = build_collection(path, args.cards, args.reviews_per_card)
    n_rev = col.db.scalar("select count() from revlog")
    print(f"  built in {time.perf_counter()-t0:.1f}s -- {n_rev:,} revlog rows")
    print(f"  collection size: {os.path.getsize(path)/1e6:.1f} MB")

    def call():
        t = time.perf_counter()
        out = col._backend.compute_transfer_scores(
            since_millis=0, min_reviews=20, min_cards=5)
        return (time.perf_counter() - t) * 1000, out

    cold_ms, out = call()
    warm = [call()[0] for _ in range(args.runs)]

    print()
    print(f"topics scored: {len(out.topics)}   readiness sufficient: {out.readiness.sufficient}")
    if out.topics:
        t = out.topics[0]
        print(f"  sample topic {t.topic!r}: memory={t.memory.point:.3f} "
              f"performance={t.performance.point:.3f} gap={t.gap:+.3f}")
    print()
    print(f"cold  (first load, budget <1000ms) : {cold_ms:8.1f} ms   "
          f"{'PASS' if cold_ms < 1000 else 'FAIL'}")
    print(f"warm  median (budget <500ms)       : {statistics.median(warm):8.1f} ms   "
          f"{'PASS' if statistics.median(warm) < 500 else 'FAIL'}")
    print(f"warm  p95                          : {sorted(warm)[int(len(warm)*0.95)-1]:8.1f} ms")
    print(f"warm  worst                        : {max(warm):8.1f} ms")
    col.close()
    return 0 if cold_ms < 1000 and statistics.median(warm) < 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
