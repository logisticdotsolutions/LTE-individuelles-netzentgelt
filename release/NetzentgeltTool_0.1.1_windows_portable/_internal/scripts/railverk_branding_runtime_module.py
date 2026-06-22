from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from textwrap import dedent
from typing import Any


RAILVERK_BRANDING_RUNTIME_MARKER = "NETZENTGELT_RAILVERK_BRANDING_PHASE11U_V4_20260619"
RAILVERK_TITLE = "RAILVERK IT Solutions e.U."
LTE_TITLE_PREFIX = "Bahnstrom Deutschland"
RAILVERK_FOOTER_LINE_1 = "Konzeption, Fachlogik & Umsetzung: RAILVERK IT Solutions e.U."
RAILVERK_FOOTER_LINE_2 = "railverk.com"


ROOT = Path(__file__).resolve().parents[1]
PIC_DIR_CANDIDATES = [
    ROOT / "data" / "06_pics",
    ROOT / "data" / "06_pic",
]
SUPPORTED_LOGO_SUFFIXES = (".svg", ".png", ".webp", ".jpg", ".jpeg")
GENERATED_PLACEHOLDER_NAMES = {
    "railverk_logo_light.svg",
    "railverk_logo_dark.svg",
}
LOGO_ASSET_STEMS = {
    "full_light": "railverk-logo-tagline",
    "full_dark": "railverk-logo-tagline-on-dark",
    "mark_light": "railverk-mark",
    "mark_dark": "railverk-mark-on-dark",
}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _html(value: str) -> str:
    """Return HTML without Markdown-indenting it into a code block."""
    return dedent(value).strip()


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


def _is_supported_logo(path: Path) -> bool:
    return (
        path.is_file()
        and path.name.lower() not in GENERATED_PLACEHOLDER_NAMES
        and path.suffix.lower() in SUPPORTED_LOGO_SUFFIXES
    )


def _resolve_logo_by_stem(stem: str) -> Path | None:
    """Resolve one explicitly named Railverk logo asset without heuristic fallback."""
    requested_stem = stem.casefold()
    for directory in PIC_DIR_CANDIDATES:
        if not directory.exists():
            continue

        for suffix in SUPPORTED_LOGO_SUFFIXES:
            candidate = directory / f"{stem}{suffix}"
            if _is_supported_logo(candidate):
                return candidate

        for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            if not _is_supported_logo(path):
                continue
            if path.stem.casefold() == requested_stem:
                return path
    return None


def _select_logo_paths() -> dict[str, Path | None]:
    return {
        key: _resolve_logo_by_stem(stem)
        for key, stem in LOGO_ASSET_STEMS.items()
    }


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


def _picture_html(light_uri: str, dark_uri: str, *, alt: str, css_class: str) -> str:
    primary_uri = light_uri or dark_uri
    if not primary_uri:
        return ""
    return _html(
        f"""
        <picture>
        <source srcset="{dark_uri or primary_uri}" media="(prefers-color-scheme: dark)">
        <img src="{primary_uri}" alt="{alt}" class="{css_class}">
        </picture>
        """
    )


def _railverk_header_html() -> str:
    logo_paths = _select_logo_paths()
    light_uri = _data_uri(logo_paths["full_light"])
    dark_uri = _data_uri(logo_paths["full_dark"]) or light_uri
    logo_html = _picture_html(
        light_uri,
        dark_uri,
        alt=RAILVERK_TITLE,
        css_class="railverk-brand-logo",
    )
    if not logo_html:
        return ""
    return _html(
        f"""
        <div class="railverk-brand-header">
        {logo_html}
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
            width: min(420px, 56vw);
            max-height: 132px;
            height: auto;
            object-fit: contain;
            display: block;
        }}
        </style>
        """
    )


