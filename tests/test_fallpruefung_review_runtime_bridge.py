from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fallpruefung_review_runtime_bridge as module  # noqa: E402


class DummyTab:
    def __init__(self, label: str) -> None:
        self.label = label
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_count += 1
        return False


def _timeline_with_stand(duration_minutes: int) -> pd.DataFrame:
    previous_end = pd.Timestamp("2026-06-09 10:00:00")
    following_start = previous_end + pd.Timedelta(minutes=duration_minutes)

    return pd.DataFrame(
        [
            {
                "row_type": "MOVEMENT",
                "loco_no": "91801234567-8",
                "sequence_ts": "2026-06-09 09:00:00",
                "period_start_utc": "2026-06-09 09:00:00",
                "period_end_utc": previous_end,
                "destination_name": "München Nord",
                "origin_name": "Augsburg",
                "report_scope": "IN_REPORT",
                "transport_number": "T-001",
                "source_table": "raw_locomotivemovement",
                "source_row_id": "1",
            },
            {
                "row_type": "MOVEMENT",
                "loco_no": "91801234567-8",
                "sequence_ts": following_start,
                "period_start_utc": following_start,
                "period_end_utc": following_start + pd.Timedelta(minutes=30),
                "destination_name": "Regensburg",
                "origin_name": "München Nord",
                "report_scope": "IN_REPORT",
                "transport_number": "T-002",
                "source_table": "raw_locomotivemovement",
                "source_row_id": "2",
            },
        ]
    )


def test_review_tab_is_hidden_and_renderer_is_routed_into_case_tab(monkeypatch) -> None:
    rendered_labels: list[list[str]] = []
    routed_calls: list[dict[str, object]] = []

    def original_tabs(labels):
        rendered_labels.append([str(label) for label in labels])
        return [DummyTab(str(label)) for label in labels]

    def original_renderer(**kwargs) -> None:
        routed_calls.append(kwargs)

    monkeypatch.setattr(module.st, "tabs", original_tabs)
    monkeypatch.setattr(module.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.review_ui, "render_phase6d_review_lists", original_renderer)

    runtime = module.install_fallpruefung_review_integration()
    try:
        tabs = module.st.tabs(
            [
                "1. Tagesprüfung",
                "2. Offene Aufgaben",
                module.FALL_TAB_LABEL,
                "4. Lok prüfen",
                "5. Exporte erstellen",
                module.REVIEW_TAB_LABEL,
            ]
        )

        assert rendered_labels[0][5] == module.HIDDEN_REVIEW_TAB_LABEL
        assert tabs[5].label == module.HIDDEN_REVIEW_TAB_LABEL

        payload = {
            "stand_candidates": pd.DataFrame(),
            "gap_context_review": pd.DataFrame(),
            "uncertain_gaps": pd.DataFrame(),
        }
        module.review_ui.render_phase6d_review_lists(**payload)

        assert routed_calls == [payload]
        assert tabs[2].enter_count == 1
    finally:
        module.restore_fallpruefung_review_integration(runtime)

    assert module.st.tabs is original_tabs
    assert module.review_ui.render_phase6d_review_lists is original_renderer


def test_cold_stand_is_proposed_only_for_gap_strictly_over_120_minutes(monkeypatch) -> None:
    def original_tabs(labels):
        return [DummyTab(str(label)) for label in labels]

    monkeypatch.setattr(module.st, "tabs", original_tabs)
    monkeypatch.setattr(module.st, "markdown", lambda *_args, **_kwargs: None)

    runtime = module.install_fallpruefung_review_integration()
    try:
        exactly_120 = module.suggestion_module._suggest_cold_stands(
            _timeline_with_stand(120)
        )
        over_120 = module.suggestion_module._suggest_cold_stands(
            _timeline_with_stand(121)
        )
    finally:
        module.restore_fallpruefung_review_integration(runtime)

    assert exactly_120 == []
    assert len(over_120) == 1
    assert over_120[0].classification_code == "COLD_STAND"
    assert over_120[0].override_type == "CLASSIFY_GAP"
