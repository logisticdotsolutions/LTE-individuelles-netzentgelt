from __future__ import annotations

BROKEN_ROUTE_CHAIN_POLICY_MARKER = "NETZENTGELT_NO_LTE_ASSIGNMENT_ONLY_POLICY_V2_20260630"
NO_LTE_ASSIGNMENT_MARKERS = (
    "keine lte zuweisung",
    "keine lte zuordnung",
    "kein lte bezug",
    "keine lte-zuweisung",
    "keine lte-zuordnung",
    "no lte assignment",
)


def is_no_lte_assignment_marker(*values: object) -> bool:
    """Return True only for explicit no-LTE assignment markers in UI text."""
    combined = " ".join(str(value or "") for value in values).strip().casefold()
    return any(marker in combined for marker in NO_LTE_ASSIGNMENT_MARKERS)


def disable_broken_route_chain_rules(con) -> None:
    """No blanket rule deactivation: normal GAP findings must stay active."""
    _ = con


def neutralize_broken_route_chain_quality_gate(con) -> None:
    """No blanket gate neutralization: normal GAP gate logic must stay active."""
    _ = con


def patch_error_rules_module(module) -> None:
    if getattr(module, "_BROKEN_ROUTE_CHAIN_POLICY_PATCHED", False):
        return
    module._BROKEN_ROUTE_CHAIN_POLICY_PATCHED = True


def patch_quality_gate_module(module) -> None:
    if getattr(module, "_BROKEN_ROUTE_CHAIN_QG_POLICY_PATCHED", False):
        return
    module._BROKEN_ROUTE_CHAIN_QG_POLICY_PATCHED = True


def patch_phase6d_gap_only_rule(module) -> None:
    if getattr(module, "_BROKEN_ROUTE_CHAIN_R016_POLICY_PATCHED", False):
        return
    module._BROKEN_ROUTE_CHAIN_R016_POLICY_PATCHED = True