def _railverk_sidebar_html() -> str:
    logo_paths = _select_logo_paths()
    full_light_uri = _data_uri(logo_paths["full_light"])
    full_dark_uri = _data_uri(logo_paths["full_dark"]) or full_light_uri
    mark_light_uri = _data_uri(logo_paths["mark_light"]) or full_light_uri
    mark_dark_uri = _data_uri(logo_paths["mark_dark"]) or mark_light_uri
    logo_html = _picture_html(
        full_light_uri,
        full_dark_uri,
        alt=RAILVERK_TITLE,
        css_class="railverk-sidebar-logo",
    )
    if not logo_html:
        return ""
    return _html(
        f"""
        <div class="railverk-sidebar-brand-expanded">
        {logo_html}
        </div>
        <div class="railverk-sidebar-heading">Angemeldet</div>
        <style>
        .railverk-sidebar-brand-expanded {{
            display: flex;
            align-items: center;
            margin: 0.15rem 0 0.75rem 0;
            padding: 0.3rem 0.1rem 0.45rem 0.1rem;
        }}
        .railverk-sidebar-logo {{
            width: min(230px, 100%);
            max-height: 72px;
            height: auto;
            object-fit: contain;
            display: block;
        }}
        .railverk-sidebar-heading {{
            font-size: 1.05rem;
            font-weight: 700;
            margin: 0.3rem 0 0.35rem 0;
        }}
        [data-testid="stSidebar"][aria-expanded="false"]::before {{
            content: "";
            position: fixed;
            top: 0.75rem;
            left: 0.58rem;
            width: 2.2rem;
            height: 2.2rem;
            background-image: url("{mark_light_uri}");
            background-repeat: no-repeat;
            background-position: center;
            background-size: contain;
            z-index: 999999;
            pointer-events: none;
        }}
        @media (prefers-color-scheme: dark) {{
            [data-testid="stSidebar"][aria-expanded="false"]::before {{
                background-image: url("{mark_dark_uri}");
            }}
        }}
        </style>
        """
    )


def _railverk_footer_html() -> str:
    return _html(
        f"""
        <div class="railverk-attribution-footer">
        <strong>{RAILVERK_FOOTER_LINE_1}</strong><br>
        <span>{RAILVERK_FOOTER_LINE_2}</span>
        </div>
        <style>
        .railverk-attribution-footer {{
            position: fixed;
            right: 1.0rem;
            bottom: 0.55rem;
            z-index: 999998;
            padding: 0.35rem 0.55rem;
            border-radius: 0.45rem;
            border: 1px solid rgba(148, 163, 184, 0.24);
            background: rgba(255, 255, 255, 0.78);
            color: rgba(15, 23, 42, 0.82);
            font-size: 0.76rem;
            line-height: 1.25;
            pointer-events: none;
            backdrop-filter: blur(4px);
        }}
        .railverk-attribution-footer span {{
            opacity: 0.82;
        }}
        @media (prefers-color-scheme: dark) {{
            .railverk-attribution-footer {{
                background: rgba(15, 23, 42, 0.78);
                color: rgba(248, 250, 252, 0.84);
            }}
        }}
        </style>
        """
    )


def install_railverk_branding_runtime() -> None:
    import streamlit as st

    if getattr(st, "_PHASE11U_RAILVERK_BRANDING_PATCHED", False):
        return

    original_title = st.title
    original_markdown = st.markdown
    original_caption = st.caption
    original_sidebar_markdown = st.sidebar.markdown

    def patched_title(body, *args, **kwargs):
        text = _clean(body)
        if should_use_railverk_branding() and LTE_TITLE_PREFIX in text:
            html = _railverk_header_html()
            if html:
                return original_markdown(html, unsafe_allow_html=True)
            return original_title(RAILVERK_TITLE, *args, **kwargs)
        return original_title(body, *args, **kwargs)

    def patched_caption(body, *args, **kwargs):
        return original_caption(body, *args, **kwargs)

    def patched_markdown(body, *args, **kwargs):
        text = _clean(body)
        if should_use_railverk_branding() and "Konzeption" in text and (
            "Christoph Orgl" in text or "LTE-group" in text
        ):
            return original_markdown(_railverk_footer_html(), unsafe_allow_html=True)
        return original_markdown(body, *args, **kwargs)

    def patched_sidebar_markdown(body, *args, **kwargs):
        text = _clean(body)
        if should_use_railverk_branding() and text == "### Angemeldet":
            html = _railverk_sidebar_html()
            if html:
                return original_sidebar_markdown(html, unsafe_allow_html=True)
        return original_sidebar_markdown(body, *args, **kwargs)

    st.title = patched_title
    st.caption = patched_caption
    st.markdown = patched_markdown
    try:
        st.sidebar.markdown = patched_sidebar_markdown
    except Exception:
        pass
    st._PHASE11U_RAILVERK_BRANDING_PATCHED = True
