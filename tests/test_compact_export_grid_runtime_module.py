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


def test_patch_export_grid_source_replaces_verbose_primary_loop() -> None:
    source = '''before
            for group_key, group_config in PRIMARY_EXPORT_GROUPS.items():
                st.divider()
                st.markdown(f"### {group_config['title']}")

                render_nutzungsmeldung_export_section(
                    title="Nutzungsmeldung",
                    export_label=group_config["file_label"],
                    performing_ru_values=tuple(group_config["performing_ru_values"]),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix=f"primary_nutzung_{group_key.lower()}",
                )

                render_aufenthaltsereignis_export_section(
                    title="Aufenthaltsereignisse",
                    export_label=group_config["file_label"],
                    performing_ru_values=tuple(group_config["performing_ru_values"]),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix=f"primary_aufenthalt_{group_key.lower()}",
                )
after'''

    patched = patch_export_grid_source(source)

    assert COMPACT_EXPORT_GRID_MARKER in patched
    assert "primary_columns = st.columns" in patched
    assert "Nutzung herunterladen" in patched
    assert "Aufenthalt herunterladen" in patched
    assert "render_nutzungsmeldung_export_section" not in patched
    assert "render_aufenthaltsereignis_export_section" not in patched


def test_patch_export_grid_source_is_idempotent() -> None:
    source = f"before\n# {COMPACT_EXPORT_GRID_MARKER}\nafter"

    assert patch_export_grid_source(source) == source
