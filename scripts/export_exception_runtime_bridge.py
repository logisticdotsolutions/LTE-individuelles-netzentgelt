"""Runtime bridge for controlled export release with documented exceptions."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from export_exception_query_module import _current_run_id, list_required_export_blockers_from_connection
from export_exception_state_module import evaluate_release_status, record_export_release
from local_auth_module import DEFAULT_DB_PATH, UserContext


PHASE9C_EXCEPTION_RUNTIME_MARKER = "NETZENTGELT_EXPORT_EXCEPTION_RUNTIME_PHASE9C_V2_20260610"


def _release_status(con, performing_ru_values, date_from, date_to):
    blockers = list_required_export_blockers_from_connection(
        con=con,
        performing_ru_values=performing_ru_values,
        date_from=date_from,
        date_to=date_to,
    )
    return evaluate_release_status(blockers, DEFAULT_DB_PATH)


def _missing_message(status) -> str:
    examples = ", ".join(item.label() for item in status.missing_blockers[:5]) or "-"
    return (
        "Export ist noch gesperrt. Für jeden blockierenden Root-Fehler muss zuerst "
        "eine fachliche Ausnahme mit Begründung dokumentiert werden. "
        f"Fehlende Ausnahmen: {len(status.missing_blockers)}. Beispiele: {examples}"
    )


def _status_and_run_id(db_path, ru_values, date_from, date_to):
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        run_id = _current_run_id(con)
        status = _release_status(con, ru_values, date_from, date_to)
    finally:
        con.close()
    return status, run_id


@contextmanager
def export_exception_runtime(user: UserContext) -> Iterator[None]:
    """Patch the existing export gate and record prepared XLSX releases."""
    import export_module

    original_gate = export_module._assert_export_gate_ready
    original_build_nutzung = export_module.build_nutzungsmeldung_xlsx
    original_build_aufenthalt = export_module.build_aufenthaltsereignis_xlsx

    def exception_aware_gate(con, performing_ru_values, date_from, date_to):
        status = _release_status(con, performing_ru_values, date_from, date_to)
        if status.released:
            return None
        raise RuntimeError(_missing_message(status))

    def audited_build_nutzung(*args: Any, **kwargs: Any):
        result = original_build_nutzung(*args, **kwargs)
        db_path = kwargs.get("db_path", args[0] if args else None)
        ru_values = kwargs.get("performing_ru_values", args[1] if len(args) > 1 else ())
        export_label = kwargs.get("export_label", args[2] if len(args) > 2 else "")
        date_from = kwargs.get("date_from", args[3] if len(args) > 3 else None)
        date_to = kwargs.get("date_to", args[4] if len(args) > 4 else None)
        status, run_id = _status_and_run_id(db_path, ru_values, date_from, date_to)
        record_export_release(
            actor=user,
            export_kind="NUTZUNGSMELDUNG",
            export_label=str(export_label),
            date_from=date_from,
            date_to=date_to,
            file_name=result.file_name,
            content=result.content,
            exception_ids=status.active_exception_ids,
            run_id=run_id,
            db_path=DEFAULT_DB_PATH,
        )
        return result

    def audited_build_aufenthalt(*args: Any, **kwargs: Any):
        result = original_build_aufenthalt(*args, **kwargs)
        db_path = kwargs.get("db_path", args[0] if args else None)
        ru_values = kwargs.get("performing_ru_values", args[1] if len(args) > 1 else ())
        export_label = kwargs.get("export_label", args[2] if len(args) > 2 else "")
        date_from = kwargs.get("date_from", args[3] if len(args) > 3 else None)
        date_to = kwargs.get("date_to", args[4] if len(args) > 4 else None)
        status, run_id = _status_and_run_id(db_path, ru_values, date_from, date_to)
        record_export_release(
            actor=user,
            export_kind="AUFENTHALTSEREIGNIS",
            export_label=str(export_label),
            date_from=date_from,
            date_to=date_to,
            file_name=result.file_name,
            content=result.content,
            exception_ids=status.active_exception_ids,
            run_id=run_id,
            db_path=DEFAULT_DB_PATH,
        )
        return result

    export_module._assert_export_gate_ready = exception_aware_gate
    export_module.build_nutzungsmeldung_xlsx = audited_build_nutzung
    export_module.build_aufenthaltsereignis_xlsx = audited_build_aufenthalt
    try:
        yield
    finally:
        export_module._assert_export_gate_ready = original_gate
        export_module.build_nutzungsmeldung_xlsx = original_build_nutzung
        export_module.build_aufenthaltsereignis_xlsx = original_build_aufenthalt
