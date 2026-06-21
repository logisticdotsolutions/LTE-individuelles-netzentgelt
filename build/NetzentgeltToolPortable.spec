# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

# PyInstaller resolves script paths relative to the spec file location.
# Therefore use the repository root explicitly instead of relying on a relative
# script name like "portable_launcher.py", which would be searched below build/.
ROOT = Path(__file__).resolve().parents[1]
PORTABLE_LAUNCHER = ROOT / "portable_launcher.py"


def data_if_exists(path: str, target: str | None = None):
    source = ROOT / path
    if source.exists():
        return [(str(source), target or path)]
    return []


if not PORTABLE_LAUNCHER.exists():
    raise SystemExit(f"Portable Launcher fehlt: {PORTABLE_LAUNCHER}")


datas = []
datas += data_if_exists("app", "app")
datas += data_if_exists("scripts", "scripts")
datas += data_if_exists("config/portable_runtime.enc", "config")
datas += data_if_exists("config/portable_runtime.key", "config")
datas += data_if_exists("data/01_mapping", "data/01_mapping")
datas += data_if_exists("data/06_pic", "data/06_pic")

hiddenimports = [
    "streamlit.web.cli",
    "streamlit.runtime.scriptrunner.script_run_context",
    "streamlit.runtime.scriptrunner_utils.script_run_context",
    "cryptography.fernet",
    "duckdb",
    "openpyxl",
    "yaml",
]


a = Analysis(
    [str(PORTABLE_LAUNCHER)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NetzentgeltTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NetzentgeltTool",
)
