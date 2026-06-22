"""Correction rebuild mode.

This mode is the default target for UI corrections. It keeps the workflow simple:
if a raw DuckDB snapshot exists, rebuild from it; otherwise create it once and
then rebuild from it.
"""

from __future__ import annotations

from .context import PipelineContext
from .full_rebuild_from_raw import run_full_rebuild_from_raw
from .raw_import import run_raw_import


def run_correction_rebuild(ctx: PipelineContext) -> str:
    """Run the fastest safe correction rebuild path."""
    ctx.ensure_directories()

    messages: list[str] = []

    if not ctx.raw_db_path.exists():
        messages.append(run_raw_import(ctx))

    messages.append(run_full_rebuild_from_raw(ctx))
    return " | ".join(messages)
