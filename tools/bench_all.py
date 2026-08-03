# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Speedrun addition.
#
# Every performance target in Section 10, measured on one 50,000-card
# collection, in one command:
#
#     make bench
#
# Rules this harness follows
# --------------------------
# * Every printed number is measured in this run. Nothing is estimated,
#   interpolated, or carried over from a previous run.
# * A target that cannot be measured in this environment prints SKIPPED with
#   the reason and contributes no number and no verdict. It does not fail the
#   run, and it does not quietly pass either.
# * Percentiles are nearest-rank: p is the ceil(q * n)-th smallest sample,
#   1-indexed. No interpolation, so every printed percentile is a sample that
#   actually occurred.
# * Each budget states the statistic it is judged on. Latency budgets are p95;
#   "nothing blocks the UI" is a worst-case claim and is judged on the worst
#   single call.
#
# Structure: the parent builds (or reuses) the deck, then spawns child
# processes. Cold start has to be a cold process, and peak RSS is only
# meaningful for a process that did nothing else, so the measurements that need
# their own process get one.

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- the targets from Section 10 --------------------------------------------

REQUIRED_METRICS = (
    "answer_card",
    "next_card",
    "dashboard_load",
    "dashboard_refresh",
    "sync_session",
    "memory_rss",
    "cold_start",
    "ui_block",
)

#: Operations that run on the UI thread, and so feed the "nothing blocks the
#: UI" worst case. Sync is excluded: Anki runs it in a background thread behind
#: a progress dialog. Cold start is excluded: there is no UI yet to block.
UI_THREAD_KEYS = (
    "answer_card",
    "next_card",
    "card_render",
    "dashboard_load",
    "dashboard_refresh",
)


# --- statistics --------------------------------------------------------------


def percentile(samples: Sequence[float], q: float) -> float:
    """Nearest-rank percentile: the ceil(q*n)-th smallest sample, 1-indexed.

    No interpolation. Every number this returns is a measurement that actually
    happened, which is the point.
    """
    if not samples:
        raise ValueError("cannot take a percentile of zero samples")
    if not 0.0 < q <= 1.0:
        raise ValueError("q must be in (0, 1]")
    ordered = sorted(samples)
    rank = max(1, min(len(ordered), math.ceil(q * len(ordered))))
    return ordered[rank - 1]


# --- metrics -----------------------------------------------------------------


class Metric:
    """One row of the report.

    Either it has samples, or it has a skip reason. Never neither, and never
    both -- that is the whole guard against a fabricated number.
    """

    def __init__(
        self,
        key: str,
        label: str,
        budget: Optional[float],
        samples: Sequence[float],
        unit: str = "ms",
        judge: str = "p95",
        note: str = "",
        reason: str = "",
        _allow_empty: bool = False,
    ):
        if not samples and not _allow_empty:
            raise ValueError(
                "metric %r has no samples; a metric with nothing measured must "
                "be constructed with Metric.skipped() so the report says so" % key
            )
        if judge not in ("p95", "worst"):
            raise ValueError("judge must be 'p95' or 'worst'")
        self.key = key
        self.label = label
        self.budget = budget
        self.samples = list(samples)
        self.unit = unit
        self.judge = judge
        self.note = note
        self.reason = reason

    @classmethod
    def skipped(
        cls, key: str, label: str, budget: Optional[float], reason: str, unit: str = "ms"
    ) -> "Metric":
        if not reason:
            raise ValueError("a skipped metric must state why")
        return cls(
            key, label, budget, [], unit=unit, reason=reason, _allow_empty=True
        )

    # -- numbers

    @property
    def measured(self) -> bool:
        return bool(self.samples)

    def _require(self) -> None:
        if not self.samples:
            raise ValueError(
                "%s was not measured (%s); it has no statistics" % (self.key, self.reason)
            )

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def p50(self) -> float:
        self._require()
        return percentile(self.samples, 0.5)

    @property
    def p95(self) -> float:
        self._require()
        return percentile(self.samples, 0.95)

    @property
    def worst(self) -> float:
        self._require()
        return max(self.samples)

    @property
    def judged_value(self) -> float:
        return self.worst if self.judge == "worst" else self.p95

    # -- verdict

    @property
    def status(self) -> str:
        if not self.measured:
            return "SKIPPED"
        if self.budget is None:
            return "REPORT"
        return "PASS" if self.judged_value < self.budget else "FAIL"

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"

    @property
    def budget_text(self) -> str:
        if self.budget is None:
            return "report only"
        return "%s < %g %s" % (self.judge, self.budget, self.unit)

    def as_dict(self) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "budget": self.budget,
            "budget_statistic": self.judge,
            "unit": self.unit,
            "status": self.status,
            "samples": self.count,
            "note": self.note,
        }
        if self.measured:
            row.update(
                p50=round(self.p50, 3), p95=round(self.p95, 3), worst=round(self.worst, 3)
            )
        else:
            row["skip_reason"] = self.reason
        return row


