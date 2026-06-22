from __future__ import annotations

from dataclasses import dataclass

import export_module
from n01_hardened_export_module import build_hardened_n01_xlsx


@dataclass(frozen=True)
class N01HardenedRuntime:
    """Originalen Legacy-N01-Builder für kontrollierte Wiederherstellung sichern."""

    original_builder: object


def install_n01_hardened_runtime() -> N01HardenedRuntime:
    """Produktive N01-Downloads auf die aktuelle Fünf-Spalten-Vorlage umschalten."""
    runtime = N01HardenedRuntime(
        original_builder=export_module.build_nutzungsmeldung_xlsx,
    )
    export_module.build_nutzungsmeldung_xlsx = build_hardened_n01_xlsx
    return runtime


def restore_n01_hardened_runtime(runtime: N01HardenedRuntime) -> None:
    """Legacy-Funktion nach Ende des authentifizierten UI-Laufs wiederherstellen."""
    export_module.build_nutzungsmeldung_xlsx = runtime.original_builder
