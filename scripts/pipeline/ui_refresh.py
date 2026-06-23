from __future__ import annotations

from pathlib import Path

from .affected_scope import get_affected_loco_nos
from .context import PipelineContext
from .full_rebuild_from_raw import run_full_rebuild_from_raw
from .partial_rebuild import run_partial_correction_rebuild
from .raw_import import run_raw_import

_OVERRIDES_CSV = Path(__file__).resolve().parents[2] / "data" / "01_mapping" / "manual_overrides.csv"


def run_ui_refresh(ctx: PipelineContext) -> str:
    ctx.ensure_directories()

    messages: list[str] = []
    if not ctx.raw_db_path.exists():
        messages.append(run_raw_import(ctx))

    affected = get_affected_loco_nos(ctx.db_path, _OVERRIDES_CSV)

    if affected is None or not ctx.db_path.exists():
        # Keine Prod-DB, kein Scope bestimmbar oder globale Override-Änderung → Vollneubau
        messages.append(run_full_rebuild_from_raw(ctx, write_csv_outputs=False))
    elif len(affected) == 0:
        # Overrides unveraendert → trotzdem Vollneubau (z.B. nach Rohdaten-Import)
        messages.append(run_full_rebuild_from_raw(ctx, write_csv_outputs=False))
    else:
        # Nur betroffene Loknummern neu berechnen
        print(
            f"Override-Diff: {len(affected)} betroffene Loknummer(n) erkannt. "
            "Partieller Rebuild wird ausgefuehrt."
        )
        messages.append(run_partial_correction_rebuild(ctx, affected_loco_nos=affected))

    return " | ".join(messages)
