"""Client-side guided tour for operators without Streamlit reruns."""
from __future__ import annotations
import json
import streamlit as st
import streamlit.components.v1 as components

PHASE10C_OPERATOR_TOUR_MARKER = "NETZENTGELT_OPERATOR_GUIDED_TOUR_PHASE10C_V1_20260611"

_STEPS = (
    {"title": "Willkommen zur Tagesprüfung", "body": "Die Oberfläche führt dich vom Rohdatenimport bis zum Export. Die Tour markiert die wichtigsten Reiter, Schaltflächen und Eingabefelder direkt auf der Seite.", "target": "Bahnstrom Deutschland"},
    {"title": "1. Daten aktualisieren", "body": "Mit dieser Schaltfläche lädst du die aktuellen Rohdaten und startest danach die vollständige Neuberechnung. Während des Laufs bitte nicht erneut klicken.", "target": "Daten aktualisieren und neu prüfen"},
    {"title": "2. Offene Aufgaben", "body": "Hier findest du blockierende Lok-Tage und Hinweise. Die Tabellen sind nach Loknummer sortiert. Beginne immer mit den gesperrten Fällen.", "target": "2. Offene Aufgaben"},
    {"title": "Fall direkt öffnen", "body": "Wähle unter der Aufgabenliste die betroffene Loknummer und klicke auf 'Fall öffnen'. Kopieren oder Merken der Loknummer ist nicht mehr erforderlich.", "target": "Fall öffnen"},
    {"title": "3. Fall bearbeiten", "body": "Hier dokumentierst du eine lokale Korrektur oder fachliche Klassifikation. Dropdowns sichern konsistente Bezeichnungen. Pflichtfelder und Datumswerte werden validiert.", "target": "3. Fall bearbeiten"},
    {"title": "Kaltabstellung klassifizieren", "body": "Für plausible längere Stehzeiten wählst du 'Unterbrechung fachlich klassifizieren' und anschließend 'Mögliche kalte Abstellung'. Die Begründung bleibt auditierbar erhalten.", "target": "Unterbrechung fachlich klassifizieren"},
    {"title": "4. Lok prüfen", "body": "Diese Detailansicht zeigt die 30-Tage-Zeitachse einer Lok mit Grenzübertritten, GAPs und Transportkontext. Im geöffneten Fall steht derselbe Kontext kompakt zur Verfügung.", "target": "4. Lok prüfen"},
    {"title": "5. Exporte erstellen", "body": "Erstelle die XLSX-Exporte erst nach der fachlichen Prüfung. Blockierende Root-Fehler müssen korrigiert oder nachvollziehbar als Ausnahme dokumentiert sein.", "target": "5. Exporte erstellen"},
    {"title": "Technische Reiter", "body": "Die Technik-Reiter dienen der Fehlersuche. Die Pipeline ist ausschließlich für ADMIN sichtbar. Fachanwender arbeiten im Normalfall mit Tagesprüfung, Aufgaben, Fallbearbeitung und Export.", "target": "Technik: Regelqueue"},
)


