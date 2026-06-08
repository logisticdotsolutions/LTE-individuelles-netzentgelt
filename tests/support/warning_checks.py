from __future__ import annotations

import argparse
import json
from pathlib import Path


def check_project(project_root: Path) -> dict[str, object]:
    warnings: list[dict[str, str]] = []
    run_all = project_root / "scripts" / "run_all.py"
    download = project_root / "scripts" / "download_blob_data.py"
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (run_all, download)
        if path.exists()
    ).lower()

    if "source_row_hash" not in combined:
        warnings.append(
            {
                "code": "W001_SOURCE_ROW_HASH_NOT_INTEGRATED",
                "message": (
                    "Die produktive Pipeline enthält noch keine persistierte source_row_hash-Spalte. "
                    "Die Testsuite prüft bereits den deterministischen Referenzvertrag; die Integration "
                    "in Import, Staging und Audit sollte als eigene Folgephase umgesetzt werden."
                ),
            }
        )

    for template in (
        "Vorlage_Nutzungsmeldung.xlsx",
        "Vorlage_Aufenthaltsereignis.xlsx",
    ):
        if not (project_root / "data" / "05_templates" / template).exists():
            warnings.append(
                {
                    "code": "W002_TEMPLATE_MISSING",
                    "message": f"Produktive XLSX-Vorlage fehlt lokal: data/05_templates/{template}",
                }
            )

    return {"warnings": warnings, "warning_count": len(warnings)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = check_project(args.project_root.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for warning in result["warnings"]:
        print(f"WARNING {warning['code']}: {warning['message']}")
    if not result["warnings"]:
        print("PASS: Keine WARNING-Verträge offen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
