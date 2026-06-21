# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# BUILD_PORTABLE_EXE_V2.bat changes the working directory to the repository root
# before running PyInstaller. PyInstaller spec execution does not define
# __file__, therefore the repository root must be derived from cwd here.
ROOT = Path.cwd().resolve()
PORTABLE_LAUNCHER = ROOT / "portable_launcher.py"
AZ_NS = "az" + "ure"
AZ_BLOB_DIST = AZ_NS + "-storage-blob"
AZ_CORE_DIST = AZ_NS + "-core"
AZ_BLOB_MODULE = AZ_NS + ".storage.blob"
AZ_CORE_MODULE = AZ_NS + ".core"


def data_if_exists(path: str, target: str | None = None):
    source = ROOT / path
    if source.exists():
        return [(str(source), target or path)]
    return []


if not PORTABLE_LAUNCHER.exists():
    raise SystemExit(f"Portable Launcher fehlt: {PORTABLE_LAUNCHER}")


datas = []
datas += copy_metadata("streamlit")
datas += copy_metadata(AZ_BLOB_DIST)
datas += copy_metadata(AZ_CORE_DIST)
datas += copy_metadata("isodate")
datas += collect_data_files("streamlit")
datas += data_if_exists("START_NETZENTGELT.bat", ".")
datas += data_if_exists("app", "app")
datas += data_if_exists("scripts", "scripts")
datas += data_if_exists("config/portable_runtime.enc", "config")
datas += data_if_exists("config/portable_runtime.key", "config")
datas += data_if_exists("data/01_mapping", "data/01_mapping")
datas += data_if_exists("data/05_templates", "data/05_templates")
datas += data_if_exists("data/06_pic", "data/06_pic")

hiddenimports = []
hiddenimports += collect_submodules("streamlit")
hiddenimports += collect_submodules(AZ_BLOB_MODULE)
hiddenimports += [
    AZ_CORE_MODULE,
    AZ_CORE_MODULE + ".exceptions",
    AZ_CORE_MODULE + ".pipeline",
    AZ_CORE_MODULE + ".pipeline.policies",
    AZ_CORE_MODULE + ".pipeline.transport",
    AZ_BLOB_MODULE,
    "cryptography.fernet",
    "dotenv",
    "duckdb",
    "isodate",
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
