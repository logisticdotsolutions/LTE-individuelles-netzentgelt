from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


RAILVERK_BRANDING_RUNTIME_MARKER = "NETZENTGELT_RAILVERK_BRANDING_PHASE11U_V1_20260619"
RAILVERK_TITLE = "RAILVERK IT Solutions e.U."
LTE_TITLE_PREFIX = "Bahnstrom Deutschland"


ROOT = Path(__file__).resolve().parents[1]
PIC_DIR = ROOT / "data" / "06_pic"
LIGHT_LOGO_PATH = PIC_DIR / "railverk_logo_light.svg"
DARK_LOGO_PATH = PIC_DIR / "railverk_logo_dark.svg"


def _clean(value: object) -> str:
    return str(value or "").strip()


def is_lte_brand_user(user: Any) -> bool:
    """Return True when the logged-in user should keep LTE branding."""
    if user is None:
        return True
    role = _clean(getattr(user, "role_code", "")).upper()
    username = _clean(getattr(user, "username", "")).lower()
    display_name = _clean(getattr(user, "display_name", "")).lower()
    if role in {"LTE_DE", "LTE_NL", "LTE_DE_NL"}:
        return True
    return "lte" in username or "lte" in display_name


def should_use_railverk_branding() -> bool:
    try:
        from local_auth_ui_module import get_current_user
    except Exception:
        return False
    return not is_lte_brand_user(get_current_user())


def _data_uri(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError:
        return ""
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _railverk_header_html() -> str:
    light_uri = _data_uri(LIGHT_LOGO_PATH)
    dark_uri = _data_uri(DARK_LOGO_PATH) or light_uri
    if not light_uri and not dark_uri:
        return ""
    return f"""
    <div class="railverk-brand-header">
        <picture>
            <source srcset="{dark_uri}" media="(prefers-color-scheme: dark)">
            <img src="{light_uri or dark_uri}" alt="RAILVERK IT Solutions" class="railverk-brand-logo">
        </picture>
        <div class="railverk-brand-text">
            <div class="railverk-brand-title">{RAILVERK_TITLE}</div>
            <div class="railverk-brand-subtitle">Netzentgelt-Prüfung und Exportvorbereitung</div>
        </div>
    </div>
    <style>
    .railverk-brand-header {{
        display: flex;
        align-items: center;
        gap: 1.1rem;
        margin: 0.4rem 0 1.0rem 0;
        padding: 0.8rem 1.0rem;
        border-radius: 0.75rem;
        border: 1px solid rgba(20, 184, 166, 0.35);
        background: rgba(20, 184, 166, 0.08);
    }}
    .railverk-brand-logo {{
        width: min(280px, 42vw);
        height: auto;
        display: block;
    }}
    .railverk-brand-title {{
        font-weight: 800;
        font-size: 1.3rem;
        line-height: 1.2;
    }}
    .railverk-brand-subtitle {{
        font-size: 0.92rem;
        opacity: 0.78;
        margin-top: 0.2rem;
    }}
    </style>
    """


def install_railverk_branding_runtime() -> None:
    import streamlit as st

    if getattr(st, "_PHASE11U_RAILVERK_BRANDING_PATCHED", False):
        return

    original_title = st.title
    original_markdown = st.markdown
    original_caption = st.caption

    def patched_title(body, *args, **kwargs):
        text = _clean(body)
        if should_use_railverk_branding() and LTE_TITLE_PREFIX in text:
            html = _railverk_header_html()
            if html:
                return original_markdown(html, unsafe_allow_html=True)
            return original_title(RAILVERK_TITLE, *args, **kwargs)
        return original_title(body, *args, **kwargs)

    def patched_caption(body, *args, **kwargs):
        text = _clean(body)
        if should_use_railverk_branding() and "individuelle Netzentgelt" in text:
            return original_caption(
                "Gebrandete RAILVERK-Version für operative Prüfung, Plausibilisierung und Exportvorbereitung.",
                *args,
                **kwargs,
            )
        return original_caption(body, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        text = _clean(body)
        if should_use_railverk_branding() and ("Christoph Orgl" in text or "LTE-group" in text):
            branded = text.replace("Christoph Orgl", RAILVERK_TITLE).replace("LTE-group", "railverk.com")
            return original_markdown(branded, *args, **kwargs)
        return original_markdown(body, *args, **kwargs)

    st.title = patched_title
    st.caption = patched_caption
    st.markdown = patched_markdown
    st._PHASE11U_RAILVERK_BRANDING_PATCHED = True
