from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ae01_hardened_runtime_bridge as ae01
import export_module
import n01_hardened_runtime_bridge as n01
import zuordnungen_hardened_runtime_bridge as z01
import zuordnungen_ui_runtime_bridge as z01_ui


def test_n01_runtime_switches_and_restores_builder():
    original = export_module.build_nutzungsmeldung_xlsx
    runtime = n01.install_n01_hardened_runtime()
    try:
        assert export_module.build_nutzungsmeldung_xlsx is n01.build_hardened_n01_xlsx
    finally:
        n01.restore_n01_hardened_runtime(runtime)
    assert export_module.build_nutzungsmeldung_xlsx is original


def test_ae01_runtime_switches_and_restores_builder():
    original = export_module.build_aufenthaltsereignis_xlsx
    runtime = ae01.install_ae01_hardened_runtime()
    try:
        assert export_module.build_aufenthaltsereignis_xlsx is ae01.build_hardened_aufenthaltsereignis_xlsx
    finally:
        ae01.restore_ae01_hardened_runtime(runtime)
    assert export_module.build_aufenthaltsereignis_xlsx is original


def test_z01_runtime_switches_and_restores_export_and_preview():
    original_export = z01_ui.build_zuordnungen_holding_xlsx
    original_preview = z01_ui.build_zuordnungen_holding_preview
    runtime = z01.install_zuordnungen_hardened_runtime()
    try:
        assert z01_ui.build_zuordnungen_holding_xlsx is z01.build_hardened_zuordnungen_holding_xlsx
        assert z01_ui.build_zuordnungen_holding_preview is z01.build_hardened_zuordnungen_holding_preview
    finally:
        z01.restore_zuordnungen_hardened_runtime(runtime)
    assert z01_ui.build_zuordnungen_holding_xlsx is original_export
    assert z01_ui.build_zuordnungen_holding_preview is original_preview