def derive_ui_block(metrics: Sequence[Metric]) -> Metric:
    """The 'nothing blocks the UI over 100 ms' target.

    Not measured separately: it is the worst single call across every UI-thread
    operation this run measured. Pooling the samples is what makes the claim
    checkable -- a per-operation p95 can look fine while one call stalls.
    """
    contributing = [
        m for m in metrics if m.key in UI_THREAD_KEYS and m.measured
    ]
    if not contributing:
        return Metric.skipped(
            "ui_block",
            "longest blocking UI call",
            100.0,
            "no UI-thread operation was measured, so there is nothing to pool",
        )
    pooled: List[float] = []
    for m in contributing:
        pooled.extend(m.samples)
    worst_metric = max(contributing, key=lambda m: m.worst)
    return Metric(
        "ui_block",
        "longest blocking UI call",
        100.0,
        pooled,
        judge="worst",
        note="worst call was %s (%.1f ms); pooled over %s"
        % (
            worst_metric.label,
            worst_metric.worst,
            ", ".join(m.label for m in contributing),
        ),
    )


def check_coverage(metrics: Sequence[Metric]) -> None:
    """Every Section 10 target must appear, even if only to say SKIPPED."""
    present = {m.key for m in metrics}
    missing = [k for k in REQUIRED_METRICS if k not in present]
    if missing:
        raise ValueError(
            "the report is missing Section 10 targets: %s" % ", ".join(missing)
        )


def exit_code(metrics: Sequence[Metric]) -> int:
    return 1 if any(m.failed for m in metrics) else 0


# --- the table ---------------------------------------------------------------


def format_table(metrics: Sequence[Metric]) -> str:
    widths = (34, 20, 10, 10, 10, 5, 8)
    header = "%-*s %-*s %*s %*s %*s %-*s %-*s" % (
        widths[0], "metric",
        widths[1], "budget",
        widths[2], "p50",
        widths[3], "p95",
        widths[4], "worst",
        widths[5], "unit",
        widths[6], "result",
    )
    lines = [header, "-" * len(header)]
    for m in metrics:
        if m.measured:
            cells = ("%*.1f" % (widths[2], m.p50),
                     "%*.1f" % (widths[3], m.p95),
                     "%*.1f" % (widths[4], m.worst))
        else:
            cells = ("%*s" % (widths[2], "--"),
                     "%*s" % (widths[3], "--"),
                     "%*s" % (widths[4], "--"))
        lines.append(
            "%-*s %-*s %s %s %s %-*s %-*s"
            % (
                widths[0], m.label[: widths[0]],
                widths[1], m.budget_text,
                cells[0], cells[1], cells[2],
                widths[5], m.unit,
                widths[6], m.status,
            )
        )

    notes = [(m.label, m.reason or m.note) for m in metrics if m.reason or m.note]
    if notes:
        lines.append("")
        lines.append("Notes")
        lines.append("-" * len(header))
        for label, text in notes:
            lines.append("  %-32s %s" % (label + ":", text))
    return "\n".join(lines)


