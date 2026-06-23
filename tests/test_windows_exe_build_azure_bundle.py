from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "BUILD_WINDOWS_EXE.ps1"
REQUIREMENTS = ROOT / "requirements.txt"


def test_runtime_requirements_include_azure_storage_blob() -> None:
    requirements_text = REQUIREMENTS.read_text(encoding="utf-8").lower()

    assert "azure-storage-blob" in requirements_text


def test_windows_exe_build_collects_azure_namespace_packages() -> None:
    build_script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "'--hidden-import', 'azure.storage.blob'" in build_script
    assert "'azure.core'" in build_script
    assert "'azure.storage'" in build_script
    assert "'azure.storage.blob'" in build_script
    assert "'dotenv'" in build_script
