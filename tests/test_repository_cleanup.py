from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_obsolete_historical_installer_tests_are_removed() -> None:
    obsolete = [
        ROOT / "tests" / "test_installer_phase6b.py",
        ROOT / "tests" / "test_installer_phase6c.py",
        ROOT / "tests" / "test_rule_engine_diagnostic_phase6a.py",
        ROOT / "tests" / "fixtures" / "rule_engine_diagnostic_phase6a.py",
        ROOT / "tests" / "fixture_rule_engine_diagnostic_phase6a.py",
    ]

    assert all(not path.exists() for path in obsolete)


def test_current_runtime_entrypoints_remain_present() -> None:
    required = [
        ROOT / "app" / "secure_app.py",
        ROOT / "scripts" / "run_all.py",
        ROOT / "scripts" / "operator_workflow_runtime_bridge.py",
        ROOT / "scripts" / "operator_workflow_activation_module.py",
        ROOT / "scripts" / "active_override_id_runtime_module.py",
        ROOT / "scripts" / "technical_loco_fallback_runtime_module.py",
    ]

    assert all(path.exists() for path in required)