# --- collection under test ---------------------------------------------------


def _import_bench_transfer():
    """Reuse the existing collection builder rather than growing a second one."""
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import bench_transfer  # noqa: E402

    return bench_transfer


def build_deck(path: Path, cards: int, reviews_per_card: int) -> None:
    """Build the benchmark deck at `path`, using bench_transfer's builder.

    One change on top of it: the notes are pointed at a real notetype, because
    the scheduler targets measured here render cards, and bench_transfer's
    synthetic mid=1 has no template to render.
    """
    bench_transfer = _import_bench_transfer()

    path.parent.mkdir(parents=True, exist_ok=True)
    # Built in place rather than via a .partial rename. Anki does not guarantee
    # the collection file stays at the path you handed it across close(), so the
    # rename step failed with the temp file already gone -- while the deck it had
    # just built was sitting at the final path, complete. Correctness here comes
    # from deleting a half-built deck on failure, not from an atomic rename we
    # cannot actually guarantee.
    for stale in (path, Path(str(path) + "-wal"), Path(str(path) + "-journal")):
        if stale.exists():
            stale.unlink()

    col = bench_transfer.build_collection(str(path), cards, reviews_per_card)
    basic = col.models.by_name("Basic")
    col.db.execute("update notes set mid = ?", basic["id"])

    # A 50k-card deck is not a 20-new-cards-a-day deck; the session being
    # measured has to be able to run past the default daily limits.
    #
    # 9999 and not 999999: anything above 9999 is rejected by the schema11
    # deck-config bridge, which then silently falls back to the *default*
    # config -- 20 new a day. That silence is why the read-back below exists;
    # the first version of this asked for 999999, got 20, and the session ran
    # dry after 40 cards while reporting nothing wrong.
    limit = 9_999
    conf = col.decks.get_config(1)
    conf["new"]["perDay"] = limit
    conf["rev"]["perDay"] = limit
    col.decks.update_config(conf)
    stored = col.decks.get_config(1)
    if stored["new"]["perDay"] != limit or stored["rev"]["perDay"] != limit:
        col.close()
        raise RuntimeError(
            "deck limits did not stick (new=%s rev=%s, wanted %d); the review "
            "session would silently measure only the first few cards"
            % (stored["new"]["perDay"], stored["rev"]["perDay"], limit)
        )
    col.close()
    if not path.exists():
        raise RuntimeError(f"deck build finished but {path} is missing")


def ensure_deck(path: Path, cards: int, reviews_per_card: int) -> bool:
    """Build the deck if it is not already there. Returns True if it built one."""
    if path.exists():
        return False
    build_deck(path, cards, reviews_per_card)
    return True


# --- local sync server -------------------------------------------------------


class SyncServer:
    """Anki's own built-in sync server, on loopback.

    Started here so that "normal session sync" is a measured number rather than
    a permanent SKIPPED. It is a real sync of a real 50k collection over real
    HTTP, but over loopback: it contains no wide-area latency. The report says
    so, because a reader who assumes otherwise would be misled.
    """

    def __init__(self, port: int = 27701):
        self.port = port
        self.proc: Optional[subprocess.Popen] = None
        self.base = Path(tempfile.mkdtemp(prefix="speedrun-syncserver-"))
        self.endpoint = "http://127.0.0.1:%d/" % port
        self.username = "bench"
        self.password = "bench"
        self.failure = ""

    def _port_open(self) -> bool:
        with socket.socket() as s:
            s.settimeout(0.25)
            return s.connect_ex(("127.0.0.1", self.port)) == 0

    def start(self, timeout: float = 30.0) -> bool:
        if self._port_open():
            self.failure = "port %d already in use" % self.port
            return False
        env = dict(os.environ)
        env.update(
            SYNC_BASE=str(self.base),
            SYNC_HOST="127.0.0.1",
            SYNC_PORT=str(self.port),
            SYNC_USER1="%s:%s" % (self.username, self.password),
            RUST_LOG="error",
        )
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "anki.syncserver"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self.failure = "could not launch anki.syncserver (%s)" % exc
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                self.failure = "anki.syncserver exited with code %s" % self.proc.returncode
                return False
            if self._port_open():
                return True
            time.sleep(0.2)
        self.failure = "anki.syncserver did not listen on port %d within %.0fs" % (
            self.port,
            timeout,
        )
        self.stop()
        return False

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.base, ignore_errors=True)