def _tour_html() -> str:
    steps = json.dumps(_STEPS, ensure_ascii=False)
    return f"""
    <button id="netzentgelt-tour-launch" style="width:100%;padding:.55rem .7rem;border:1px solid #bbb;border-radius:.45rem;background:white;cursor:pointer;font-weight:600;">▶️ Tour starten</button>
    <script>
    (() => {{
      const steps = {steps};
      const doc = window.parent.document;
      let index = 0;

      const removeFocus = () => {{
        const old = doc.getElementById('netzentgelt-tour-focus');
        if (old) old.remove();
      }};

      const findTarget = (text) => {{
        const all = Array.from(doc.querySelectorAll('button, [role="tab"], label, h1, h2, h3, h4, p, span, div'))
          .filter(el => el.offsetParent !== null && (el.innerText || '').trim().includes(text));
        all.sort((a, b) => {{
          const ra = a.getBoundingClientRect();
          const rb = b.getBoundingClientRect();
          return (ra.width * ra.height) - (rb.width * rb.height);
        }});
        return all[0] || null;
      }};

      const drawFocus = (target) => {{
        removeFocus();
        if (!target) return;
        const rect = target.getBoundingClientRect();
        const focus = doc.createElement('div');
        focus.id = 'netzentgelt-tour-focus';
        focus.style.cssText = `position:fixed;z-index:999998;pointer-events:none;border:4px solid #1f6feb;border-radius:10px;box-shadow:0 0 0 9999px rgba(15,23,42,.20),0 0 0 5px rgba(31,111,235,.22);transition:all .2s ease;left:${{Math.max(rect.left - 6, 4)}}px;top:${{Math.max(rect.top - 6, 4)}}px;width:${{Math.max(rect.width + 12, 24)}}px;height:${{Math.max(rect.height + 12, 24)}}px;`;
        doc.body.appendChild(focus);
      }};

      const ensureOverlay = () => {{
        let overlay = doc.getElementById('netzentgelt-guided-tour');
        if (overlay) return overlay;
        overlay = doc.createElement('div');
        overlay.id = 'netzentgelt-guided-tour';
        overlay.innerHTML = `
          <div id="netzentgelt-tour-card" style="position:fixed;right:24px;bottom:24px;z-index:999999;width:min(430px,calc(100vw - 48px));background:#fff;border:1px solid #d0d7de;border-radius:12px;box-shadow:0 12px 38px rgba(0,0,0,.22);padding:18px;font-family:Arial,sans-serif;color:#1f2937;">
            <div id="netzentgelt-tour-progress" style="font-size:12px;color:#6b7280;margin-bottom:6px;"></div>
            <div id="netzentgelt-tour-title" style="font-size:18px;font-weight:700;margin-bottom:8px;"></div>
            <div id="netzentgelt-tour-body" style="font-size:14px;line-height:1.45;margin-bottom:14px;"></div>
            <div style="display:flex;gap:8px;justify-content:space-between;align-items:center;">
              <button id="netzentgelt-tour-close" style="padding:7px 10px;border:1px solid #ccc;border-radius:7px;background:#fff;cursor:pointer;">Tour abbrechen</button>
              <div style="display:flex;gap:8px;">
                <button id="netzentgelt-tour-back" style="padding:7px 10px;border:1px solid #ccc;border-radius:7px;background:#fff;cursor:pointer;">← Zurück</button>
                <button id="netzentgelt-tour-next" style="padding:7px 10px;border:1px solid #1f6feb;border-radius:7px;background:#1f6feb;color:#fff;cursor:pointer;">Weiter →</button>
              </div>
            </div>
          </div>`;
        doc.body.appendChild(overlay);
        doc.getElementById('netzentgelt-tour-close').onclick = closeTour;
        doc.getElementById('netzentgelt-tour-back').onclick = () => {{ if (index > 0) {{ index -= 1; render(); }} }};
        doc.getElementById('netzentgelt-tour-next').onclick = () => {{ if (index < steps.length - 1) {{ index += 1; render(); }} else closeTour(); }};
        return overlay;
      }};

      const closeTour = () => {{
        removeFocus();
        const overlay = doc.getElementById('netzentgelt-guided-tour');
        if (overlay) overlay.remove();
      }};

      const render = () => {{
        ensureOverlay();
        const step = steps[index];
        doc.getElementById('netzentgelt-tour-progress').innerText = `Schritt ${{index + 1}} von ${{steps.length}}`;
        doc.getElementById('netzentgelt-tour-title').innerText = step.title;
        doc.getElementById('netzentgelt-tour-body').innerText = step.body;
        doc.getElementById('netzentgelt-tour-back').disabled = index === 0;
        doc.getElementById('netzentgelt-tour-next').innerText = index === steps.length - 1 ? 'Tour beenden' : 'Weiter →';
        const target = findTarget(step.target);
        if (!target) {{ removeFocus(); return; }}
        target.scrollIntoView({{behavior:'smooth', block:'center'}});
        window.setTimeout(() => drawFocus(target), 250);
      }};

      document.getElementById('netzentgelt-tour-launch').onclick = () => {{ index = 0; render(); }};
    }})();
    </script>
    """


def render_operator_tour_sidebar() -> None:
    """Render a lightweight client-side launcher; navigation does not rerun Streamlit."""
    st.sidebar.markdown("### Hilfe")
    with st.sidebar:
        components.html(_tour_html(), height=48)
    st.sidebar.caption("Die Tour erklärt Reiter, Schaltflächen und Pflichtfelder direkt auf der Oberfläche.")
    st.sidebar.divider()
