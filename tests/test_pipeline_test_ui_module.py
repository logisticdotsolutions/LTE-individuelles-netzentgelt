from __future__ import annotations

from pathlib import Path

from pipeline_test_ui_module import (
    TestCaseResult as CaseResult,
    latest_report_dir,
    parse_junit_report,
    read_warning_rows,
    summarize_tests,
)


def test_parse_junit_report_returns_individual_statuses(tmp_path: Path):
    report = tmp_path / "pytest-junit.xml"
    report.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
<testsuites><testsuite name='pytest'>
  <testcase classname='tests.test_demo' name='test_passed' time='0.10'/>
  <testcase classname='tests.test_demo' name='test_failed' time='0.20'><failure message='kaputt'>trace</failure></testcase>
  <testcase classname='tests.test_demo' name='test_skipped' time='0'><skipped message='spaeter'/></testcase>
</testsuite></testsuites>
""",
        encoding="utf-8",
    )
    rows = parse_junit_report(report)
    assert [row.status for row in rows] == ["PASSED", "FAILED", "SKIPPED"]
    assert rows[1].test_id == "tests.test_demo::test_failed"
    assert "kaputt" in rows[1].message


def test_summarize_tests_counts_pass_fail_error_skip_and_warnings():
    rows = [
        CaseResult("PASSED", "a", "", "a", 0.0, ""),
        CaseResult("FAILED", "b", "", "b", 0.0, "x"),
        CaseResult("ERROR", "c", "", "c", 0.0, "x"),
        CaseResult("SKIPPED", "d", "", "d", 0.0, ""),
    ]
    summary = summarize_tests(rows, [{"code": "W1"}])
    assert (summary.total, summary.passed, summary.failed, summary.errors, summary.skipped, summary.warnings) == (4, 1, 1, 1, 1, 1)
    assert summary.successful is False


def test_read_warning_rows_handles_contract_and_invalid_json(tmp_path: Path):
    valid = tmp_path / "warnings.json"
    valid.write_text('{"warnings":[{"code":"W1","message":"offen"}]}', encoding="utf-8")
    assert read_warning_rows(valid) == [{"code": "W1", "message": "offen"}]
    invalid = tmp_path / "broken.json"
    invalid.write_text('{', encoding="utf-8")
    rows = read_warning_rows(invalid)
    assert rows[0]["code"] == "W000_WARNING_REPORT_UNREADABLE"


def test_latest_report_dir_returns_latest_timestamp_folder(tmp_path: Path):
    root = tmp_path / "_test_reports"
    (root / "20260608T100000Z").mkdir(parents=True)
    (root / "20260608T110000Z").mkdir()
    assert latest_report_dir(tmp_path).name == "20260608T110000Z"
