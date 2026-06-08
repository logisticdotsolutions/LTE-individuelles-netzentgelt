#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

CLEANUP_ID = "NETZENTGELT_REPOSITORY_CLEANUP_PHASE7C_V1_20260608"
EXPECTED_REPOSITORY_NAME = "LTE-individuelles-netzentgelt"

# Productive runtime and tests that must survive cleanup.
PROTECTED_PATHS = {
    ".gitignore",
    "README.md",
    "RUN_TESTS.bat",
    "RUN_TESTS.ps1",
    "requirements-test.txt",
    "pytest.ini",
    "app/app.py",
    "scripts/run_all.py",
    "scripts/download_blob_data.py",
    "scripts/error_rules.py",
    "scripts/export_module.py",
    "scripts/rest_export_module.py",
    "scripts/manual_override_module.py",
    "scripts/manual_override_ui_module.py",
    "scripts/operator_ui_module.py",
    "scripts/operational_day_filter_module.py",
    "scripts/quality_gate_module.py",
    "scripts/rule_engine_hardening_phase6b.py",
    "scripts/rule_engine_hardening_phase6c.py",
    "scripts/rule_engine_hardening_phase6d.py",
    "scripts/phase6d_controller_review_ui.py",
    "scripts/pipeline_test_ui_module.py",
}

# Known one-time patch, rollback, backup, report, and legacy diagnostic artifacts.
DELETE_TRACKED_PATTERNS = [
    r"^\.patch_backups(?:/|$)",
    r"^\.netzentgelt_hotfix_backups(?:/|$)",
    r"^_test_reports(?:/|$)",
    r"^payload(?:/|$)",
    r"^PACKAGE_MANIFEST\.json$",
    r"^install_phase.*\.ps1$",
    r"^01_DRY_RUN_.*\.bat$",
    r"^02_APPLY_.*\.bat$",
    r"^03_VERIFY_.*\.bat$",
    r"^03_ROLLBACK_.*\.bat$",
    r"^04_RUN_.*\.bat$",
    r"^04_CREATE_LOCAL_COMMIT\.bat$",
    r"^CREATE_TEST_SUITE_COMMIT\.bat$",
    r"^05_ROLLBACK_.*\.bat$",
    r"^06_PACKAGE_SELFTEST_.*\.bat$",
    r"^README_PHASE.*\.md$",
    r"^README_MANUAL_OVERRIDE_PHASE.*\.md$",
    r"^TEST_REPORT_.*\.md$",
    r"^test_phase.*_logic\.py$",
    r"^verify_manual_override_phase.*\.py$",
    r"^apply_.*\.py$",
    r"^\.phase5.*_latest_backup\.txt$",
    r"^scripts/rule_engine_diagnostic_phase6a\.py$",
    r"^scripts/verify_rule_engine_hardening_phase6[bcd]\.py$",
    r"^scripts/run_pipeline_verify_rule_engine_hardening_phase6[bcd]\.py$",
    r"^scripts/test_rule_engine_hardening_phase6d\.py$",
    r"^.*\.zip$",
]

# Generated data must not be versioned. Files stay on disk for the local runtime.
UNTRACK_KEEP_LOCAL_PATTERNS = [
    r"^data/00_raw/(?!\.gitkeep$).+",
    r"^data/01_staging/(?!\.gitkeep$).+",
    r"^data/02_processed/(?!\.gitkeep$).+",
    r"^data/02_duckdb/(?!\.gitkeep$).+",
    r"^data/03_exports/(?!\.gitkeep$).+",
    r"^data/04_logs/(?!\.gitkeep$).+",
    r"^logs/.+",
    r"^tmp/.+",
    r"^temp/.+",
    r"^\.env(?:\..+)?$",
    r"^\.streamlit/secrets\.toml$",
    r"^.*\.duckdb(?:\.wal)?$",
    r"^.*\.db(?:-journal)?$",
    r"^.*credentials.*\.json$",
    r"^.*secrets.*\.(?:json|toml)$",
    r"^.*\.(?:pem|key|pfx|p12|crt)$",
]

