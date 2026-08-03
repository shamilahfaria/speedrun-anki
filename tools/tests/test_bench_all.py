"""Tests for the Section 10 benchmark harness.

Written before tools/bench_all.py exists. They pin the parts that decide
whether a number is reported honestly: percentile definition, the PASS/FAIL
rule, that a metric which could not be measured says so instead of producing a
number, and that the exit code follows the measured results.

The measurement functions themselves are not unit-tested -- they are the thing
being measured, and stubbing a timer would test the stub. What is tested here
is everything that stands between a raw sample and a printed claim.
"""

from __future__ import annotations

import pytest

import bench_all as ba


# --- percentiles -------------------------------------------------------------


def test_percentile_is_nearest_rank():
    # Nearest-rank: p = ceil(q * n) th smallest, 1-indexed. Stated in the
    # report so a reader can reproduce the arithmetic.
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert ba.percentile(data, 0.5) == 5.0
    assert ba.percentile(data, 0.95) == 10.0
    assert ba.percentile(data, 1.0) == 10.0


def test_percentile_ignores_input_order():
    assert ba.percentile([9.0, 1.0, 5.0], 0.5) == 5.0


def test_percentile_of_single_sample_is_that_sample():
    assert ba.percentile([42.0], 0.95) == 42.0


def test_percentile_rejects_empty_input():
    with pytest.raises(ValueError):
        ba.percentile([], 0.5)


# --- a measured metric -------------------------------------------------------


def test_metric_reports_p50_p95_and_worst():
    m = ba.Metric("k", "label", budget=100.0, samples=[10.0, 20.0, 30.0, 400.0])
    assert m.p50 == 20.0
    assert m.p95 == 400.0
    assert m.worst == 400.0
    assert m.count == 4


def test_metric_passes_when_p95_is_under_budget():
    m = ba.Metric("k", "label", budget=50.0, samples=[10.0] * 20)
    assert m.status == "PASS"
    assert m.failed is False


def test_metric_fails_when_p95_exceeds_budget():
    # Two of twenty over budget: nearest-rank p95 is the 19th sample, so a
    # single outlier would (correctly) not fail a p95 budget.
    m = ba.Metric("k", "label", budget=50.0, samples=[10.0] * 18 + [900.0, 900.0])
    assert m.status == "FAIL"
    assert m.failed is True


def test_one_outlier_in_twenty_does_not_fail_a_p95_budget():
    m = ba.Metric("k", "label", budget=50.0, samples=[10.0] * 19 + [900.0])
    assert m.p95 == 10.0
    assert m.worst == 900.0
    assert m.status == "PASS"


def test_a_worst_case_budget_is_judged_on_the_worst_sample():
    m = ba.Metric("k", "label", budget=50.0, samples=[10.0] * 19 + [900.0], judge="worst")
    assert m.status == "FAIL"


def test_metric_with_no_budget_is_report_only_and_never_fails():
    m = ba.Metric("mem", "peak RSS", budget=None, samples=[812.0], unit="MB")
    assert m.status == "REPORT"
    assert m.failed is False
    assert m.unit == "MB"


# --- unmeasurable metrics ----------------------------------------------------


def test_skipped_metric_has_no_numbers_and_never_fails():
    m = ba.Metric.skipped("sync", "session sync", budget=5000.0, reason="no sync server")
    assert m.status == "SKIPPED"
    assert m.failed is False
    assert m.samples == []
    assert m.reason == "no sync server"


def test_skipped_metric_refuses_to_invent_a_percentile():
    m = ba.Metric.skipped("sync", "session sync", budget=5000.0, reason="no sync server")
    with pytest.raises(ValueError):
        _ = m.p95


def test_a_metric_with_zero_samples_is_not_silently_a_pass():
    with pytest.raises(ValueError):
        ba.Metric("k", "label", budget=50.0, samples=[])


# --- the table ---------------------------------------------------------------


def _row_for(table: str, key_fragment: str) -> str:
    for line in table.splitlines():
        if key_fragment in line:
            return line
    raise AssertionError("no row containing %r in:\n%s" % (key_fragment, table))


def test_table_has_the_required_columns():
    table = ba.format_table([ba.Metric("k", "answer card", 50.0, [1.0])])
    header = table.splitlines()[0]
    for column in ("metric", "budget", "p50", "p95", "worst", "result"):
        assert column in header.lower()


