from __future__ import annotations
import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hotfix", ROOT / "apply_loco_bookmark_hotfix.py")
hotfix = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(hotfix)

operator_fixture = '''            st.session_state["timeline_preview_loco"] = selected_loco
            st.success(
                f"Lok {selected_loco} wurde vorgemerkt. Öffne jetzt den Tab '4. Lok prüfen'."
            )
'''

app_header_fixture = '''with tab_timeline:
    st.header("🔎 Lok-Detailprüfung")

    core_path = EXPORT_DIR / "core_loco_timeline.csv"
'''

app_select_fixture = '''        selected_loco = st.selectbox(
            "Lok auswählen",
            loco_values,
            index=0 if loco_values else None,
            key="timeline_detail_loco",
        )
'''

def main():
    patched_operator = hotfix._patch_operator(operator_fixture)
    assert 'timeline_detail_loco' in patched_operator
    assert 'timeline_bookmarked_loco' in patched_operator
    assert "Tab '4. Lok prüfen'" in patched_operator

    patched_app = hotfix._patch_app(app_header_fixture + "\n" + app_select_fixture)
    assert 'Vorgemerkte Lok:' in patched_app
    assert 'timeline_bookmarked_loco' in patched_app
    assert 'st.session_state.pop("timeline_detail_loco", None)' in patched_app

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "test.py"
        hotfix._write(path, patched_operator, "\r\n")
        assert b"\r\n" in path.read_bytes()

    print("OK: Patch-Logik erfolgreich getestet.")
    print("OK: Verweis auf Tab '4. Lok prüfen'.")
    print("OK: Sichtbare Vormerkung und korrekter Widget-Key vorhanden.")
    print("OK: Windows-CRLF bleibt erhalten.")

if __name__ == "__main__":
    main()
