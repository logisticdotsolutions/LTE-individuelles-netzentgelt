from __future__ import annotations

from .context import PipelineContext
from .full_rebuild_from_raw import run_full_rebuild_from_raw
from .raw_import import run_raw_import


def run_ui_refresh(ctx: PipelineContext) -> str:
    ctx.ensure_directories()

    messages: list[str] = []
    if not ctx.raw_db_path.exists():
        messages.append(run_raw_import(ctx))

    messages.append(run_full_rebuild_from_raw(ctx, write_csv_outputs=False))
    return " | ".join(messages)
