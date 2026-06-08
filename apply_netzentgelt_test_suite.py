from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PATCH_ID = "NETZENTGELT_TEST_SUITE_PHASE7A_V1_1_20260608"
MANIFEST_NAME = "PACKAGE_MANIFEST.json"
SENTINELS = (
    "scripts/run_all.py",
    "scripts/error_rules.py",
    "scripts/rule_engine_hardening_phase6d.py",
)
TEXT_SUFFIXES = {".py", ".ps1", ".bat", ".md", ".ini", ".txt", ".json", ".yml", ".yaml"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def payload_root() -> Path:
    return Path(__file__).resolve().parent / "payload"


def package_manifest_path() -> Path:
    return Path(__file__).resolve().parent / MANIFEST_NAME


def read_package_manifest() -> dict:
    path = package_manifest_path()
    if not path.is_file():
        raise RuntimeError(f"Paketmanifest fehlt: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("package_id") != PATCH_ID:
        raise RuntimeError(
            "Paketmanifest gehört nicht zum Installer. "
            f"Erwartet={PATCH_ID}, gefunden={payload.get('package_id')}."
        )
    return payload


def rel_payload(path: Path) -> str:
    return path.relative_to(payload_root()).as_posix()


def approved_payload_rows() -> list[tuple[Path, dict]]:
    """Nur explizit im Paketmanifest freigegebene Dateien verwenden.

    Dadurch werden versehentlich im gleichen payload-Ordner verbliebene Dateien
    älterer Patch-Pakete weder geprüft noch installiert oder committed.
    """
    root = payload_root().resolve()
    manifest = read_package_manifest()
    declared = manifest.get("payload_files", [])
    if not isinstance(declared, list) or not declared:
        raise RuntimeError("Paketmanifest enthält keine freigegebenen Payload-Dateien.")

    approved: list[tuple[Path, dict]] = []
    seen: set[str] = set()
    for row in declared:
        relative = str(row.get("path", "")).replace("\\", "/").strip()
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            raise RuntimeError(f"Ungültiger Payload-Pfad im Manifest: {relative!r}")
        if relative in seen:
            raise RuntimeError(f"Payload-Pfad mehrfach im Manifest enthalten: {relative}")
        seen.add(relative)

        path = (root / Path(relative)).resolve()
        if path != root and root not in path.parents:
            raise RuntimeError(f"Payload-Pfad verlässt den Paketordner: {relative}")
        if not path.is_file():
            raise RuntimeError(f"Freigegebene Payload-Datei fehlt: {relative}")

        expected_hash = str(row.get("sha256", "")).strip().lower()
        actual_hash = sha256(path)
        if expected_hash and actual_hash != expected_hash:
            raise RuntimeError(
                f"Payload-Hash stimmt nicht: {relative}. "
                f"Erwartet={expected_hash}, gefunden={actual_hash}."
            )
        approved.append((path, row))
    return sorted(approved, key=lambda item: rel_payload(item[0]))


def payload_files() -> list[Path]:
    return [path for path, _ in approved_payload_rows()]


def ignored_payload_files() -> list[str]:
    root = payload_root()
    approved = {rel_payload(path) for path in payload_files()}
    existing = {rel_payload(path) for path in root.rglob("*") if path.is_file()}
    return sorted(existing - approved)


def validate_project(target: Path) -> None:
    missing = [name for name in SENTINELS if not (target / name).is_file()]
    if missing:
        raise RuntimeError(
            "Zielordner ist kein kompatibler Netzentgelt-MVP-Stand. Fehlende Dateien: "
            + ", ".join(missing)
        )


def validate_crlf() -> None:
    failures: list[str] = []
    for path in payload_files():
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        raw = path.read_bytes()
        if b"\n" in raw.replace(b"\r\n", b""):
            failures.append(rel_payload(path))
    if failures:
        raise RuntimeError("Payload enthält Textdateien ohne Windows-CRLF: " + ", ".join(failures))


def syntax_check(paths: list[Path]) -> None:
    failures: list[str] = []
    for path in paths:
        if path.suffix.lower() != ".py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except (OSError, UnicodeError, SyntaxError) as exc:
            failures.append(f"{path}: {exc}")
    if failures:
        raise RuntimeError("Python-Syntaxprüfung fehlgeschlagen:\n" + "\n".join(failures))


def latest_manifest(target: Path) -> Path:
    backup_root = target / ".patch_backups"
    candidates = sorted(backup_root.glob(f"{PATCH_ID}_*/manifest.json"), reverse=True)
    if not candidates:
        raise RuntimeError("Kein Rollback-Manifest für diese Testsuite gefunden.")
    return candidates[0]


def dry_run(target: Path) -> None:
    validate_project(target)
    validate_crlf()
    files = payload_files()
    ignored = ignored_payload_files()
    syntax_check(files)
    collisions = [rel_payload(src) for src in files if (target / rel_payload(src)).exists()]

    print("=" * 78)
    print(f"{PATCH_ID} - DRY RUN")
    print("=" * 78)
    print(f"Zielordner: {target}")
    print(f"Neue Dateien im Payload: {len(files)}")
    print("Python-Syntaxprüfung: PASS")
    print("Windows-CRLF-Prüfung: PASS")
    print("Produktive Rohdaten/DuckDB-Dateien: werden NICHT verändert")
    if ignored:
        print("\nWARNING: Zusätzliche Dateien im lokalen payload-Ordner werden ignoriert, da sie nicht im Paketmanifest freigegeben sind:")
        for item in ignored:
            print(f" - {item}")

    if collisions:
        print("\nFAIL: Folgende Zieldateien existieren bereits. Es wird nichts überschrieben:")
        for item in collisions:
            print(f" - {item}")
        raise RuntimeError("Additive Installation wegen vorhandener Zieldateien abgebrochen.")

    print("Dateikollisionen: keine")
    print("\nPASS: Additive Installation ist möglich.")


def apply_patch(target: Path) -> None:
    dry_run(target)
    stamp = utc_stamp()
    backup_dir = target / ".patch_backups" / f"{PATCH_ID}_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    sentinel_state = {}
    sentinel_backups: dict[str, str] = {}
    for relative in SENTINELS:
        path = target / relative
        sentinel_state[relative] = sha256(path)
        backup_path = backup_dir / "sentinels" / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        sentinel_backups[relative] = backup_path.relative_to(backup_dir).as_posix()

    applied: list[dict[str, str]] = []
    try:
        for src in payload_files():
            relative = rel_payload(src)
            dst = target / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            applied.append({"path": relative, "sha256": sha256(dst)})

        syntax_check([target / row["path"] for row in applied])
        manifest = {
            "patch_id": PATCH_ID,
            "applied_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target_root": str(target),
            "mode": "additive-only",
            "sentinel_hashes_before": sentinel_state,
            "sentinel_backup_files": sentinel_backups,
            "added_files": applied,
        }
        (backup_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("\nPASS: Testsuite additiv installiert.")
        print(f"Rollback-Manifest: {backup_dir / 'manifest.json'}")
        print("Start: RUN_TESTS.bat")
    except Exception:
        for row in reversed(applied):
            path = target / row["path"]
            if path.exists() and sha256(path) == row["sha256"]:
                path.unlink()
        raise


def rollback(target: Path, manifest_path: Path | None) -> None:
    validate_project(target)
    manifest_path = manifest_path or latest_manifest(target)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("patch_id") != PATCH_ID:
        raise RuntimeError(f"Manifest gehört nicht zu {PATCH_ID}: {manifest_path}")

    modified: list[str] = []
    removed: list[str] = []
    missing: list[str] = []
    for row in reversed(payload.get("added_files", [])):
        relative = row["path"]
        path = target / relative
        if not path.exists():
            missing.append(relative)
            continue
        if sha256(path) != row["sha256"]:
            modified.append(relative)
            continue
        path.unlink()
        removed.append(relative)

    tests_root = target / "tests"
    if tests_root.exists():
        for cache_dir in sorted(tests_root.rglob("__pycache__"), reverse=True):
            shutil.rmtree(cache_dir, ignore_errors=True)

    sentinel_changes = []
    for relative, expected_hash in payload.get("sentinel_hashes_before", {}).items():
        path = target / relative
        if not path.exists() or sha256(path) != expected_hash:
            sentinel_changes.append(relative)

    print("=" * 78)
    print(f"{PATCH_ID} - ROLLBACK")
    print("=" * 78)
    print(f"Gelöscht: {len(removed)} unveränderte Testsuite-Dateien")
    if missing:
        print(f"Bereits nicht mehr vorhanden: {len(missing)}")
    if sentinel_changes:
        print("\nWARNING: Bestehende Sentinel-Module unterscheiden sich vom Stand bei Installation. Sie wurden bewusst NICHT überschrieben:")
        for item in sentinel_changes:
            print(f" - {item}")
    if modified:
        print("\nWARNING: Manuell geänderte Testsuite-Dateien wurden bewusst NICHT gelöscht:")
        for item in modified:
            print(f" - {item}")
        raise RuntimeError("Rollback unvollständig: geänderte Testsuite-Dateien bleiben erhalten.")
    print("PASS: Rollback abgeschlossen. Produktive Dateien blieben unangetastet.")


def create_local_commit(target: Path) -> None:
    validate_project(target)
    files = [rel_payload(path) for path in payload_files()]
    missing = [relative for relative in files if not (target / relative).exists()]
    if missing:
        raise RuntimeError("Testsuite ist nicht vollständig installiert. Fehlend: " + ", ".join(missing))

    subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=target, check=True, capture_output=True)
    subprocess.run(["git", "add", "--", *files], cwd=target, check=True)
    result = subprocess.run(
        ["git", "commit", "-m", "test: add automated Netzentgelt MVP regression suite", "--", *files],
        cwd=target,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Lokaler Git-Commit konnte nicht erstellt werden. Es wurde nichts gepusht.")
    print(result.stdout)
    print("PASS: Lokaler Commit erstellt. Es wurde bewusst NICHT gepusht.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Additive Installation der Netzentgelt-MVP-Testsuite")
    parser.add_argument("--mode", choices=["dry-run", "apply", "rollback", "commit"], required=True)
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = args.target.resolve()
    try:
        if args.mode == "dry-run":
            dry_run(target)
        elif args.mode == "apply":
            apply_patch(target)
        elif args.mode == "rollback":
            rollback(target, args.manifest)
        else:
            create_local_commit(target)
        return 0
    except Exception as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
