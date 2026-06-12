from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from ukl_preflight_module import summarize_issues_by_row, validate_z01_rows
from zuordnungen_preview_module import build_zuordnungen_holding_preview


OPTIONAL_TRANSFER_MP_COLUMN = "Marktpartner ID für Nutzungsüberlassung"


def build_hardened_zuordnungen_holding_preview(
    *,
    db_path: Path,
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """Bestehende Vorschau um UKL-Preflight-Gründe ergänzen und unsichere Fallbacks leeren."""
    preview = build_zuordnungen_holding_preview(
        db_path=Path(db_path),
        date_from=date_from,
        date_to=date_to,
    ).copy()

    if preview.empty:
        return preview

    preview[OPTIONAL_TRANSFER_MP_COLUMN] = ""

    rows = [
        {
            "locomotive_no": row.get("TfzE oder tEns*"),
            "usage_start": row.get("Beginn der Zuordnung*"),
            "usage_end": row.get("Ende der Zuordnung"),
            "user_vens": row.get("Nutzer-vEns*"),
            "performing_ru": row.get("PerformingRU"),
            "holder_market_partner_id": "",
        }
        for _, row in preview.iterrows()
    ]

    issues_by_row = summarize_issues_by_row(
        validate_z01_rows(rows)
    )

    for row_number, message in issues_by_row.items():
        index = preview.index[row_number - 1]
        previous_hint = str(preview.at[index, "Hinweis"] or "").strip()
        preview.at[index, "Exportstatus"] = "BLOCKIERT"
        preview.at[index, "Hinweis"] = " | ".join(
            part for part in [previous_hint, message] if part
        )

    return preview
