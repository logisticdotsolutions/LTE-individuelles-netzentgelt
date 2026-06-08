from __future__ import annotations

import json
from pathlib import Path

import duckdb


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def patch_pipeline_paths(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    import export_module
    import manual_override_module
    import run_all

    root = tmp_path / "isolated_project"
    raw = root / "data" / "00_raw"
    mapping = root / "data" / "01_mapping"
    duckdb_dir = root / "data" / "02_duckdb"
    exports = root / "data" / "03_exports"
    logs = root / "data" / "04_logs"
    templates = root / "data" / "05_templates"
    for path in (raw, mapping, duckdb_dir, exports, logs, templates):
        path.mkdir(parents=True, exist_ok=True)

    values = {
        "ROOT": root,
        "RAW_DIR": raw,
        "MAP_DIR": mapping,
        "DB_DIR": duckdb_dir,
        "EXP_DIR": exports,
        "LOG_DIR": logs,
        "RAW_IMPORT_MANIFEST_PATH": raw / "raw_import_manifest.json",
        "DB_PATH": duckdb_dir / "netzentgelt.duckdb",
        "DB_BUILD_PATH": duckdb_dir / "netzentgelt_build.duckdb",
    }
    for name, value in values.items():
        monkeypatch.setattr(run_all, name, value)
    monkeypatch.setattr(export_module, "EXP_DIR", exports)
    monkeypatch.setattr(export_module, "TEMPLATE_DIR", templates)
    monkeypatch.setattr(manual_override_module, "ROOT", root)
    monkeypatch.setattr(manual_override_module, "MAP_DIR", mapping)
    monkeypatch.setattr(manual_override_module, "MANUAL_OVERRIDE_PATH", mapping / "manual_overrides.csv")
    return values | {"TEMPLATE_DIR": templates}


def write_minimal_fixture(paths: dict[str, Path]) -> None:
    raw = paths["RAW_DIR"]
    mapping = paths["MAP_DIR"]
    write_text(
        raw / "LocomotiveMovement.csv",
        "LocomotiveNo;LocomotiveHolder;CurrentContractant;TractionType;OriginCountryISO;DestinationCountryISO;ActualDeparture;ActualArrival;LocomotiveOriginLocationName;LocomotiveDestinationLocationName;TransportNumber;TrainNo\n"
        "91800000001-1;Holder GmbH;RU GmbH;electric;DE;DE;2026-06-01T10:00:00;2026-06-01T11:00:00;Berlin;Hamburg;TR-SMOKE;TN-SMOKE\n",
    )
    write_text(
        raw / "TransportDetail.csv",
        "TransportNumber;TransportStatus;SequenceID;OriginCountryISO;DestinationCountryISO;ActualDeparture;ActualArrival;FirstLocomotiveNo;MovementType\n"
        "TR-SMOKE;Planned;1;DE;DE;2026-06-01T10:00:00;2026-06-01T11:00:00;91800000001-1;Train movement\n",
    )
    write_text(raw / "Locomotive.csv", "LocomotiveNo\n91800000001-1\n")
    write_text(
        mapping / "loco_mapping.csv",
        "loco_no;tfze_or_tens;halter_name;halter_marktpartner_id;default_vens;valid_from_utc;valid_to_utc;priority;source;comment;active_flag\n"
        "91800000001-1;91800000001-1;Holder GmbH;;VENS-RU;;;;fixture;;Y\n",
    )
    (raw / "raw_import_manifest.json").write_text(
        json.dumps({"schema_version": 1, "snapshot_at_utc": "2026-06-08T12:00:00Z", "files": []}, indent=2) + "\n",
        encoding="utf-8",
    )


def run_isolated_pipeline(monkeypatch, tmp_path: Path) -> tuple[dict[str, Path], dict[str, int]]:
    import run_all

    paths = patch_pipeline_paths(monkeypatch, tmp_path)
    write_minimal_fixture(paths)
    run_all.main()
    db_path = paths["DB_PATH"]
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        metrics = {
            "raw_locomotivemovement_rows": con.execute("select count(*) from raw_locomotivemovement").fetchone()[0],
            "staging_event_rows": con.execute("select count(*) from stg_loco_events").fetchone()[0],
            "timeline_movement_rows": con.execute("select count(*) from core_loco_timeline where row_type='MOVEMENT'").fetchone()[0],
            "timeline_gap_rows": con.execute("select count(*) from core_loco_timeline where row_type='GAP'").fetchone()[0],
            "findings_rows": con.execute("select count(*) from dq_findings").fetchone()[0],
            "export_zuordnungen_rows": con.execute("select count(*) from export_zuordnungen").fetchone()[0],
            "export_nutzungsmeldung_rows": con.execute("select count(*) from export_nutzungsmeldung").fetchone()[0],
            "ready_gate_rows": con.execute("select count(*) from dq_export_gate where gate_status='READY'").fetchone()[0],
        }
    finally:
        con.close()
    return paths, metrics