def test_table_prints_the_skip_reason_instead_of_numbers():
    table = ba.format_table(
        [ba.Metric.skipped("sync", "session sync", 5000.0, "no sync server")]
    )
    row = _row_for(table, "session sync")
    assert "SKIPPED" in row
    assert "no sync server" in table
    # No fabricated digits in the number columns.
    assert "0.0" not in row


def test_table_shows_units_for_non_millisecond_metrics():
    table = ba.format_table(
        [ba.Metric("mem", "peak RSS", None, [812.5], unit="MB")]
    )
    row = _row_for(table, "peak RSS")
    assert "812.5" in row
    assert "MB" in row


# --- exit code ---------------------------------------------------------------


def test_exit_code_is_zero_when_everything_measured_passes():
    metrics = [
        ba.Metric("a", "a", 50.0, [1.0]),
        ba.Metric("b", "b", 100.0, [2.0]),
        ba.Metric("m", "m", None, [999.0], unit="MB"),
    ]
    assert ba.exit_code(metrics) == 0


def test_exit_code_is_non_zero_when_any_measured_metric_fails():
    metrics = [ba.Metric("a", "a", 50.0, [1.0]), ba.Metric("b", "b", 100.0, [500.0])]
    assert ba.exit_code(metrics) != 0


def test_a_skipped_metric_does_not_fail_the_run():
    metrics = [
        ba.Metric("a", "a", 50.0, [1.0]),
        ba.Metric.skipped("sync", "sync", 5000.0, "no sync server"),
    ]
    assert ba.exit_code(metrics) == 0


# --- the derived "nothing blocks the UI" metric ------------------------------


def test_ui_block_takes_the_worst_single_call_across_ui_thread_operations():
    a = ba.Metric("answer_card", "answer card", 50.0, [10.0, 12.0])
    b = ba.Metric("card_render", "card render", 100.0, [40.0, 310.0])
    ui = ba.derive_ui_block([a, b])
    assert ui.worst == 310.0
    assert ui.budget == 100.0
    assert "card render" in ui.note


def test_ui_block_excludes_dashboard_scoring_because_it_is_backgrounded():
    # qt/aqt/transfer.py computes scores via taskman.run_in_background. Pooling
    # it here would report a UI freeze that does not happen. If that call ever
    # goes back inline, this test is the thing that has to be changed with it.
    on_thread = ba.Metric("answer_card", "answer card", 50.0, [10.0])
    backgrounded = ba.Metric("dashboard_refresh", "dashboard refresh", 500.0, [500.0])
    ui = ba.derive_ui_block([on_thread, backgrounded])
    assert ui.worst == 10.0
    assert "dashboard" in ui.note.lower()


def test_ui_block_is_skipped_when_no_ui_thread_operation_was_measured():
    ui = ba.derive_ui_block(
        [ba.Metric.skipped("answer_card", "answer card", 50.0, "nope")]
    )
    assert ui.status == "SKIPPED"


def test_ui_block_ignores_operations_that_do_not_run_on_the_ui_thread():
    # Sync runs in a background thread behind a progress dialog; counting it
    # would report a UI stall that never happens.
    on_thread = ba.Metric("answer_card", "answer card", 50.0, [10.0])
    off_thread = ba.Metric("sync_session", "session sync", 5000.0, [4000.0])
    assert ba.derive_ui_block([on_thread, off_thread]).worst == 10.0


def test_ui_block_fails_when_a_single_call_blocks_too_long():
    a = ba.Metric("card_render", "card question render", 100.0, [820.0])
    assert ba.derive_ui_block([a]).failed is True


# --- coverage of the stated targets ------------------------------------------


def test_every_section_10_target_has_a_metric_key():
    # If a target is dropped from the harness this test is what notices.
    assert set(ba.REQUIRED_METRICS) == {
        "answer_card",
        "next_card",
        "dashboard_load",
        "dashboard_refresh",
        "sync_session",
        "memory_rss",
        "cold_start",
        "ui_block",
    }


def test_report_refuses_to_omit_a_required_target():
    with pytest.raises(ValueError):
        ba.check_coverage([ba.Metric("answer_card", "answer card", 50.0, [1.0])])


def test_report_accepts_a_full_set_even_if_some_are_skipped():
    metrics = [
        ba.Metric.skipped(key, key, 1.0, "not run") for key in ba.REQUIRED_METRICS
    ]
    ba.check_coverage(metrics)  # must not raise
