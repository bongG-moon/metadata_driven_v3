from __future__ import annotations

import html
import json
import re
from typing import Any

import pandas as pd


TABLE_MIN_HEIGHT = 82
TABLE_MAX_HEIGHT = 460
TABLE_HEADER_HEIGHT = 34
TABLE_ROW_HEIGHT = 32
TABLE_VERTICAL_PADDING = 12
TABLE_AUTO_HEIGHT_ROWS = 8
QUANTITY_COLUMN_HINTS = (
    "WIP",
    "PRODUCTION",
    "PLAN",
    "OUT_PLAN",
    "INPUT_PLAN",
    "TARGET",
    "QTY",
    "COUNT",
    "RATE",
    "BALANCE",
    "DIE",
    "WF",
)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def compact_json_html(value: Any) -> str:
    raw = html.escape(json_text(value))
    raw = raw.replace("&quot;", '"')
    return (
        raw.replace("null", '<span class="compact-json-null">null</span>')
        .replace("true", '<span class="compact-json-boolean">true</span>')
        .replace("false", '<span class="compact-json-boolean">false</span>')
    )


def safe_markdown_text(value: Any) -> str:
    text = str(value or "")
    # Langflow/API 응답에 포함된 ~ 문자가 Markdown 취소선으로 해석되지 않게 막습니다.
    return re.sub(r"(?<!\\)~", r"\\~", text)


def separate_data_lines_from_explanation(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    rendered_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line
        split_line = False
        for marker in ("위 결과는", "이 결과는", "해당 결과는", "참고:", "참고로"):
            index = line.find(marker)
            if index <= 0:
                continue
            leading_text = line[:index].rstrip()
            trailing_text = line[index:].lstrip()
            if _looks_like_inline_result_line(leading_text):
                rendered_lines.append(leading_text)
                rendered_lines.append("")
                rendered_lines.append(trailing_text)
                split_line = True
                break
        if not split_line:
            rendered_lines.append(line)
    return "\n".join(rendered_lines)


def _looks_like_inline_result_line(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(re.search(r"[:|]\s*[-+]?\d[\d,]*(?:\.\d+)?(?:\s*[A-Za-z가-힣%]*)?\s*$", text))


def chat_table_visible_rows(max_height: int = TABLE_MAX_HEIGHT) -> int:
    usable_height = max_height - TABLE_HEADER_HEIGHT - TABLE_VERTICAL_PADDING
    return max(1, usable_height // TABLE_ROW_HEIGHT)


def chat_table_height(row_count: int, max_height: int = TABLE_MAX_HEIGHT) -> int:
    clean_count = max(0, int(row_count or 0))
    if clean_count <= 0:
        return TABLE_MIN_HEIGHT
    visible_rows = chat_table_visible_rows(max_height)
    if clean_count > visible_rows:
        return max_height
    content_height = TABLE_HEADER_HEIGHT + TABLE_VERTICAL_PADDING + clean_count * TABLE_ROW_HEIGHT
    return max(TABLE_MIN_HEIGHT, min(max_height, content_height))


def chat_dataframe_height(row_count: int, max_height: int = TABLE_MAX_HEIGHT) -> str | int:
    clean_count = max(0, int(row_count or 0))
    if 0 < clean_count <= TABLE_AUTO_HEIGHT_ROWS:
        return "auto"
    return chat_table_height(clean_count, max_height)


def display_table_frame(frame: pd.DataFrame, number_mode: str = "comma") -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    for column in result.columns:
        if not _looks_quantity_column(column):
            continue
        result[column] = result[column].map(lambda value: _format_number(value, number_mode))
    return result


def _looks_quantity_column(column: Any) -> bool:
    text = str(column or "").upper()
    return any(hint in text for hint in QUANTITY_COLUMN_HINTS)


def _format_number(value: Any, mode: str) -> Any:
    if value is None or isinstance(value, bool):
        return value
    try:
        number = float(value)
    except Exception:
        return value
    if number != number:
        return value
    if mode == "k" and abs(number) >= 1000:
        return f"{number / 1000:.1f}K"
    if float(number).is_integer():
        return f"{int(number):,}"
    return f"{number:,.1f}"
