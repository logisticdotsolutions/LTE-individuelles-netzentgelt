from dataclasses import dataclass
import ae01_hardened_export_module as ae01
import n01_hardened_export_module as n01
import zuordnungen_hardened_export_module as z01
import zuordnungen_hardened_preview_module as preview
from ukl_vens_mapping_module import apply_vens_mapping


@dataclass(frozen=True)
class VEnsMappingRuntime:
    n01_fetch: object
    ae01_fetch: object
    z01_fetch: object
    preview_fetch: object


def install_vens_mapping_runtime():
    runtime = VEnsMappingRuntime(
        n01._fetch_usage_segments,
        ae01._fetch_hardened_ae01_rows,
        z01._fetch_hardened_holding_rows,
        preview.build_zuordnungen_holding_preview,
    )

    def mapped(fetch, keys, *args, **kwargs):
        return apply_vens_mapping(fetch(*args, **kwargs), timestamp_keys=keys)

    def n01_fetch(*args, **kwargs):
        return mapped(runtime.n01_fetch, ("usage_start",), *args, **kwargs)

    def ae01_fetch(*args, **kwargs):
        return mapped(runtime.ae01_fetch, ("event_ts",), *args, **kwargs)

    def z01_fetch(*args, **kwargs):
        return mapped(runtime.z01_fetch, ("usage_start",), *args, **kwargs)

    def preview_fetch(*args, **kwargs):
        frame = runtime.preview_fetch(*args, **kwargs).copy()
        if frame.empty:
            return frame
        rows = [{
            "performing_ru": row.get("PerformingRU"),
            "usage_start": row.get("Beginn der Zuordnung*"),
            "user_vens": row.get("Nutzer-vEns*"),
        } for _, row in frame.iterrows()]
        mapped_rows = apply_vens_mapping(rows, timestamp_keys=("usage_start",))
        frame["Nutzer-vEns*"] = [row.get("user_vens") for row in mapped_rows]
        return frame

    n01._fetch_usage_segments = n01_fetch
    ae01._fetch_hardened_ae01_rows = ae01_fetch
    z01._fetch_hardened_holding_rows = z01_fetch
    preview.build_zuordnungen_holding_preview = preview_fetch
    return runtime


def restore_vens_mapping_runtime(runtime):
    n01._fetch_usage_segments = runtime.n01_fetch
    ae01._fetch_hardened_ae01_rows = runtime.ae01_fetch
    z01._fetch_hardened_holding_rows = runtime.z01_fetch
    preview.build_zuordnungen_holding_preview = runtime.preview_fetch
