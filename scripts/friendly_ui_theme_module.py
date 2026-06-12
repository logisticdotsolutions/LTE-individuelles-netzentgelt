from __future__ import annotations

import streamlit as st


SESSION_KEY = "ui_dark_mode"


def _palette(dark_mode: bool) -> dict[str, str]:
    if dark_mode:
        return {
            "app": "#111827",
            "sidebar": "#182235",
            "surface": "#1f2937",
            "surface_soft": "#263244",
            "text": "#f3f4f6",
            "muted": "#b8c2cf",
            "border": "#3b4758",
            "accent": "#7aa2d6",
            "accent_soft": "rgba(122, 162, 214, 0.18)",
        }
    return {
        "app": "#f7f9fc",
        "sidebar": "#eef3f8",
        "surface": "#ffffff",
        "surface_soft": "#f5f8fb",
        "text": "#243447",
        "muted": "#66788a",
        "border": "#d9e2ec",
        "accent": "#4f81bd",
        "accent_soft": "rgba(79, 129, 189, 0.12)",
    }


def apply_theme(*, dark_mode: bool | None = None) -> bool:
    """Apply a calm application theme without changing fachliche UI behavior."""
    if dark_mode is None:
        dark_mode = bool(st.session_state.get(SESSION_KEY, False))
    palette = _palette(bool(dark_mode))

    st.markdown(
        f"""
        <style>
        :root {{
            --lte-app: {palette['app']};
            --lte-sidebar: {palette['sidebar']};
            --lte-surface: {palette['surface']};
            --lte-surface-soft: {palette['surface_soft']};
            --lte-text: {palette['text']};
            --lte-muted: {palette['muted']};
            --lte-border: {palette['border']};
            --lte-accent: {palette['accent']};
            --lte-accent-soft: {palette['accent_soft']};
        }}

        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > .main {{
            background: var(--lte-app) !important;
            color: var(--lte-text) !important;
        }}

        [data-testid="stSidebar"] {{
            background: var(--lte-sidebar) !important;
            border-right: 1px solid var(--lte-border) !important;
        }}

        [data-testid="stHeader"] {{
            background: transparent !important;
        }}

        h1, h2, h3, h4, h5, h6, p, label,
        [data-testid="stMarkdownContainer"],
        [data-testid="stCaptionContainer"] {{
            color: var(--lte-text) !important;
        }}

        [data-testid="stCaptionContainer"] {{
            opacity: 0.72;
        }}

        [data-testid="stForm"],
        [data-testid="stExpander"],
        [data-testid="stMetric"],
        [data-testid="stDataFrame"] {{
            background: var(--lte-surface) !important;
            border: 1px solid var(--lte-border) !important;
            border-radius: 8px !important;
        }}

        [data-baseweb="input"] > div,
        [data-baseweb="select"] > div,
        [data-baseweb="textarea"] > div {{
            background: var(--lte-surface) !important;
            border-color: var(--lte-border) !important;
            color: var(--lte-text) !important;
        }}

        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea,
        [data-baseweb="select"] input,
        [data-baseweb="select"] div,
        input,
        textarea {{
            color: var(--lte-text) !important;
            caret-color: var(--lte-text) !important;
            -webkit-text-fill-color: var(--lte-text) !important;
        }}

        [data-baseweb="input"] input::placeholder,
        [data-baseweb="textarea"] textarea::placeholder,
        [data-baseweb="select"] input::placeholder,
        input::placeholder,
        textarea::placeholder {{
            color: var(--lte-muted) !important;
            opacity: 1 !important;
            -webkit-text-fill-color: var(--lte-muted) !important;
        }}

        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        textarea:-webkit-autofill,
        select:-webkit-autofill {{
            -webkit-text-fill-color: var(--lte-text) !important;
            caret-color: var(--lte-text) !important;
            box-shadow: 0 0 0 1000px var(--lte-surface) inset !important;
            -webkit-box-shadow: 0 0 0 1000px var(--lte-surface) inset !important;
            transition: background-color 9999s ease-in-out 0s;
        }}

        [data-baseweb="input"] svg,
        [data-baseweb="select"] svg,
        [data-baseweb="textarea"] svg {{
            color: var(--lte-muted) !important;
            fill: var(--lte-muted) !important;
        }}

        [data-baseweb="tab-list"] {{
            gap: 0.25rem;
            border-bottom: 1px solid var(--lte-border);
        }}

        [data-baseweb="tab"] {{
            border-radius: 6px 6px 0 0 !important;
            padding: 0.55rem 0.8rem !important;
            color: var(--lte-muted) !important;
        }}

        [aria-selected="true"][data-baseweb="tab"] {{
            background: var(--lte-accent-soft) !important;
            color: var(--lte-text) !important;
        }}

        .stButton > button,
        .stDownloadButton > button,
        [data-testid="stFormSubmitButton"] > button {{
            border-radius: 6px !important;
            border: 1px solid var(--lte-border) !important;
            box-shadow: none !important;
        }}

        hr {{
            border-color: var(--lte-border) !important;
            opacity: 0.75;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    return bool(dark_mode)


def render_theme_toggle() -> bool:
    """Render a compact sidebar toggle and re-apply the selected theme."""
    dark_mode = st.sidebar.toggle(
        "Dunkelmodus",
        value=bool(st.session_state.get(SESSION_KEY, False)),
        key=SESSION_KEY,
        help="Optional dunkle Darstellung. Der freundliche Light-Mode ist Standard.",
    )
    apply_theme(dark_mode=dark_mode)
    return bool(dark_mode)