# --- child processes ---------------------------------------------------------
#
# Anki's backend prints a "blocked main thread for Nms" traceback to stdout
# whenever a call exceeds 200ms, so children write their JSON to a file rather
# than stdout, and the parent counts those warnings from the captured stdout.


def _peak_rss_mb() -> float:
    import resource

    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes, Linux reports kilobytes.
    return raw / 1e6 if sys.platform == "darwin" else raw / 1e3


def child_coldstart(collection: str, out_path: str, process_start: float) -> None:
    """Cold start: an untouched process opening the 50k collection and getting
    to the point where the first card could be shown."""
    from anki.collection import Collection

    t = time.perf_counter()
    col = Collection(collection)
    open_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    col.sched.get_queued_cards(fetch_limit=1)
    first_fetch_ms = (time.perf_counter() - t) * 1000
    ready_ms = (time.time() - process_start) * 1000
    col.close()
    Path(out_path).write_text(
        json.dumps(
            {
                "ready_ms": ready_ms,
                "open_ms": open_ms,
                "first_fetch_ms": first_fetch_ms,
                "peak_rss_mb": _peak_rss_mb(),
            }
        ),
        encoding="utf-8",
    )


def child_session(
    collection: str,
    out_path: str,
    reviews: int,
    refreshes: int,
    sync: Optional[Dict[str, str]],
) -> None:
    """A review session on the 50k collection, in one process, measuring the
    per-operation latencies and the peak RSS that session costs."""
    # anki.collection must be imported before anki.cards: importing cards
    # first hits a circular import in anki.hooks_gen.
    from anki.collection import Collection
    from anki.cards import Card
    from anki.scheduler.v3 import CardAnswer

    result: Dict[str, Any] = {
        "next_card_ms": [],
        "card_render_ms": [],
        "answer_card_ms": [],
        "dashboard_load_ms": [],
        "dashboard_refresh_ms": [],
        "sync_ms": [],
        "sync_skip_reason": "",
        "cards_answered": 0,
    }

    def grade(count: int) -> int:
        """The real review loop: fetch, render, answer, repeat."""
        done = 0
        for _ in range(count):
            t = time.perf_counter()
            queued = col.sched.get_queued_cards(fetch_limit=1)
            result["next_card_ms"].append((time.perf_counter() - t) * 1000)
            if not queued.cards:
                break
            entry = queued.cards[0]
            card = Card(col)
            card._load_from_backend_card(entry.card)
            t = time.perf_counter()
            card.question()
            result["card_render_ms"].append((time.perf_counter() - t) * 1000)
            card.start_timer()
            answer = col.sched.build_answer(
                card=card, states=entry.states, rating=CardAnswer.GOOD
            )
            t = time.perf_counter()
            col.sched.answer_card(answer)
            result["answer_card_ms"].append((time.perf_counter() - t) * 1000)
            result["cards_answered"] += 1
            done += 1
        return done

    col = Collection(collection)
    try:
        # Dashboard: first load is cold by definition, so it is measured once,
        # before anything else has warmed the page cache or SQLite.
        t = time.perf_counter()
        col._backend.compute_transfer_scores(since_millis=0, min_reviews=20, min_cards=5)
        result["dashboard_load_ms"].append((time.perf_counter() - t) * 1000)
        for _ in range(refreshes):
            t = time.perf_counter()
            col._backend.compute_transfer_scores(
                since_millis=0, min_reviews=20, min_cards=5
            )
            result["dashboard_refresh_ms"].append((time.perf_counter() - t) * 1000)

        if sync:
            _measure_sync(col, sync, result, grade, reviews)
        else:
            result["sync_skip_reason"] = "no sync server was started"
            grade(reviews)

        result["peak_rss_mb"] = _peak_rss_mb()
        result["collection_bytes"] = os.path.getsize(collection)
        result["card_count"] = col.db.scalar("select count() from cards")
        result["revlog_count"] = col.db.scalar("select count() from revlog")
    finally:
        col.close()

    Path(out_path).write_text(json.dumps(result), encoding="utf-8")


