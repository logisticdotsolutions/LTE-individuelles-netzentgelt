from __future__ import annotations

import argparse
from pathlib import Path


def python_files(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".py":
            result.append(path)
        elif path.is_dir():
            result.extend(sorted(item for item in path.rglob("*.py") if item.is_file()))
    return sorted(set(result))


def check(paths: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in python_files(paths):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, UnicodeError, SyntaxError) as exc:
            failures.append(f"{path}: {exc}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Python-Syntaxprüfung ohne pyc-Dateien")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    failures = check(args.paths)
    if failures:
        print("FAIL: Python-Syntaxprüfung fehlgeschlagen:")
        for failure in failures:
            print(f" - {failure}")
        return 1
    print("PASS: Python-Syntaxprüfung erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
