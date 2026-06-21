from __future__ import annotations

import pandas as pd

from web_app.ui_helpers import chat_dataframe_height, compact_json_html, display_table_frame


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