SYNC_ROUNDS = 3


def _measure_sync(
    col: Any,
    sync: Dict[str, str],
    result: Dict[str, Any],
    grade: Any,
    reviews: int,
) -> None:
    """Time a normal session sync: study some cards, then sync what that made.

    Deliberately not synthesised with raw SQL. An earlier version bumped
    `usn = -1` directly and the sync then left every one of those rows pending
    -- the guard below caught it -- because writes that go around the backend
    are not what the sync layer tracks. So the changes timed here are the ones
    the graded review session actually produced.

    Excluded, and why: the first sync of a fresh collection is a full upload,
    not a session sync; `sync_login` is a one-time PBKDF2 hash, not something a
    session sync pays. Each timed sync checks that there were pending changes
    going in and none coming out. A sync that moved nothing is reported as a
    skip, not as a fast sync.
    """
    per_round = max(1, reviews // SYNC_ROUNDS)
    try:
        auth = col.sync_login(sync["username"], sync["password"], sync["endpoint"])
    except Exception as exc:
        result["sync_skip_reason"] = "sync login failed (%s: %s)" % (
            type(exc).__name__,
            exc,
        )
        grade(reviews)
        return
    try:
        out = col.sync_collection(auth, False)
        if out.required != 0:
            # media is not synced here, so no media usn is passed -- the same
            # choice aqt/sync.py makes when media syncing is disabled.
            col.full_upload_or_download(auth=auth, server_usn=None, upload=True)
            col.sync_collection(auth, False)
    except Exception as exc:
        result["sync_skip_reason"] = "baseline full upload failed (%s: %s)" % (
            type(exc).__name__,
            exc,
        )
        grade(reviews)
        return

    for _ in range(SYNC_ROUNDS):
        graded = grade(per_round)
        pending = col.db.scalar(
            "select (select count() from cards where usn = -1) + "
            "(select count() from revlog where usn = -1)"
        )
        if not pending:
            result["sync_skip_reason"] = (
                "grading %d cards produced no pending sync changes, so a timed "
                "sync here would be a no-op, not a session sync" % graded
            )
            result["sync_ms"] = []
            return
        try:
            t = time.perf_counter()
            col.sync_collection(auth, False)
            elapsed = (time.perf_counter() - t) * 1000
        except Exception as exc:
            result["sync_skip_reason"] = "sync failed (%s: %s)" % (
                type(exc).__name__,
                exc,
            )
            result["sync_ms"] = []
            return
        left = col.db.scalar(
            "select (select count() from cards where usn = -1) + "
            "(select count() from revlog where usn = -1)"
        )
        if left:
            result["sync_skip_reason"] = (
                "sync left %d of %d changes pending, so the elapsed time does "
                "not represent a completed sync" % (left, pending)
            )
            result["sync_ms"] = []
            return
        result["sync_ms"].append(elapsed)
        result.setdefault("sync_changes", []).append(pending)

    remaining = reviews - result["cards_answered"]
    if remaining > 0:
        grade(remaining)


# --- parent ------------------------------------------------------------------


@dataclass
class ChildRun:
    payload: Dict[str, Any]
    wall_ms: float
    blocked_warnings: int
    stdout: str = ""

    @property
    def blocked_detail(self) -> str:
        hits = parse_blocked_warnings(self.stdout)
        if not hits:
            return ""
        return ", ".join("%dms in %s()" % (ms, where) for ms, where in hits)


def parse_blocked_warnings(stdout: str) -> List[tuple]:
    """Pull Anki's own >200ms main-thread warnings out of a child's stdout.

    These are calls the harness does not time itself -- collection open, close,
    the full upload -- so without this they would be invisible to the
    UI-blocking target even though the backend already noticed them.
    """
    hits: List[tuple] = []
    chunks = stdout.split("blocked main thread for ")[1:]
    for chunk in chunks:
        head, _, body = chunk.partition("ms:")
        try:
            ms = int(head.strip())
        except ValueError:
            continue
        where = "unknown"
        lines = body.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not (stripped.startswith('File "') and ", in " in stripped):
                continue
            if "_backend.py" in stripped or "_backend_generated.py" in stripped:
                continue
            # The source line under the frame says what the call actually was;
            # the function name alone is usually just the harness's own frame.
            source = lines[index + 1].strip() if index + 1 < len(lines) else ""
            where = source or stripped.rsplit(", in ", 1)[1]
        hits.append((ms, where[:70]))
    return hits


def _run_child(args: List[str], env: Dict[str, str]) -> ChildRun:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        out_path = handle.name
    try:
        start = time.time()
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())]
            + args
            + ["--out", out_path, "--process-start", repr(start)],
            env=env,
            capture_output=True,
            text=True,
        )
        wall_ms = (time.time() - start) * 1000
        if completed.returncode != 0:
            raise RuntimeError(
                "child failed (%d):\n%s\n%s"
                % (completed.returncode, completed.stdout[-2000:], completed.stderr[-2000:])
            )
        payload = json.loads(Path(out_path).read_text(encoding="utf-8"))
        return ChildRun(
            payload=payload,
            wall_ms=wall_ms,
            blocked_warnings=completed.stdout.count("blocked main thread"),
            stdout=completed.stdout,
        )
    finally:
        Path(out_path).unlink(missing_ok=True)


