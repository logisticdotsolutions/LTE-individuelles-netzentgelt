from __future__ import annotations


REMOVE_VENS_RUNTIME_MARKER = "NETZENTGELT_REMOVE_VENS_RUNTIME_PHASE11L_V1_20260618"


def install_remove_vens_runtime() -> None:
    """Disable vEns-only checks while keeping all other UKL preflight checks active."""
    try:
        import ukl_preflight_module as preflight
    except Exception:
        return

    def no_vens_issues(rows, *, prefix: str):
        return []

    preflight._validate_vens_rows = no_vens_issues
