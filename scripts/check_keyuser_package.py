from __future__ import annotations

from pathlib import Path
import argparse
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = ROOT / "_release"

NEEDED = [
    "NetzentgeltMVP.exe",
    "START_HIER.txt",
    "app/secure_app.py",
    "app/secure_app_portable.py",
    "packaging/netzentgelt_entrypoint.txt",
    "scripts/download_blob_data.py",
    "scripts/run_all.py",
    "scripts/packaged_subprocess_runtime_bridge.py",
    "scripts/full_import_lock_runtime_module.py",
    "config/portable_runtime.template.json",
    "portable_runtime.template.json",
    "data/00_raw",
    "data/01_mapping",
    "data/02_duckdb",
    "data/03_exports",
]

FORBIDDEN = ["RUN_TESTS.bat", "tests", "_test_reports"]
EXPECTED_ENTRYPOINT = "app/secure_app_portable.py"


def _norm(value: str) -> str:
    return str(value).replace("\\", "/").strip("/")


def _latest_release_dir() -> Path | None:
    if not RELEASE_ROOT.is_dir():
        return None
    candidates = sorted(
        [path for path in RELEASE_ROOT.glob("NetzentgeltMVP_KeyUser_*") if path.is_dir()],
        reverse=True,
    )
    return candidates[0] if candidates else None


def _default_package_paths() -> tuple[Path, Path]:
    latest = _latest_release_dir()
    if latest is None:
        fallback = RELEASE_ROOT / "NetzentgeltMVP_KeyUser_TIMESTAMP"
        return fallback / "NetzentgeltMVP_KeyUser", fallback / "NetzentgeltMVP_KeyUser.zip"
    return latest / "NetzentgeltMVP_KeyUser", latest / "NetzentgeltMVP_KeyUser.zip"


def _zip_entries(zip_path: Path) -> set[str]:
    if not zip_path.is_file():
        return set()
    with zipfile.ZipFile(zip_path, "r") as archive:
        return {_norm(name) for name in archive.namelist()}


def _zip_contains(entries: set[str], relative_path: str) -> bool:
    rel = _norm(relative_path)
    return any(
        entry == rel
        or entry.endswith("/" + rel)
        or entry.startswith(rel + "/")
        or ("/" + rel + "/") in entry
        for entry in entries
    )


def _validate_runtime_template(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return [f"{path}: ungueltiges JSON ({type(exc).__name__}: {exc})"]

    if not isinstance(payload, dict):
        return [f"{path}: Root-Element ist kein JSON-Objekt"]
    if payload.get("schema_version") != 1:
        errors.append(f"{path}: schema_version muss 1 sein")
    if not isinstance(payload.get("azure"), dict):
        errors.append(f"{path}: Abschnitt 'azure' fehlt oder ist ungueltig")
    if not isinstance(payload.get("users"), list) or not payload.get("users"):
        errors.append(f"{path}: Abschnitt 'users' fehlt oder ist leer")
    return errors


def parse_args() -> argparse.Namespace:
    default_pkg, default_zip = _default_package_paths()
    parser = argparse.ArgumentParser(description="Prueft das portable Netzentgelt-Key-User-Paket.")
    parser.add_argument("--package-dir", default=str(default_pkg), help="Ordner des zu pruefenden Key-User-Pakets")
    parser.add_argument("--zip-path", default=str(default_zip), help="Pfad zur erzeugten Key-User-ZIP-Datei")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pkg = Path(args.package_dir)
    pkg_zip = Path(args.zip_path)

    print(f"Paketordner: {pkg}")
    print(f"Paket-ZIP:    {pkg_zip}")

    if not pkg.exists():
        print(f"FAIL: Paketordner fehlt: {pkg}")
        return 1

    missing = [rel for rel in NEEDED if not (pkg / rel).exists()]
    if missing:
        print("FAIL: Paket unvollstaendig")
        for rel in missing:
            print("- " + rel)
        return 1

    forbidden_found = [rel for rel in FORBIDDEN if (pkg / rel).exists()]
    if forbidden_found:
        print("FAIL: Entwickler-Artefakte duerfen nicht im Key-User-Paket liegen")
        for rel in forbidden_found:
            print("- " + rel)
        return 1

    entrypoint_config = (pkg / "packaging" / "netzentgelt_entrypoint.txt").read_text(encoding="utf-8-sig").strip()
    if _norm(entrypoint_config) != EXPECTED_ENTRYPOINT:
        print("FAIL: Paket startet nicht den portablen Entrypoint")
        print(f"- erwartet: {EXPECTED_ENTRYPOINT}")
        print(f"- gefunden: {entrypoint_config}")
        return 1

    template_errors: list[str] = []
    template_errors.extend(_validate_runtime_template(pkg / "config" / "portable_runtime.template.json"))
    template_errors.extend(_validate_runtime_template(pkg / "portable_runtime.template.json"))
    if template_errors:
        print("FAIL: portable_runtime.template.json ist nicht gueltig")
        for error in template_errors:
            print("- " + error)
        return 1

    if not pkg_zip.is_file():
        print(f"FAIL: Key-User-ZIP fehlt: {pkg_zip}")
        return 1

    entries = _zip_entries(pkg_zip)
    zip_missing = [rel for rel in ("config/portable_runtime.template.json", "portable_runtime.template.json") if not _zip_contains(entries, rel)]
    if zip_missing:
        print("FAIL: portable_runtime.template.json fehlt im ZIP")
        for rel in zip_missing:
            print("- " + rel)
        return 1

    zip_forbidden = [rel for rel in FORBIDDEN if _zip_contains(entries, rel)]
    if zip_forbidden:
        print("FAIL: Entwickler-Artefakte duerfen nicht im Key-User-ZIP liegen")
        for rel in zip_forbidden:
            print("- " + rel)
        return 1

    print("PASS: Paketdateien vorhanden")
    print("PASS: Portabler Entrypoint ist konfiguriert")
    print("PASS: portable_runtime.template.json liegt in config und Paket-Root")
    print("PASS: ZIP enthaelt portable_runtime.template.json an beiden Zielpfaden")
    print("PASS: RUN_TESTS.bat wird im Key-User-Paket nicht erwartet und ist nicht enthalten")
    print("PASS: Paketcheck abgeschlossen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
