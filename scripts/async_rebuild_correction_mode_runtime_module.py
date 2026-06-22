"""Set async correction rebuilds to the correction pipeline mode."""

from __future__ import annotations

PATCH_MARKER = "NETZENTGELT_ASYNC_CORRECTION_MODE_PHASE13G_V1_20260622"


def install_async_correction_rebuild_mode() -> None:
    import async_rebuild_runtime_module

    async_rebuild_runtime_module.DEFAULT_REBUILD_MODE = "CORRECTION_REBUILD"

    try:
        import async_rebuild_status_ui_module
    except ImportError:
        return

    async_rebuild_status_ui_module.DEFAULT_REBUILD_MODE = "CORRECTION_REBUILD"
