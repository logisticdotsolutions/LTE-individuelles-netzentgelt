from __future__ import annotations

from dataclasses import dataclass

import manual_override_ui_module as cockpit
from vens_selection_ui_module import render_vens_selection_area, reset_vens_selection_render_guard


@dataclass(frozen=True)
class VEnsSelectionUIRuntime:
    original_renderer: object


def install_vens_selection_ui_runtime() -> VEnsSelectionUIRuntime:
    """vEns-Auswahl kontrolliert unterhalb der bestehenden Fallbearbeitung ergänzen."""
    reset_vens_selection_render_guard()
    runtime = VEnsSelectionUIRuntime(original_renderer=cockpit.render_manual_override_cockpit)

    def wrapped_renderer(*args, **kwargs):
        runtime.original_renderer(*args, **kwargs)
        timeline = kwargs.get("timeline")
        if timeline is None and len(args) >= 4:
            timeline = args[3]
        render_vens_selection_area(timeline=timeline)

    cockpit.render_manual_override_cockpit = wrapped_renderer
    return runtime


def restore_vens_selection_ui_runtime(runtime: VEnsSelectionUIRuntime) -> None:
    """Originalen Cockpit-Renderer nach Ende des UI-Laufs wiederherstellen."""
    cockpit.render_manual_override_cockpit = runtime.original_renderer