LOCAL_REMOVE_DIRS = [
    ".patch_backups",
    ".netzentgelt_hotfix_backups",
    "_test_reports",
    ".pytest_cache",
    "payload",
]

GITIGNORE_BLOCK = r"""
# =========================================================
# Netzentgelt Tool - repository cleanup and deployment guard
# =========================================================
.patch_backups/
_test_reports/
payload/
PACKAGE_MANIFEST.json
install_phase*.ps1
01_DRY_RUN_*.bat
02_APPLY_*.bat
03_VERIFY_*.bat
03_ROLLBACK_*.bat
04_RUN_*.bat
04_CREATE_LOCAL_COMMIT.bat
CREATE_TEST_SUITE_COMMIT.bat
05_ROLLBACK_*.bat
06_PACKAGE_SELFTEST_*.bat
README_PHASE*.md
README_MANUAL_OVERRIDE_PHASE*.md
TEST_REPORT_*.md
apply_*.py
*.zip
data/02_duckdb/**
!data/02_duckdb/.gitkeep
data/04_logs/**
!data/04_logs/.gitkeep
""".strip() + "\n"

@dataclass
class Entry:
    action: str
    path: str
    backup_path: str | None = None
    comment: str | None = None

def normalized(path: str | Path) -> str:
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text

def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Git-Befehl fehlgeschlagen: git {' '.join(args)}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result

def git_lines(root: Path, *args: str) -> list[str]:
    output = run_git(root, *args).stdout
    return [line.strip() for line in output.splitlines() if line.strip()]

def matches(path: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, path, flags=re.IGNORECASE) for pattern in patterns)

