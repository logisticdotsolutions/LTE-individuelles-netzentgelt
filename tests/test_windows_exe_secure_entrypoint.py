from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_exe_build_uses_portable_entrypoint_by_default():
    build_script = (ROOT / "BUILD_WINDOWS_EXE.ps1").read_text(encoding="utf-8")

    assert '[string]$EntryPoint = "app\\secure_app_portable.py"' in build_script
    assert '[string]$EntryPoint = "app\\app.py"' not in build_script


def test_packaged_entrypoint_config_points_to_portable_entrypoint():
    entrypoint = (ROOT / "packaging" / "netzentgelt_entrypoint.txt").read_text(
        encoding="utf-8-sig"
    ).strip().replace("/", "\\")

    assert entrypoint == "app\\secure_app_portable.py"
