from __future__ import annotations

import pandas as pd

from web_app.ui_helpers import chat_dataframe_height, compact_json_html, display_table_frame, format_answer_markdown_text, safe_markdown_text


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


def test_format_answer_markdown_text_separates_metric_rows_and_followup_explanation() -> None:
    rendered = format_answer_markdown_text(
        "2026년 6월 23일 기준 HBM 제품 재공입니다. "
        "D/SA : 10,000 EEAA : 100 FCAA : 10,000 MDAA : 2,000 MUAA : 5,000 "
        "위 결과는 TSV_DIE_TYP 값이 비어 있지 않은 레코드 기준입니다."
    )

    assert "D/SA : 10,000  \nEEAA : 100  \nFCAA : 10,000  \nMDAA : 2,000  \nMUAA : 5,000" in rendered
    assert "MUAA : 5,000\n\n위 결과는" in rendered
