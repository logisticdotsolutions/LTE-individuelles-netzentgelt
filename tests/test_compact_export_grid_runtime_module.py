from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from compact_export_grid_runtime_module import (  # noqa: E402
    COMPACT_EXPORT_GRID_MARKER,
    patch_export_grid_source,
)
from export_cockpit_ui_module import _friendly_category  # noqa: E402


def test_patch_export_grid_source_replaces_full_export_tab() -> None:
    source = '''before
with tab_exports:
    st.subheader("XLSX-Nutzungsmeldungen je nutzendem EVU")
    st.caption("alter langer Exportbereich")
    for group_key, group_config in PRIMARY_EXPORT_GROUPS.items():
        st.divider()
        st.markdown(f"### {group_config['title']}")
with tab_run:
    render_pipeline_test_controller()
after'''

    patched = patch_export_grid_source(source)

    assert COMPACT_EXPORT_GRID_MARKER in patched
    assert "render_export_cockpit" in patched
    assert "export_cockpit_ui_module" in patched
    assert "alter langer Exportbereich" not in patched
    assert "with tab_run:" in patched


def test_patch_export_grid_source_is_idempotent() -> None:
    source = f"before\n# {COMPACT_EXPORT_GRID_MARKER}\nafter"

    assert patch_export_grid_source(source) == source


def test_export_cockpit_rule_codes_are_friendly_labels() -> None:
    assert _friendly_category("R003") == "Ankunft fehlt"
    assert _friendly_category("R010") == "Zeitliche Lücke"
    assert _friendly_category("R011") == "Überschneidung"
    assert _friendly_category("R012") == "Pflichtfeld offen"
