from __future__ import annotations

from dataclasses import dataclass

import zuordnungen_ui_runtime_bridge as ui_bridge
from t01_ui_runtime_bridge import (
    install_t01_export_ui_extension,
    restore_t01_export_ui_extension,
)
from zuordnungen_hardened_export_module import build_hardened_zuordnungen_holding_xlsx
from zuordnungen_hardened_preview_module import build_hardened_zuordnungen_holding_preview
from zuordnungen_export_module import build_zuordnungen_holding_xlsx
from zuordnungen_preview_module import build_zuordnungen_holding_preview


@dataclass(frozen=True)
class ZuordnungenHardenedRuntime:
    original_export_builder: object
    original_preview_builder: object
    t01_ui_runtime: object


def install_zuordnungen_hardened_runtime() -> ZuordnungenHardenedRuntime:
    original_export_builder = getattr(
        ui_bridge,
        "build_zuordnungen_holding_xlsx",
        build_zuordnungen_holding_xlsx,
    )
    original_preview_builder = getattr(
        ui_bridge,
        "build_zuordnungen_holding_preview",
        build_zuordnungen_holding_preview,
    )
    runtime = ZuordnungenHardenedRuntime(
        original_export_builder=original_export_builder,
        original_preview_builder=original_preview_builder,
        t01_ui_runtime=install_t01_export_ui_extension(),
    )
    ui_bridge.build_zuordnungen_holding_xlsx = build_hardened_zuordnungen_holding_xlsx
    ui_bridge.build_zuordnungen_holding_preview = build_hardened_zuordnungen_holding_preview
    return runtime


def restore_zuordnungen_hardened_runtime(runtime: ZuordnungenHardenedRuntime) -> None:
    ui_bridge.build_zuordnungen_holding_xlsx = runtime.original_export_builder
    ui_bridge.build_zuordnungen_holding_preview = runtime.original_preview_builder
    restore_t01_export_ui_extension(runtime.t01_ui_runtime)
