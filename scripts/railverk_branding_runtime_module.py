from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any


RAILVERK_BRANDING_RUNTIME_MARKER = "NETZENTGELT_RAILVERK_BRANDING_PHASE11U_V2_20260619"
RAILVERK_TITLE = "RAILVERK IT Solutions e.U."
LTE_TITLE_PREFIX = "Bahnstrom Deutschland"


ROOT = Path(__file__).resolve().parents[1]
PIC_DIR_CANDIDATES = [
    ROOT / "data" / "06_pic",
    ROOT / "data" / "06_pics",
]
SUPPORTED_LOGO_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".webp"}
GENERATED_PLACEHOLDER_NAMES = {
    "railverk_logo_light.svg",
    "railverk_logo_dark.svg",
}


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


def _existing_logo_files() -> list[Path]:
    files: list[Path] = []
    for directory in PIC_DIR_CANDIDATES:
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if not path.is_file():
                continue
            if path.name.lower() in GENERATED_PLACEHOLDER_NAMES:
                continue
            if path.suffix.lower() not in SUPPORTED_LOGO_SUFFIXES:
                continue
            files.append(path)
    return sorted(files, key=lambda item: item.name.lower())


def _score_logo(path: Path, *, dark: bool) -> tuple[int, str]:
    name = path.name.lower()
    score = 0
    if "railverk" in name:
        score += 40
    if "logo" in name:
        score += 30
    if dark:
        if any(token in name for token in ["dark", "dunkel", "black", "schwarz", "negative", "white"]):
            score += 20
    else:
        if any(token in name for token in ["light", "hell", "white", "weiss", "weiß", "positive", "black"]):
            score += 20
    # SVG/PNG are preferred in browser rendering, but all supported formats are accepted.
    if path.suffix.lower() in {".svg", ".png"}:
        score += 5
    return (-score, name)


def _select_logo_pair() -> tuple[Path | None, Path | None]:
    files = _existing_logo_files()
    if not files:
        return None, None
    light = sorted(files, key=lambda path: _score_logo(path, dark=False))[0]
    dark = sorted(files, key=lambda path: _score_logo(path, dark=True))[0]
    return light, dark


def _data_uri(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        payload = path.read_bytes()
    except OSError:
        return ""
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _railverk_header_html() -> str:
    light_path, dark_path = _select_logo_pair()
    light_uri = _data_uri(light_path)
    dark_uri = _data_uri(dark_path) or light_uri
    if not light_uri and not dark_uri:
        return ""
    return f"""
    <div class="railverk-brand-header">
        <picture>
            <source srcset="{dark_uri}" media="(prefers-color-scheme: dark)">
            <img src="{light_uri or dark_uri}" alt="RAILVERK IT Solutions e.U." class="railverk-brand-logo">
        </picture>
    </div>
    <style>
    .railverk-brand-header {{
        display: flex;
        align-items: center;
        margin: 0.35rem 0 1.0rem 0;
        padding: 0.65rem 0.8rem;
        border-radius: 0.75rem;
        border: 1px solid rgba(148, 163, 184, 0.28);
        background: rgba(148, 163, 184, 0.08);
    }}
    .railverk-brand-logo {{
        width: min(360px, 48vw);
        max-height: 120px;
        height: auto;
        object-fit: contain;
        display: block;
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
