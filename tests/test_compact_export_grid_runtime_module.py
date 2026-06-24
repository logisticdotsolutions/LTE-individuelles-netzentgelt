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
    assert "st.subheader(\"Exporte\")" in patched
    assert "LTE Arbeitsdateien" in patched
    assert "Nutzung XLSX" in patched
    assert "Aufenthalt XLSX" in patched
    assert "Betroffene Loks" in patched
    assert "Betroffene Transporte" in patched
    assert "Betroffene Fälle anzeigen" in patched
    assert "Technischer Hinweis anzeigen" in patched
    assert "Kontrolllisten und technische Dateien" in patched
    assert "alter langer Exportbereich" not in patched
    assert "with tab_run:" in patched


def test_patch_export_grid_source_is_idempotent() -> None:
    source = f"before\n# {COMPACT_EXPORT_GRID_MARKER}\nafter"

    assert patch_export_grid_source(source) == source