def _child_env() -> Dict[str, str]:
    env = dict(os.environ)
    pylib_out = REPO_ROOT / "out" / "pylib"
    existing = env.get("PYTHONPATH", "")
    if str(pylib_out) not in existing.split(os.pathsep):
        env["PYTHONPATH"] = (
            str(pylib_out) + (os.pathsep + existing if existing else "")
        )
    return env


def run_benchmark(
    collection: Path,
    reviews: int,
    refreshes: int,
    cold_runs: int,
    want_sync: bool,
) -> "BenchResult":
    env = _child_env()
    work = Path(tempfile.mkdtemp(prefix="speedrun-bench-"))
    notes: List[str] = []
    metrics: List[Metric] = []

    server: Optional[SyncServer] = None
    sync_config: Optional[Dict[str, str]] = None
    sync_skip = ""
    if want_sync:
        server = SyncServer()
        if server.start():
            sync_config = {
                "endpoint": server.endpoint,
                "username": server.username,
                "password": server.password,
            }
        else:
            sync_skip = "no sync server (%s)" % server.failure
            server = None
    else:
        sync_skip = "no sync server (--no-sync was passed)"

    try:
        # --- cold start: a fresh process per sample, on its own copy so no
        #     earlier run has warmed anything it should not have.
        cold_ready: List[float] = []
        cold_open: List[float] = []
        cold_rss: List[float] = []
        for index in range(cold_runs):
            copy = work / ("cold%d.anki2" % index)
            shutil.copy2(collection, copy)
            run = _run_child(["--child-coldstart", "--collection", str(copy)], env)
            cold_ready.append(run.payload["ready_ms"])
            cold_open.append(run.payload["open_ms"])
            cold_rss.append(run.payload["peak_rss_mb"])
            copy.unlink(missing_ok=True)

        metrics.append(
            Metric(
                "cold_start",
                "cold start (open collection, first card)",
                5000.0,
                cold_ready,
                note="process spawn to first card fetched, %d cold processes; "
                "collection open alone was p50 %.0f ms. Excludes Qt UI "
                "construction -- this is the pylib path only."
                % (cold_runs, percentile(cold_open, 0.5)),
            )
        )

        # --- the session
        session_copy = work / "session.anki2"
        shutil.copy2(collection, session_copy)
        session_args = [
            "--child-session",
            "--collection", str(session_copy),
            "--reviews", str(reviews),
            "--refreshes", str(refreshes),
        ]
        if sync_config:
            session_args += [
                "--sync-endpoint", sync_config["endpoint"],
                "--sync-user", sync_config["username"],
                "--sync-pass", sync_config["password"],
            ]
        session = _run_child(session_args, env)
        payload = session.payload

        metrics.append(
            Metric(
                "answer_card",
                "button press acknowledged",
                50.0,
                payload["answer_card_ms"],
                note="col.sched.answer_card() round trip, %d graded cards%s"
                % (
                    payload["cards_answered"],
                    ""
                    if payload["cards_answered"] >= reviews
                    else " -- SHORT of the %d asked for; the deck's queue ran "
                    "out, so this sample is smaller than intended" % reviews,
                ),
            )
        )
        metrics.append(
            Metric(
                "next_card",
                "next card after grading",
                100.0,
                payload["next_card_ms"],
                note="col.sched.get_queued_cards() fetch; question rendering is "
                "timed separately below",
            )
        )
        metrics.append(
            Metric(
                "card_render",
                "  ...card question render",
                100.0,
                payload["card_render_ms"],
                note="not a Section 10 target on its own; measured because it is "
                "on the UI thread between the fetch and the card appearing",
            )
        )
        metrics.append(
            Metric(
                "dashboard_load",
                "dashboard first load",
                1000.0,
                payload["dashboard_load_ms"],
                note="one cold compute_transfer_scores in a fresh process",
            )
        )
        metrics.append(
            Metric(
                "dashboard_refresh",
                "dashboard refresh",
                500.0,
                payload["dashboard_refresh_ms"],
                note="%d warm compute_transfer_scores calls"
                % len(payload["dashboard_refresh_ms"]),
            )
        )

        # --- sync
        if payload["sync_ms"]:
            metrics.append(
                Metric(
                    "sync_session",
                    "normal session sync",
                    5000.0,
                    payload["sync_ms"],
                    note="incremental sync of ~%d pending card/revlog changes against "
                    "Anki's own sync server on loopback. Real HTTP, real collection, "
                    "but NO wide-area latency: a floor, not an AnkiWeb number. "
                    "Baseline full upload and login are excluded."
                    % (payload.get("sync_changes", [0])[0]),
                )
            )
        else:
            metrics.append(
                Metric.skipped(
                    "sync_session",
                    "normal session sync",
                    5000.0,
                    payload["sync_skip_reason"] or sync_skip or "no sync server",
                )
            )

        # --- memory
        metrics.append(
            Metric(
                "memory_rss",
                "peak RSS, desktop",
                None,
                [payload["peak_rss_mb"]],
                unit="MB",
                note="peak resident set size of the session process after "
                "opening the collection, grading %d cards and %d dashboard "
                "renders. Cold-start processes peaked at %.0f MB. No stated "
                "budget in Section 10, so this is reported, not judged."
                % (
                    payload["cards_answered"],
                    len(payload["dashboard_refresh_ms"]) + 1,
                    max(cold_rss),
                ),
            )
        )

        # --- derived
        ui = derive_ui_block(metrics)
        if session.blocked_warnings:
            ui.note += (
                ". Anki's own >200ms main-thread watchdog also fired %d time(s) "
                "during the session, on calls this harness does not time: %s"
                % (session.blocked_warnings, session.blocked_detail)
            )
        else:
            ui.note += (
                ". Anki's own >200ms main-thread watchdog did not fire during "
                "the session"
            )
        metrics.append(ui)

        notes.append(
            "collection: %s (%.0f MB, %s cards, %s revlog rows)"
            % (
                collection,
                payload["collection_bytes"] / 1e6,
                "{:,}".format(payload["card_count"]),
                "{:,}".format(payload["revlog_count"]),
            )
        )
    finally:
        if server:
            server.stop()
        shutil.rmtree(work, ignore_errors=True)

    check_coverage(metrics)
    return BenchResult(metrics=metrics, notes=notes)


