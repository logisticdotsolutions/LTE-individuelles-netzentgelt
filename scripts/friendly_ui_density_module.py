from __future__ import annotations

import streamlit as st


def apply_density_cleanup() -> None:
    """Reduce visual noise while keeping all information and controls available."""
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.2rem !important;
            padding-bottom: 1.5rem !important;
        }

        [data-testid="stVerticalBlock"] > div {
            gap: 0.45rem;
        }

        [data-testid="stCaptionContainer"] {
            font-size: 0.82rem !important;
            line-height: 1.25 !important;
        }

        [data-testid="stAlert"] {
            padding: 0.55rem 0.75rem !important;
            border-radius: 6px !important;
        }

        [data-testid="stAlert"] p {
            margin: 0 !important;
            font-size: 0.9rem !important;
            line-height: 1.3 !important;
        }

        [data-testid="stMarkdownContainer"] div[style*="border-left: 4px solid #4f81bd"] {
            margin-top: 0.15rem !important;
            margin-bottom: 0.45rem !important;
            padding: 0.15rem 0 !important;
            border-left: 0 !important;
            background: transparent !important;
            border-radius: 0 !important;
            font-size: 0.82rem !important;
            opacity: 0.72;
        }

        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            font-size: 0.76rem !important;
        }

        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] .stButton > button p {
            background: var(--lte-surface) !important;
            color: var(--lte-text) !important;
        }

        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary p {
            background: var(--lte-surface-soft) !important;
            color: var(--lte-text) !important;
        }

        [data-testid="stExpander"] summary svg {
            color: var(--lte-text) !important;
            fill: var(--lte-text) !important;
        }

        [data-testid="stStatusWidget"],
        [data-testid="stSpinner"] {
            color: var(--lte-text) !important;
        }

        [data-testid="stStatusWidget"] svg,
        [data-testid="stSpinner"] svg {
            color: var(--lte-accent) !important;
            fill: var(--lte-accent) !important;
        }

        h1 {
            font-size: 1.85rem !important;
            margin-bottom: 0.2rem !important;
        }

        h2, h3 {
            margin-top: 0.8rem !important;
            margin-bottom: 0.25rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
