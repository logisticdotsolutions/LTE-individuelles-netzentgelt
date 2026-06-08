from __future__ import annotations

"""
Netzentgelt MVP - technischer Pipeline- und Testcontroller fuer Streamlit.

Die UI-Schicht startet vorhandene Skripte bewusst nur synchron und zeigt die
Ergebnisse anschliessend nachvollziehbar an. Die eigentliche Fachlogik bleibt in
run_all.py und RUN_TESTS.bat. Tests verwenden weiterhin ausschliesslich Fixtures
und temporaere DuckDB-Dateien.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Iterable, Sequence
import xml.etree.ElementTree as ET

PHASE_ID = "NETZENTGELT_PIPELINE_TEST_UI_PHASE7B_V1_20260608"
MODE_TESTS_ONLY = "TESTS_ONLY"
MODE_PIPELINE_AND_TESTS = "PIPELINE_AND_TESTS"
MODE_FULL_REFRESH_AND_TESTS = "FULL_REFRESH_AND_TESTS"
MODE_LABELS = {
    MODE_TESTS_ONLY: "Nur Tests ausfuehren",
    MODE_PIPELINE_AND_TESTS: "Pipeline neu berechnen und Tests ausfuehren",
    MODE_FULL_REFRESH_AND_TESTS: "Azure-Download, Pipeline und Tests ausfuehren",
}


@dataclass(frozen=True)
class CommandResult:
    label: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    started_at_utc: str
    finished_at_utc: str
    duration_seconds: float

    @property
    def passed(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class TestCaseResult:
    status: str
    test_id: str
    classname: str
    name: str
    duration_seconds: float
    message: str


@dataclass(frozen=True)
class TestSummary:
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    warnings: int

    @property
    def successful(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.total > 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_dir() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%SZ")


def _short_message(element: ET.Element | None) -> str:
    if element is None:
        return ""
    parts = [str(element.attrib.get("message", "")).strip(), str(element.text or "").strip()]
    return "\n".join(part for part in parts if part).strip()


def parse_junit_report(path: Path) -> list[TestCaseResult]:
    """JUnit-XML robust in eine UI-taugliche Einzeltestliste ueberfuehren."""
    path = Path(path)
    if not path.is_file():
        return []
    root = ET.parse(path).getroot()
    rows: list[TestCaseResult] = []
    for case in root.iter("testcase"):
        classname = str(case.attrib.get("classname", "")).strip()
        name = str(case.attrib.get("name", "")).strip()
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            status = "FAILED"
            message = _short_message(failure)
        elif error is not None:
            status = "ERROR"
            message = _short_message(error)
        elif skipped is not None:
            status = "SKIPPED"
            message = _short_message(skipped)
        else:
            status = "PASSED"
            message = ""
        try:
            duration = float(case.attrib.get("time", 0) or 0)
        except (TypeError, ValueError):
            duration = 0.0
        test_id = f"{classname}::{name}" if classname else name
        rows.append(
            TestCaseResult(
                status=status,
                test_id=test_id,
                classname=classname,
                name=name,
                duration_seconds=round(duration, 4),
                message=message,
            )
        )
    return rows


def read_warning_rows(path: Path) -> list[dict]:
    """WARNING-Vertrag aus warnings.json lesen; defekte Berichte werden sichtbar."""
    path = Path(path)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [{"code": "W000_WARNING_REPORT_UNREADABLE", "message": str(exc)}]
    rows = payload.get("warnings", []) if isinstance(payload, dict) else []
    return [row if isinstance(row, dict) else {"message": str(row)} for row in rows]


def summarize_tests(cases: Iterable[TestCaseResult], warnings: Iterable[dict] = ()) -> TestSummary:
    rows = list(cases)
    warning_rows = list(warnings)
    return TestSummary(
        total=len(rows),
        passed=sum(row.status == "PASSED" for row in rows),
        failed=sum(row.status == "FAILED" for row in rows),
        skipped=sum(row.status == "SKIPPED" for row in rows),
        errors=sum(row.status == "ERROR" for row in rows),
        warnings=len(warning_rows),
    )


def latest_report_dir(base_dir: Path) -> Path | None:
    root = Path(base_dir) / "_test_reports"
    candidates = sorted((path for path in root.glob("*") if path.is_dir()), reverse=True)
    return candidates[0] if candidates else None


def run_command(label: str, command: Sequence[str], cwd: Path) -> CommandResult:
    """Einen technischen Schritt synchron und mit vollstaendigem Audit-Output starten."""
    started = _utc_now()
    try:
        completed = subprocess.run(
            [str(value) for value in command],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        returncode = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except Exception as exc:  # UI muss auch Startfehler transparent darstellen.
        returncode = 999
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
    finished = _utc_now()
    return CommandResult(
        label=label,
        command=[str(value) for value in command],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        started_at_utc=_utc_text(started),
        finished_at_utc=_utc_text(finished),
        duration_seconds=round((finished - started).total_seconds(), 3),
    )


def _test_command(base_dir: Path, fast: bool) -> list[str]:
    runner = Path(base_dir) / "RUN_TESTS.bat"
    if os.name == "nt":
        command = ["cmd.exe", "/d", "/c", str(runner)]
    else:
        # Nur fuer Entwicklungs- und Parser-Tests ausserhalb von Windows.
        command = [str(runner)]
    if fast:
        command.append("-Fast")
    return command


def _python_command(script: Path) -> list[str]:
    return [sys.executable, str(script)]


def _persist_controller_summary(
    report_dir: Path,
    *,
    mode: str,
    steps: list[CommandResult],
    cases: list[TestCaseResult],
    warnings: list[dict],
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_tests(cases, warnings)
    payload = {
        "phase_id": PHASE_ID,
        "created_at_utc": _utc_text(_utc_now()),
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "steps": [asdict(row) | {"passed": row.passed} for row in steps],
        "test_summary": asdict(summary) | {"successful": summary.successful},
        "tests": [asdict(row) for row in cases],
        "warnings": warnings,
    }
    output = report_dir / "ui-controller-summary.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def execute_controller_run(
    *,
    base_dir: Path,
    script_download_blob: Path,
    script_run_all: Path,
    mode: str,
    fast_tests: bool = False,
    on_step_start: Callable[[str], None] | None = None,
    on_step_complete: Callable[[CommandResult], None] | None = None,
) -> dict:
    """Pipeline- und Testschritte sequentiell ausfuehren; bei Fehler sicher stoppen."""
    base_dir = Path(base_dir)
    if mode not in MODE_LABELS:
        raise ValueError(f"Unbekannter Controller-Modus: {mode}")
    steps: list[CommandResult] = []
    report_root = base_dir / "_test_reports"
    reports_before_tests = {path.resolve() for path in report_root.glob("*") if path.is_dir()}

    def execute(label: str, command: Sequence[str]) -> CommandResult:
        if on_step_start:
            on_step_start(label)
        row = run_command(label, command, base_dir)
        steps.append(row)
        if on_step_complete:
            on_step_complete(row)
        return row

    if mode == MODE_FULL_REFRESH_AND_TESTS:
        if not Path(script_download_blob).is_file():
            raise FileNotFoundError(f"Download-Skript fehlt: {script_download_blob}")
        if not execute("Azure-Rohdaten laden", _python_command(Path(script_download_blob))).passed:
            return _finalize_result(base_dir, mode, steps, report_dir=None)

    if mode in {MODE_PIPELINE_AND_TESTS, MODE_FULL_REFRESH_AND_TESTS}:
        if not Path(script_run_all).is_file():
            raise FileNotFoundError(f"Pipeline-Skript fehlt: {script_run_all}")
        if not execute("DuckDB und Exporte neu berechnen", _python_command(Path(script_run_all))).passed:
            return _finalize_result(base_dir, mode, steps, report_dir=None)

    runner = base_dir / "RUN_TESTS.bat"
    if not runner.is_file():
        raise FileNotFoundError(f"Test-Startskript fehlt: {runner}")
    execute("Automatisierte Testsuite ausfuehren", _test_command(base_dir, fast_tests))
    reports_after_tests = {path.resolve() for path in report_root.glob("*") if path.is_dir()}
    new_reports = sorted(reports_after_tests - reports_before_tests, reverse=True)
    current_report_dir = new_reports[0] if new_reports else None
    return _finalize_result(base_dir, mode, steps, report_dir=current_report_dir)


def _finalize_result(base_dir: Path, mode: str, steps: list[CommandResult], report_dir: Path | None) -> dict:
    if report_dir is None:
        report_dir = Path(base_dir) / "_test_reports" / f"ui_{_timestamp_dir()}"
    cases = parse_junit_report(report_dir / "pytest-junit.xml")
    warnings = read_warning_rows(report_dir / "warnings.json")
    summary = summarize_tests(cases, warnings)
    summary_path = _persist_controller_summary(
        report_dir,
        mode=mode,
        steps=steps,
        cases=cases,
        warnings=warnings,
    )
    return {
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "steps": steps,
        "report_dir": report_dir,
        "summary_path": summary_path,
        "tests": cases,
        "warnings": warnings,
        "summary": summary,
        "successful": bool(steps) and all(row.passed for row in steps) and summary.successful,
    }


def load_latest_test_result(base_dir: Path) -> dict | None:
    report_dir = latest_report_dir(base_dir)
    if report_dir is None:
        return None
    cases = parse_junit_report(report_dir / "pytest-junit.xml")
    warnings = read_warning_rows(report_dir / "warnings.json")
    if not cases and not warnings:
        return None
    return {
        "mode": "LAST_REPORT",
        "mode_label": "Letzter vorhandener Testbericht",
        "steps": [],
        "report_dir": report_dir,
        "summary_path": report_dir / "ui-controller-summary.json",
        "tests": cases,
        "warnings": warnings,
        "summary": summarize_tests(cases, warnings),
        "successful": summarize_tests(cases, warnings).successful,
    }


def _render_download(st, path: Path, label: str, key: str, mime: str) -> None:
    if Path(path).is_file():
        st.download_button(
            label,
            data=Path(path).read_bytes(),
            file_name=Path(path).name,
            mime=mime,
            key=key,
            use_container_width=True,
        )


def _render_result(st, result: dict) -> None:
    summary: TestSummary = result["summary"]
    if result["successful"]:
        st.success("PASS: Pipeline-Schritte und ausgefuehrte Tests sind erfolgreich.")
    else:
        st.error("FAIL: Mindestens ein technischer Schritt oder Test ist fehlgeschlagen.")

    metric_cols = st.columns(6)
    values = [
        ("Tests gesamt", summary.total),
        ("PASSED", summary.passed),
        ("FAILED", summary.failed),
        ("ERROR", summary.errors),
        ("SKIPPED", summary.skipped),
        ("WARNING", summary.warnings),
    ]
    for column, (label, value) in zip(metric_cols, values):
        column.metric(label, value)

    if result.get("steps"):
        st.markdown("#### Ausgefuehrte technische Schritte")
        for index, step in enumerate(result["steps"], start=1):
            icon = "✅" if step.passed else "❌"
            with st.expander(
                f"{icon} {index}. {step.label} ({step.duration_seconds:.2f} s)",
                expanded=not step.passed,
            ):
                st.code(" ".join(step.command), language="powershell")
                if step.stdout.strip():
                    st.text_area("Output", step.stdout, height=180, key=f"ui_step_out_{index}_{step.started_at_utc}")
                if step.stderr.strip():
                    st.text_area("Fehler", step.stderr, height=180, key=f"ui_step_err_{index}_{step.started_at_utc}")

    if result.get("warnings"):
        st.markdown("#### WARNING-Vertraege")
        for row in result["warnings"]:
            code = str(row.get("code", "WARNING")).strip()
            message = str(row.get("message", row)).strip()
            st.warning(f"{code}: {message}")

    st.markdown("#### Einzeltests")
    tests = result.get("tests", [])
    if not tests:
        st.warning("Kein auswertbarer JUnit-Einzeltestbericht gefunden.")
    else:
        import pandas as pd

        status_icon = {"PASSED": "✅", "FAILED": "❌", "ERROR": "❌", "SKIPPED": "⏭️"}
        rows = [
            {
                "Status": f"{status_icon.get(row.status, '⚪')} {row.status}",
                "Test": row.test_id,
                "Dauer (s)": row.duration_seconds,
                "Fehlermeldung": row.message,
            }
            for row in tests
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        failed = [row for row in tests if row.status in {"FAILED", "ERROR"}]
        if failed:
            st.markdown("#### Fehlerdetails")
            for index, row in enumerate(failed, start=1):
                with st.expander(f"❌ {row.test_id}", expanded=True):
                    st.code(row.message or "Keine Detailmeldung im JUnit-Bericht.")

    report_dir = Path(result["report_dir"])
    st.caption(f"Berichtsordner: {report_dir}")
    download_cols = st.columns(4)
    with download_cols[0]:
        _render_download(st, report_dir / "pytest-report.html", "HTML-Bericht", "ui_download_html", "text/html")
    with download_cols[1]:
        _render_download(st, report_dir / "pytest-junit.xml", "JUnit-Bericht", "ui_download_junit", "application/xml")
    with download_cols[2]:
        _render_download(st, report_dir / "pytest-console.txt", "Konsolenausgabe", "ui_download_console", "text/plain")
    with download_cols[3]:
        _render_download(st, Path(result["summary_path"]), "UI-Zusammenfassung", "ui_download_summary", "application/json")


def render_pipeline_test_controller(*, base_dir: Path, script_download_blob: Path, script_run_all: Path) -> None:
    """Streamlit-Oberflaeche fuer kontrollierte Pipeline- und Testlaeufe."""
    import streamlit as st

    st.subheader("Technischer Pipeline- und Testcontroller")
    st.caption(
        "Die vollstaendige Testsuite verwendet Fixtures und temporaere DuckDB-Dateien. "
        "Produktive Rohdaten oder produktive DuckDB-Dateien werden durch die Tests nicht veraendert. "
        "Die beiden Pipeline-Aktionen fuehren dagegen bewusst den produktiven Tageslauf aus."
    )
    st.info(
        "Die Suite deckt die definierten fachlichen Anforderungen R001 bis R016 sowie die vereinbarten "
        "Pipeline-, Schema-, Export-, Override- und Regressionstests ab. Eine fachliche Vollabdeckung "
        "ist nicht dasselbe wie 100 Prozent Quellcode-Zeilenabdeckung; die Einzeltests bleiben deshalb sichtbar."
    )
    fast_tests = st.checkbox(
        "Schnelltest verwenden (Smoke- und Regressionstests auslassen)",
        value=False,
        key="pipeline_test_ui_fast",
    )
    col_tests, col_pipeline, col_full = st.columns(3)
    selected_mode: str | None = None
    with col_tests:
        if st.button("Nur Tests starten", use_container_width=True, key="pipeline_test_ui_tests"):
            selected_mode = MODE_TESTS_ONLY
    with col_pipeline:
        if st.button("Pipeline + Tests", use_container_width=True, key="pipeline_test_ui_pipeline"):
            selected_mode = MODE_PIPELINE_AND_TESTS
    with col_full:
        if st.button(
            "Azure-Download + Pipeline + Tests",
            type="primary",
            use_container_width=True,
            key="pipeline_test_ui_full",
        ):
            selected_mode = MODE_FULL_REFRESH_AND_TESTS

    if selected_mode:
        with st.status("Technischer Lauf wurde gestartet ...", expanded=True) as status:
            def on_start(label: str) -> None:
                st.write(f"⏳ {label}")

            def on_complete(step: CommandResult) -> None:
                icon = "✅" if step.passed else "❌"
                st.write(f"{icon} {step.label} ({step.duration_seconds:.2f} s)")

            result = execute_controller_run(
                base_dir=Path(base_dir),
                script_download_blob=Path(script_download_blob),
                script_run_all=Path(script_run_all),
                mode=selected_mode,
                fast_tests=fast_tests,
                on_step_start=on_start,
                on_step_complete=on_complete,
            )
            st.session_state["pipeline_test_ui_last_result"] = result
            status.update(
                label="Technischer Lauf abgeschlossen." if result["successful"] else "Technischer Lauf mit Fehlern abgeschlossen.",
                state="complete" if result["successful"] else "error",
                expanded=not result["successful"],
            )

    result = st.session_state.get("pipeline_test_ui_last_result")
    if result is None:
        result = load_latest_test_result(Path(base_dir))
    if result is not None:
        st.divider()
        st.markdown(f"### Ergebnis: {result['mode_label']}")
        _render_result(st, result)
    else:
        st.info("Noch kein Testbericht gefunden. Starte zuerst einen Testlauf.")
