"""Pipeline-Runner fuer den Netzentgelt-MVP.

Der erste Schritt dieser Modularisierung ist bewusst risikoarm: Die bestehende
Fachlogik in scripts/run_all.py bleibt unveraendert und wird als Legacy-Full-
Rebuild-Schritt ausgefuehrt. Dadurch entstehen bereits ein einheitlicher
Einstieg, Rebuild-Modes und Laufzeitmessung, ohne die fachliche Berechnung zu
veraendern.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .context import PipelineContext
from .rebuild_modes import RebuildMode
from .step_result import StepResult


@dataclass(frozen=True)
class PipelineStep:
    """Ausfuehrbarer Pipeline-Schritt."""

    step_id: str
    action: Callable[[PipelineContext], str | None]


def _import_legacy_run_all():
    """Bestehendes scripts/run_all.py robust importieren.

    run_all.py nutzt aktuell Imports relativ zum scripts-Verzeichnis
    (z. B. error_rules). Deshalb wird das scripts-Verzeichnis explizit in den
    Python-Pfad aufgenommen, bevor das Modul geladen wird.
    """
    scripts_dir = Path(__file__).resolve().parents[1]
    scripts_dir_text = str(scripts_dir)

    if scripts_dir_text not in sys.path:
        sys.path.insert(0, scripts_dir_text)

    return importlib.import_module("run_all")


def _legacy_full_rebuild(_: PipelineContext) -> str:
    legacy_run_all = _import_legacy_run_all()
    legacy_run_all.main()
    return "Legacy-Full-Rebuild erfolgreich abgeschlossen."


def _steps_for_mode(mode: RebuildMode) -> list[PipelineStep]:
    if mode is RebuildMode.FULL_IMPORT_REBUILD:
        return [PipelineStep("legacy_full_import_rebuild", _legacy_full_rebuild)]

    raise NotImplementedError(
        f"RebuildMode {mode.value} ist als Zielbild angelegt, aber noch nicht "
        "technisch implementiert. Aktuell produktiv angebunden ist nur "
        f"{RebuildMode.FULL_IMPORT_REBUILD.value}."
    )


def _write_step_log(ctx: PipelineContext, results: list[StepResult]) -> None:
    ctx.ensure_directories()
    log_path = ctx.log_dir / f"{ctx.run_id}_pipeline_steps.json"
    payload = {
        "run_id": ctx.run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "steps": [result.to_log_dict() for result in results],
    }
    log_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Pipeline-Step-Log: {log_path}")


def run_pipeline(
    mode: RebuildMode = RebuildMode.FULL_IMPORT_REBUILD,
    ctx: PipelineContext | None = None,
) -> list[StepResult]:
    """Pipeline im angegebenen Rebuild-Modus ausfuehren."""
    pipeline_context = ctx or PipelineContext.from_project_root()
    pipeline_context.ensure_directories()

    print("")
    print("=" * 80)
    print(f"Pipeline-Modus: {mode.value}")
    print(f"Run-ID: {pipeline_context.run_id}")
    print("=" * 80)

    results: list[StepResult] = []

    try:
        for step in _steps_for_mode(mode):
            started_at = datetime.now(timezone.utc)
            print(f"Starte Pipeline-Step: {step.step_id}")

            try:
                message = step.action(pipeline_context) or ""
            except Exception as exc:
                result = StepResult.failed(step.step_id, started_at, exc)
                results.append(result)
                _write_step_log(pipeline_context, results)
                raise

            result = StepResult.success(step.step_id, started_at, message=message)
            results.append(result)
            print(
                f"Pipeline-Step abgeschlossen: {step.step_id} "
                f"({result.duration_seconds:.2f}s)"
            )

    finally:
        if results:
            _write_step_log(pipeline_context, results)

    return results


def run_full_rebuild() -> list[StepResult]:
    """Rueckwaertskompatibler Einstieg fuer den vollstaendigen Neuaufbau."""
    return run_pipeline(RebuildMode.FULL_IMPORT_REBUILD)
