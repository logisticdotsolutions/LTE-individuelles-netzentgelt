from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import vens_selection_store as module


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8-sig")


def test_candidates_are_filtered_by_performing_ru_and_user_type(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    _write(
        catalog,
        "communication_partner;vens_type;user_vens;market_location_feed_in;market_location_consumption;source;comment;active_flag\n"
        "LTE Germany GmbH;NUTZER;VENS-DE-1;FEED-1;CONS-1;PORTAL;;Y\n"
        "LTE Germany GmbH;BASIS;VENS-DE-BASE;FEED-2;CONS-2;PORTAL;;Y\n"
        "LTE Netherlands B.V.;NUTZER;VENS-NL-1;FEED-3;CONS-3;PORTAL;;Y\n",
    )

    result = module.candidates_for_performing_ru(
        "LTE DE - LTE Germany GmbH",
        path=catalog,
    )

    assert [row["user_vens"] for row in result] == ["VENS-DE-1"]
    assert "Entnahme CONS-1" in module.candidate_label(result[0])


def test_save_mapping_writes_row_and_returns_unchanged_for_duplicate(monkeypatch, tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.csv"
    log = tmp_path / "mapping_change_log.csv"
    backup = tmp_path / "backups"
    monkeypatch.setattr(module, "LOG_PATH", log)
    monkeypatch.setattr(module, "BACKUP_DIR", backup)

    kwargs = {
        "performing_ru": "LTE DE - LTE Germany GmbH",
        "user_vens": "VENS-DE-1",
        "valid_from_utc": "2026-06-12T08:00:00Z",
        "valid_to_utc": "2026-06-12T10:00:00Z",
        "priority": 10,
        "changed_by": "tester",
        "comment": "fachlich geprüft",
        "mapping_path": mapping,
    }

    assert module.save_mapping(**kwargs) == "CREATED"
    assert module.save_mapping(**kwargs) == "UNCHANGED"

    rows = module._read(mapping, module.MAPPING_COLUMNS)
    assert len(rows) == 1
    assert rows[0]["user_vens"] == "VENS-DE-1"
    assert rows[0]["priority"] == "10"
    assert log.exists()


def test_save_mapping_requires_comment(tmp_path: Path) -> None:
    try:
        module.save_mapping(
            performing_ru="LTE DE - LTE Germany GmbH",
            user_vens="VENS-DE-1",
            valid_from_utc="2026-06-12T08:00:00Z",
            valid_to_utc="",
            priority=100,
            changed_by="tester",
            comment="",
            mapping_path=tmp_path / "mapping.csv",
        )
    except ValueError as error:
        assert "Begründung" in str(error)
    else:
        raise AssertionError("ValueError erwartet")
