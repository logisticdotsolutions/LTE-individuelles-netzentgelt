from __future__ import annotations

from dataclasses import dataclass

import ae01_hardened_export_module as ae01
import n01_hardened_export_module as n01
import zuordnungen_hardened_export_module as z01
import zuordnungen_hardened_preview_module as z01_preview
from ukl_vens_mapping_module import apply_vens_mapping


@dataclass(frozen=True)
class VEnsMappingRuntime:
    n01_fetch: object
    ae01_fetch: object
    z01_fetch: object
    preview_fetch: object


def install_vens_mapping_runtime() -> VEnsMappingRuntime:
    """Alle aktiven UKL-Pfade auf zeitabhängige PerformingRU-vEns-Auflösung umschalten."""
    runtime = VEnsMappingRuntime(
        n01_fetch=n01._fetch_usage_segments,
        ae01_fetch=ae01._fetch_hardened_ae01_rows,
        z01_fetch=z01._fetch_hardened_holding_rows,
        preview_fetch=z01_preview.build_zuordnungen_holding_preview,
    )

    def n01_fetch(**kwargs):
        return apply_vens_mapping(
            runtime.n01_fetch(**kwargs),
            timestamp_keys=("usage_start",),
        )

    def ae01_fetch(**kwargs):
        return apply_vens_mapping(
            runtime.ae01_fetch(**kwargs),
            timestamp_keys=("event_ts",),
        )

    def z01_fetch(**kwargs):
        return apply_vens_mapping(
            runtime.z01_fetch(**kwargs),
            timestamp_keys=("usage_start",),
        )

    def preview_fetch(**kwargs):
        frame = runtime.preview_fetch(**kwargs).copy()
        if frame.empty:
            return frame
        rows = [
            {
                "performing_ru": row.get("PerformingRU"),
                "usage_start": row.get("Beginn der Zuordnung*"),
                "user_vens": row.get("Nutzer-vEns*"),
            }
            for _, row in frame.iterrows()
        ]
        mapped = apply_vens_mapping(rows, timestamp_keys=("usage_start",))
        frame["Nutzer-vEns*"] = [row.get("user_vens") for row in mapped]
        return frame

    n01._fetch_usage_segments = n01_fetch
    ae01._fetch_hardened_ae01_rows = ae01_fetch
    z01._fetch_hardened_holding_rows = z01_fetch
    z01_preview.build_zuordnungen_holding_preview = preview_fetch
    return runtime


def restore_vens_mapping_runtime(runtime: VEnsMappingRuntime) -> None:
    """Zeitabhängige Mapping-Patches nach Ende des UI-Laufs zurücksetzen."""
    n01._fetch_usage_segments = runtime.n01_fetch
    ae01._fetch_hardened_ae01_rows = runtime.ae01_fetch
    z01._fetch_hardened_holding_rows = runtime.z01_fetch
    z01_preview.build_zuordnungen_holding_preview = runtime.preview_fetch