@dataclass
class BenchResult:
    metrics: List[Metric]
    notes: List[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return exit_code(self.metrics)

    def format_text(self) -> str:
        lines = ["", "Speedrun Section 10 performance targets", "=" * 108]
        for note in self.notes:
            lines.append(note)
        lines.append(
            "percentiles are nearest-rank (the ceil(q*n)-th smallest sample; no "
            "interpolation)"
        )
        lines.append("")
        lines.append(format_table(self.metrics))
        lines.append("")
        measured = [m for m in self.metrics if m.measured and m.budget is not None]
        skipped = [m for m in self.metrics if not m.measured]
        failed = [m for m in self.metrics if m.failed]
        lines.append(
            "%d budgeted targets measured, %d skipped, %d failed"
            % (len(measured), len(skipped), len(failed))
        )
        if failed:
            lines.append(
                "FAILED: %s" % ", ".join("%s (%s)" % (m.label, m.status) for m in failed)
            )
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "notes": self.notes,
            "percentile_method": "nearest-rank, ceil(q*n)-th smallest, 1-indexed",
            "metrics": [m.as_dict() for m in self.metrics],
        }


# --- CLI ---------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python tools/bench_all.py",
        description="Measure every Section 10 performance target on one "
        "50,000-card collection.",
    )
    parser.add_argument("--cards", type=int, default=50_000)
    parser.add_argument("--reviews-per-card", type=int, default=8)
    parser.add_argument(
        "--collection",
        default=str(REPO_ROOT / "out" / "bench" / "speedrun-50k.anki2"),
        help="path to the benchmark deck; built if absent",
    )
    parser.add_argument("--reviews", type=int, default=200, help="cards graded")
    parser.add_argument("--refreshes", type=int, default=12)
    parser.add_argument("--cold-runs", type=int, default=5)
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="rebuild the deck")
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="build the deck and stop, without measuring anything",
    )
    # child-process entry points
    parser.add_argument("--child-session", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--child-coldstart", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--out", default="", help=argparse.SUPPRESS)
    parser.add_argument("--process-start", default="0", help=argparse.SUPPRESS)
    parser.add_argument("--sync-endpoint", default="", help=argparse.SUPPRESS)
    parser.add_argument("--sync-user", default="", help=argparse.SUPPRESS)
    parser.add_argument("--sync-pass", default="", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.child_coldstart:
        child_coldstart(args.collection, args.out, float(args.process_start))
        return 0
    if args.child_session:
        sync = None
        if args.sync_endpoint:
            sync = {
                "endpoint": args.sync_endpoint,
                "username": args.sync_user,
                "password": args.sync_pass,
            }
        child_session(args.collection, args.out, args.reviews, args.refreshes, sync)
        return 0

    collection = Path(args.collection)
    if args.rebuild and collection.exists():
        collection.unlink()
    if not collection.exists():
        print(
            "building %s: %s cards x %d reviews (one-off; reused on later runs)"
            % (collection, "{:,}".format(args.cards), args.reviews_per_card),
            flush=True,
        )
        started = time.perf_counter()
        build_deck(collection, args.cards, args.reviews_per_card)
        print("  built in %.0fs" % (time.perf_counter() - started), flush=True)
    else:
        print("reusing deck at %s (--rebuild to rebuild)" % collection, flush=True)

    if args.build_only:
        return 0

    result = run_benchmark(
        collection=collection,
        reviews=args.reviews,
        refreshes=args.refreshes,
        cold_runs=args.cold_runs,
        want_sync=not args.no_sync,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(result.format_text())
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