def copy_to_backup(root: Path, backup_dir: Path, relative: str) -> str | None:
    source = root / Path(relative)
    if not source.exists() or not source.is_file():
        return None
    destination = backup_dir / "files" / Path(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return normalized(destination.relative_to(backup_dir))

def find_untracked_cleanup_paths(root: Path) -> list[str]:
    results: set[str] = set()
    for rel in LOCAL_REMOVE_DIRS:
        path = root / rel
        if path.exists():
            results.add(normalized(rel))
    for path in root.rglob("__pycache__"):
        if ".git" not in path.parts:
            results.add(normalized(path.relative_to(root)))
    for pattern in ("*.pyc", "*.pyo", "*.tmp", "*.bak"):
        for path in root.rglob(pattern):
            if ".git" not in path.parts and path.is_file():
                results.add(normalized(path.relative_to(root)))
    for path in root.glob("*.zip"):
        if path.is_file():
            results.add(normalized(path.relative_to(root)))
    return sorted(results)

def inventory(root: Path) -> dict[str, list[str]]:
    tracked = sorted(set(git_lines(root, "ls-files")))
    delete_tracked = []
    untrack_keep_local = []
    protected_hits = []
    for rel in tracked:
        rel = normalized(rel)
        if rel in PROTECTED_PATHS:
            protected_hits.append(rel)
            continue
        if matches(rel, UNTRACK_KEEP_LOCAL_PATTERNS):
            untrack_keep_local.append(rel)
        elif matches(rel, DELETE_TRACKED_PATTERNS):
            delete_tracked.append(rel)
    return {
        "tracked": tracked,
        "delete_tracked": sorted(set(delete_tracked)),
        "untrack_keep_local": sorted(set(untrack_keep_local)),
        "protected_hits": sorted(set(protected_hits)),
        "local_cleanup": find_untracked_cleanup_paths(root),
    }

def assert_repo(root: Path) -> None:
    if not (root / ".git").exists():
        raise RuntimeError(f"Kein Git-Repository gefunden: {root}")
    name = root.name
    if name.lower() != EXPECTED_REPOSITORY_NAME.lower():
        print(f"WARNING: Repository-Ordner heißt '{name}', erwartet war '{EXPECTED_REPOSITORY_NAME}'.")
    head = run_git(root, "rev-parse", "HEAD").stdout.strip()
    branch = run_git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    print(f"Repository: {root}")
    print(f"Branch: {branch}")
    print(f"HEAD: {head}")

def assert_clean(root: Path, allow_dirty: bool) -> None:
    dirty = run_git(root, "status", "--porcelain").stdout.strip()
    if dirty and not allow_dirty:
        raise RuntimeError(
            "Das Repository enthält lokale Änderungen. Cleanup wurde abgebrochen, "
            "damit nichts überschrieben wird. Bitte zuerst committen oder sichern.\n\n"
            + dirty
        )
    if dirty:
        print("WARNING: Cleanup wird trotz lokaler Änderungen ausgeführt (-AllowDirty).")

def print_inventory(inv: dict[str, list[str]]) -> None:
    print("\n=== ENTFERNEN: getrackte Einmal-Artefakte ===")
    if inv["delete_tracked"]:
        for rel in inv["delete_tracked"]:
            print(f"DELETE TRACKED  {rel}")
    else:
        print("Keine gefunden.")
    print("\n=== NUR AUS GIT LÖSEN: lokale Laufdaten bleiben auf der Festplatte ===")
    if inv["untrack_keep_local"]:
        for rel in inv["untrack_keep_local"]:
            print(f"UNTRACK LOCAL   {rel}")
    else:
        print("Keine gefunden.")
    print("\n=== LOKAL ENTFERNEN: Cache-, Backup- und Reportreste ===")
    if inv["local_cleanup"]:
        for rel in inv["local_cleanup"]:
            print(f"DELETE LOCAL    {rel}")
    else:
        print("Keine gefunden.")
    print("\n=== GESCHÜTZTE PRODUKTIVDATEIEN ===")
    print(f"Erkannte geschützte Dateien: {len(inv['protected_hits'])}")

def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def append_gitignore(root: Path, backup_dir: Path, entries: list[Entry]) -> None:
    path = root / ".gitignore"
    before = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    backup = backup_dir / "gitignore.before"
    backup.write_text(before, encoding="utf-8")
    marker = "# Netzentgelt Tool - repository cleanup and deployment guard"
    if marker in before:
        print(".gitignore enthält den Deployment-Guard bereits.")
        return
    text = before.rstrip() + "\n\n" + GITIGNORE_BLOCK
    path.write_text(text, encoding="utf-8", newline="\n")
    run_git(root, "add", ".gitignore")
    entries.append(Entry("PATCH_GITIGNORE", ".gitignore", "gitignore.before"))

def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()

def apply_cleanup(root: Path, allow_dirty: bool) -> None:
    assert_repo(root)
    assert_clean(root, allow_dirty)
    inv = inventory(root)
    print_inventory(inv)
    backup_base = root.parent / "_netzentgelt_cleanup_backups"
    backup_dir = backup_base / f"{CLEANUP_ID}_{timestamp()}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    entries: list[Entry] = []

    for rel in inv["delete_tracked"]:
        backup_path = copy_to_backup(root, backup_dir, rel)
        run_git(root, "rm", "-f", "--", rel)
        entries.append(Entry("DELETE_TRACKED", rel, backup_path))

    for rel in inv["untrack_keep_local"]:
        backup_path = copy_to_backup(root, backup_dir, rel)
        run_git(root, "rm", "--cached", "-f", "--", rel)
        entries.append(Entry("UNTRACK_KEEP_LOCAL", rel, backup_path))

    tracked_now = set(git_lines(root, "ls-files"))
    for rel in inv["local_cleanup"]:
        # Never remove any surviving tracked path implicitly.
        if rel in tracked_now:
            continue
        path = root / rel
        if not path.exists():
            continue
        if path.is_file():
            backup_path = copy_to_backup(root, backup_dir, rel)
        else:
            destination = backup_dir / "local_dirs" / Path(rel)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(path, destination, dirs_exist_ok=True)
            backup_path = normalized(destination.relative_to(backup_dir))
        remove_path(path)
        entries.append(Entry("DELETE_LOCAL", rel, backup_path))

    append_gitignore(root, backup_dir, entries)
    manifest = {
        "cleanup_id": CLEANUP_ID,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_root": str(root),
        "head_before": run_git(root, "rev-parse", "HEAD").stdout.strip(),
        "entries": [asdict(entry) for entry in entries],
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    backup_base.mkdir(parents=True, exist_ok=True)
    (backup_base / "LATEST.txt").write_text(str(backup_dir), encoding="utf-8")
    print("\nPASS: Cleanup wurde angewendet und für einen lokalen Commit vorgemerkt.")
    print(f"Externes Backup: {backup_dir}")
    print("\nGit-Status:")
    print(run_git(root, "status", "--short").stdout or "(sauber)")
    print("Nächster Schritt: RUN_TESTS.bat ausführen. Danach externen Commit-Helfer starten.")

def rollback(root: Path) -> None:
    assert_repo(root)
    backup_base = root.parent / "_netzentgelt_cleanup_backups"
    latest = backup_base / "LATEST.txt"
    if not latest.exists():
        raise RuntimeError("Kein Cleanup-Backup gefunden.")
    backup_dir = Path(latest.read_text(encoding="utf-8").strip())
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Backup-Manifest fehlt: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Rollback is intended before cleanup commit. Reset staged cleanup changes first.
    run_git(root, "reset", "--", ".")
    for item in manifest.get("entries", []):
        action = item["action"]
        rel = item["path"]
        backup_path = item.get("backup_path")
        if action == "PATCH_GITIGNORE":
            source = backup_dir / str(backup_path)
            shutil.copy2(source, root / ".gitignore")
            continue
        if not backup_path:
            continue
        source = backup_dir / str(backup_path)
        target = root / rel
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        elif source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    print("PASS: Cleanup-Rollback wurde lokal wiederhergestellt.")
    print("Git-Status:")
    print(run_git(root, "status", "--short").stdout or "(sauber)")

def commit_cleanup(root: Path) -> None:
    assert_repo(root)
    run_git(root, "add", "-u")
    if (root / ".gitignore").exists():
        run_git(root, "add", ".gitignore")
    staged = run_git(root, "diff", "--cached", "--name-status").stdout.strip()
    if not staged:
        print("INFO: Keine vorgemerkten Cleanup-Änderungen vorhanden. Kein Commit erzeugt.")
        return
    print("Folgende Cleanup-Änderungen werden committed:\n")
    print(staged)
    run_git(root, "commit", "-m", "chore: remove temporary patch and runtime artifacts")
    print("PASS: Lokaler Cleanup-Commit erstellt. Es wurde NICHT gepusht.")
    print(run_git(root, "log", "-1", "--oneline").stdout)

def dry_run(root: Path) -> None:
    assert_repo(root)
    inv = inventory(root)
    print_inventory(inv)
    print("\n=== SICHERHEITSHINWEIS ===")
    suspicious = [
        rel for rel in inv["untrack_keep_local"]
        if rel.lower().startswith((".env", ".streamlit/secrets"))
        or "credential" in rel.lower()
        or "secret" in rel.lower()
        or rel.lower().endswith((".pem", ".key", ".pfx", ".p12", ".crt"))
    ]
    if suspicious:
        print("WARNING: Potenziell sensible getrackte Dateien erkannt:")
        for rel in suspicious:
            print(f"  {rel}")
        print("Nach Entfernung aus Git müssen möglicherweise Zugangsdaten rotiert und die Git-Historie bereinigt werden.")
    else:
        print("PASS: Keine offensichtlich sensiblen Dateinamen im aktuellen Tracking erkannt.")
    print("\nPASS: Dry-Run abgeschlossen. Es wurde nichts verändert.")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dry-run", "apply", "rollback", "commit"], required=True)
    parser.add_argument("--target-root", default=os.getcwd())
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    root = Path(args.target_root).resolve()
    try:
        if args.mode == "dry-run":
            dry_run(root)
        elif args.mode == "apply":
            apply_cleanup(root, args.allow_dirty)
        elif args.mode == "rollback":
            rollback(root)
        elif args.mode == "commit":
            commit_cleanup(root)
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
