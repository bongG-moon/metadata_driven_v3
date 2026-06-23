from __future__ import annotations

import pandas as pd

from web_app.ui_helpers import (
    chat_dataframe_height,
    compact_json_html,
    display_table_frame,
    safe_markdown_text,
    separate_data_lines_from_explanation,
)


def test_table_height_uses_auto_for_small_results_and_caps_large_results() -> None:
    assert chat_dataframe_height(1) == "auto"
    assert chat_dataframe_height(8) == "auto"
    assert isinstance(chat_dataframe_height(9), int)
    assert chat_dataframe_height(1000) == 460


def test_display_table_frame_formats_quantity_columns_only() -> None:
    frame = pd.DataFrame([{"WORK_DT": "20260612", "MCP_NO": "L-217", "WIP": 9876.5, "PRODUCTION": 12345}])
    formatted = display_table_frame(frame, "comma")

    assert formatted.loc[0, "WORK_DT"] == "20260612"
    assert formatted.loc[0, "MCP_NO"] == "L-217"
    assert formatted.loc[0, "WIP"] == "9,876.5"
    assert formatted.loc[0, "PRODUCTION"] == "12,345"
    assert frame.loc[0, "PRODUCTION"] == 12345


def test_compact_json_html_escapes_values() -> None:
    rendered = compact_json_html({"unsafe": "<tag>", "ok": True, "empty": None})

    assert "&lt;tag&gt;" in rendered
    assert "compact-json-boolean" in rendered
    assert "compact-json-null" in rendered


def test_safe_markdown_text_escapes_tildes_without_double_escaping() -> None:
    rendered = safe_markdown_text(r"OPER D/A1~D/A6 and ~~HOLD~~ and already \~safe")

    assert rendered == r"OPER D/A1\~D/A6 and \~\~HOLD\~\~ and already \~safe"


def test_separate_data_lines_from_explanation_splits_inline_summary() -> None:
    text = "MUAA : 5,000 위 결과는 TSV_DIE_TYP 값이 비어 있지 않은 레코드만 대상으로 합니다."

    rendered = separate_data_lines_from_explanation(text)

    assert rendered == "MUAA : 5,000\n\n위 결과는 TSV_DIE_TYP 값이 비어 있지 않은 레코드만 대상으로 합니다."


def test_separate_data_lines_from_explanation_keeps_normal_sentence() -> None:
    text = "2026년 6월 23일 기준 결과입니다. 위 결과는 wip_today에서 추출되었습니다."

    assert separate_data_lines_from_explanation(text) == text
