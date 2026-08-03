# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
#
# Speedrun addition: the transfer report.
#
# This view has one job beyond displaying numbers: when the engine refuses to
# score something, it must show the refusal AS a refusal. Rendering a declined
# score as 0%, or as an empty cell that reads like a low score, would reintroduce
# exactly the dishonesty the engine was built to prevent -- and it would do it in
# the last hundred lines of the stack, where nobody is looking.

from __future__ import annotations

from concurrent.futures import Future
from typing import Any

import aqt
from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
    Qt,
    qconnect,
)
from aqt.utils import restoreGeom, saveGeom

# Below these counts the engine declines to score. Passed explicitly so the
# displayed shortfall matches what the engine actually applied.
MIN_REVIEWS = 20
MIN_CARDS = 5


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _score_cell(score) -> str:
    """Render one score, or an honest account of why there isn't one."""
    if not score.sufficient:
        missing = []
        if score.observations < score.needed_observations:
            missing.append(
                f"{score.needed_observations - score.observations} more reviews"
            )
        if score.cards < score.needed_cards:
            missing.append(f"{score.needed_cards - score.cards} more cards")
        detail = " and ".join(missing) if missing else "more evidence"
        return (
            '<td class="refused">not enough evidence'
            f'<span class="detail">needs {detail}</span></td>'
        )
    width = score.upper - score.lower
    return (
        f'<td class="score">{_pct(score.point)}'
        f'<span class="detail">{_pct(score.lower)} – {_pct(score.upper)}'
        f" &nbsp;·&nbsp; {score.observations} reviews / {score.cards} cards</span></td>"
    )


def _gap_cell(topic) -> str:
    if not topic.gap_valid:
        return '<td class="refused">—<span class="detail">needs both scores</span></td>'
    # A negative gap means transfer performance exceeded recall, which is
    # unusual and worth showing plainly rather than clamping to zero.
    cls = "gap-wide" if topic.gap >= 0.15 else "gap"
    return f'<td class="{cls}">{topic.gap * 100:+.0f} pts</td>'


def _render(scores) -> str:
    readiness = scores.readiness
    if readiness.sufficient:
        readiness_html = (
            f'<div class="headline">{_pct(readiness.point)}'
            f'<span class="sub">{_pct(readiness.lower)} – {_pct(readiness.upper)}'
            f" &nbsp;·&nbsp; from {readiness.observations} probe reviews</span></div>"
        )
    else:
        readiness_html = (
            '<div class="headline refused-headline">Not enough evidence to project'
            f'<span class="sub">{readiness.observations} probe reviews so far;'
            f" needs {readiness.needed_observations}</span></div>"
        )

    rows = "".join(
        f"<tr><td class='topic'>{t.topic}</td>"
        f"{_score_cell(t.memory)}{_score_cell(t.performance)}{_gap_cell(t)}</tr>"
        for t in scores.topics
    )
    if not rows:
        rows = (
            "<tr><td colspan='4' class='refused'>No reviews are attributed to an "
            "exam topic yet. Tag notes with <code>speedrun::topic::&lt;name&gt;</code>, "
            "and tag reworded variants <code>speedrun::probe</code>.</td></tr>"
        )

    return f"""
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; font-size: 13px; }}
  .headline {{ font-size: 30px; font-weight: 600; margin: 4px 0 2px; }}
  .headline .sub {{ display:block; font-size:12px; font-weight:400; opacity:.65; }}
  .refused-headline {{ font-size: 17px; opacity: .8; }}
  .caption {{ opacity:.65; margin-bottom:14px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ text-align:left; font-weight:600; padding:6px 8px;
       border-bottom:1px solid rgba(128,128,128,.35); }}
  td {{ padding:8px; border-bottom:1px solid rgba(128,128,128,.15);
       vertical-align: top; }}
  .topic {{ font-weight:600; }}
  .score {{ font-variant-numeric: tabular-nums; }}
  .detail {{ display:block; font-size:11px; opacity:.6; }}
  .refused {{ opacity:.75; font-style:italic; }}
  .gap {{ font-variant-numeric: tabular-nums; }}
  .gap-wide {{ font-variant-numeric: tabular-nums; font-weight:700; }}
  .note {{ margin-top:16px; font-size:11.5px; opacity:.7; line-height:1.5; }}
</style>

<div class="caption">Projected exam readiness</div>
{readiness_html}

<table>
  <tr>
    <th>Topic</th>
    <th>Memory<br><span class="detail">recall, as trained</span></th>
    <th>Performance<br><span class="detail">reworded probes</span></th>
    <th>Gap</th>
  </tr>
  {rows}
</table>

<div class="note">
  <b>Memory</b> is how often you recall material in the form you studied it.
  <b>Performance</b> is how often you get it right when the wording changes.
  The <b>gap</b> between them is what a single retention percentage hides.<br>
  Readiness pools probe results across topics. It is <i>not</i> yet weighted by
  the official exam outline, so it reflects the mix you happen to have studied,
  not the mix the exam will ask. Treat it as a floor, not a prediction.
</div>
"""


def _render_loading() -> str:
    return (
        '<div style="font-family:-apple-system,Segoe UI,sans-serif;'
        'opacity:.6;padding:24px">Scoring your review history…</div>'
    )


class TransferReportDialog(QDialog):
    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        QDialog.__init__(self, mw, Qt.WindowType.Window)
        self.mw = mw
        self.setWindowTitle("Transfer Report")
        self.setMinimumSize(660, 460)

        layout = QVBoxLayout(self)
        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(False)
        layout.addWidget(self.browser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

        self.refresh()
        restoreGeom(self, "transferReport")

    def refresh(self) -> None:
        """Compute off the main thread.

        Scoring scans the whole review log: ~500 ms on a 50,000-card collection.
        Run inline, that is a half-second UI freeze every time this opens, and
        Anki's own watchdog flags it. Section 10 sets a 100 ms ceiling on
        blocking the UI, and no amount of optimising the query gets a full-log
        scan under that -- the fix is to not be on this thread at all.
        """
        self.browser.setHtml(_render_loading())

        def task() -> Any:
            return self.mw.col._backend.compute_transfer_scores(
                since_millis=0, min_reviews=MIN_REVIEWS, min_cards=MIN_CARDS
            )

        def on_done(future: Future) -> None:
            # Re-raises on the main thread if scoring failed, so an error
            # surfaces as an error rather than as a permanently loading pane.
            self.browser.setHtml(_render(future.result()))

        self.mw.taskman.run_in_background(task, on_done)

    def reject(self) -> None:
        saveGeom(self, "transferReport")
        QDialog.reject(self)


def show_transfer_report(mw: aqt.main.AnkiQt) -> None:
    TransferReportDialog(mw).show()
