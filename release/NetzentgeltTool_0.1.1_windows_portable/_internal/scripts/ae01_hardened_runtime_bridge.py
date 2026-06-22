from __future__ import annotations

from dataclasses import dataclass

import export_module
from ae01_hardened_export_module import build_hardened_aufenthaltsereignis_xlsx


@dataclass(frozen=True)
class AE01HardenedRuntime:
    """Originalen Legacy-AE01-Builder für kontrollierte Wiederherstellung sichern."""

    original_builder: object


def install_ae01_hardened_runtime() -> AE01HardenedRuntime:
    """Produktive AE01-Downloads auf den gemappten und validierten Pfad umschalten."""
    runtime = AE01HardenedRuntime(
        original_builder=export_module.build_aufenthaltsereignis_xlsx,
    )
    export_module.build_aufenthaltsereignis_xlsx = build_hardened_aufenthaltsereignis_xlsx
    return runtime


def restore_ae01_hardened_runtime(runtime: AE01HardenedRuntime) -> None:
    """Legacy-Funktion nach Ende des authentifizierten UI-Laufs wiederherstellen."""
    export_module.build_aufenthaltsereignis_xlsx = runtime.original_builder
