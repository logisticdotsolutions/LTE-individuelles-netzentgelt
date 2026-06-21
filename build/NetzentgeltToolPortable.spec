# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path.cwd()


def data_if_exists(path: str, target: str | None = None):
    source = ROOT / path
    if source.exists():
        return [(str(source), target or path)]
    return []


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
    ["portable_launcher.py"],
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
