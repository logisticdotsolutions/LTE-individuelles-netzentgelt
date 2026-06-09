from __future__ import annotations
import getpass
from datetime import datetime
from pathlib import Path
from manual_override_batch_module import (
    PHASE5D_BATCH_MARKER,
    create_overrides_from_selected_suggestions,
)
PHASE5D_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_V1_20260608"
OVERRIDE_TYPE_LABELS = {
    "CASE_NOTE": "Bearbeitungsnotiz hinterlegen",
}
def _clean(value):
    return str(value or "").strip()
def demo():
    prefill = {}
    selected_label = "x"
    override_type = "CASE_NOTE"
    form_key = f"manual_override_form_{override_type}_{abs(hash(selected_label))}_{_clean(prefill.get('suggestion_id'))}"
    with st.form(form_key):
        save_only = st.form_submit_button("Override speichern")
        save_and_rebuild = st.form_submit_button("Speichern und neu prüfen", type="primary")
    if not (save_only or save_and_rebuild):
        return
    comment = "x"
    target_loco_no = "x"
    created_by = "x"
    if override_type not in {"CLASSIFY_GAP", "CASE_NOTE"} and not override_value.strip():
        return
    if CHANGE_LOG_PATH.exists():
        pass
