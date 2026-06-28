# 파일 설명: 04 Table Catalog Authoring Result Normalizer Langflow custom component 파일입니다.
# 흐름 역할: table catalog authoring LLM JSON을 MongoDB 저장 가능한 dataset item으로 정규화합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


STANDARD_ALIAS_KEYS = {
    "DATE",
    "OPER_NAME",
    "OPER_NUM",
    "MODE",
    "TECH",
    "DEN",
    "PKG_TYPE1",
    "PKG_TYPE2",
    "LEAD",
    "MCP_NO",
    "DEVICE",
    "DEVICE_DESC",
    "TSV_DIE_TYP",
    "DIE_ATTACH_QTY",
    "NETDIE_300_CNT",
    "OPER_SEQ",
    "EQP_ID",
    "EQP_MODEL",
    "RECIPE_ID",
}

SOURCE_REQUIRED_FIELDS = {
    "oracle": ["db_key", "query_template"],
    "h_api": ["api_url"],
    "datalake": ["query_template"],
    "goodocs": ["doc_id"],
}

TRUNCATED_QUERY_MARKERS = ("...", "…", "<생략>", "생략", "omitted", "truncated")
QUERY_BLOCK_STOP_FIELDS = {
    "dataset_key",
    "display_name",
    "dataset_family",
    "date_scope",
    "source_type",
    "db_key",
    "required_params",
    "required_param_mappings",
    "filter_mappings",
    "standard_column_aliases",
    "default_detail_columns",
    "columns",
    "date_format",
    "primary_quantity_column",
}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: table catalog authoring LLM JSON을 MongoDB 저장 가능한 dataset item으로 정규화합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def normalize_table_catalog_authoring_result(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    parsed = _extract_json_object(_text(llm_response_value))
    errors = []
    items = []
    if not parsed:
        errors.append("저장 형식 변환 LLM 응답에서 JSON을 찾지 못했습니다.")
    raw_items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    source_text = _source_text(payload)
    raw_item_count = len(raw_items)
    for index, raw_item in enumerate(raw_items):
        item, item_errors = _normalize_item(raw_item, index, source_text, raw_item_count)
        if item:
            items.append(item)
        errors.extend(item_errors)
    next_payload = dict(payload)
    next_payload["items"] = items
    next_payload["query_template_checks"] = _query_template_checks(items)
    next_payload["authoring"] = {
        "missing_information": _as_list(parsed.get("missing_information")),
        "warnings": _as_list(parsed.get("warnings")),
        "raw_item_count": len(raw_items),
    }
    next_payload["errors"] = list(next_payload.get("errors", [])) + errors
    next_payload["warnings"] = list(next_payload.get("warnings", [])) + [str(item) for item in _as_list(parsed.get("warnings"))]
    return next_payload


def _normalize_item(raw_item: Any, index: int, source_text: str = "", raw_item_count: int = 0) -> tuple[dict[str, Any] | None, list[str]]:
    errors = []
    if not isinstance(raw_item, dict):
        return None, [f"items[{index}]가 object가 아닙니다."]
    dataset_key = _clean(raw_item.get("dataset_key") or raw_item.get("key"))
    payload = deepcopy(raw_item.get("payload")) if isinstance(raw_item.get("payload"), dict) else {}
    dataset_key = _backfill_dataset_key(dataset_key, source_text, raw_item_count)
    if not dataset_key:
        errors.append(f"items[{index}] dataset_key가 없습니다.")
    source_type = _clean(payload.get("source_type") or (payload.get("source_config") or {}).get("source_type") or _source_type_from_text(source_text) or "dummy").lower()
    payload["source_type"] = source_type
    source_config = deepcopy(payload.get("source_config")) if isinstance(payload.get("source_config"), dict) else {}
    source_config.setdefault("source_type", source_type)
    _normalize_source_config_query(source_config)
    payload["source_config"] = source_config
    if raw_item_count == 1:
        _backfill_structured_fields(payload, source_text)
    _normalize_source_config_query(payload["source_config"])
    for field in SOURCE_REQUIRED_FIELDS.get(source_type, []):
        if not _clean(payload["source_config"].get(field)):
            errors.append(f"{dataset_key} source_type={source_type}에는 source_config.{field}가 필요합니다.")
    query_template = _clean(payload["source_config"].get("query_template"))
    if _query_template_looks_truncated(query_template):
        errors.append(f"{dataset_key} source_config.query_template이 축약되어 저장할 수 없습니다. 실제 실행 SQL 전체를 입력해 주세요.")
    if not _clean(payload.get("dataset_family")):
        errors.append(f"{dataset_key} dataset_family가 필요합니다.")
    if not _as_text_list(payload.get("columns")):
        errors.append(f"{dataset_key} columns 목록이 필요합니다.")
    if not isinstance(payload.get("required_params"), list):
        payload["required_params"] = _as_text_list(payload.get("required_params"))
    if payload.get("default_detail_columns") is not None:
        payload["default_detail_columns"] = _as_text_list(payload.get("default_detail_columns"))
    if payload.get("columns") is not None:
        payload["columns"] = _as_text_list(payload.get("columns"))
    payload["filter_mappings"] = _normalize_mapping(payload.get("filter_mappings"))
    payload["required_param_mappings"] = _normalize_mapping(payload.get("required_param_mappings"))
    _normalize_required_param_fields(payload, source_text)
    payload["standard_column_aliases"] = _normalize_mapping(payload.get("standard_column_aliases"))
    _repair_filter_mappings_from_standard_aliases(payload)
    return {
        "dataset_key": dataset_key,
        "key": dataset_key,
        "status": _clean(raw_item.get("status") or "active"),
        "payload": payload,
        "confidence": _clean(raw_item.get("confidence") or "medium"),
    }, errors


def _source_text(payload: dict[str, Any]) -> str:
    parts = [_clean(payload.get("raw_text")), _clean(payload.get("refined_text"))]
    return "\n\n".join(part for part in parts if part)


def _backfill_dataset_key(dataset_key: str, source_text: str, raw_item_count: int) -> str:
    if raw_item_count != 1:
        return dataset_key
    candidates = _dataset_key_candidates_from_text(source_text)
    if len(candidates) != 1:
        return dataset_key
    candidate = candidates[0]
    if not dataset_key or dataset_key.endswith("_detailed") or dataset_key not in source_text:
        return candidate
    return dataset_key


def _dataset_key_candidates_from_text(text: str) -> list[str]:
    patterns = [
        r"\b([A-Za-z][A-Za-z0-9_]*)\s*(?:로|으로)\s*등록",
        r"데이터는\s*([A-Za-z][A-Za-z0-9_]*)\s*(?:로|으로)",
        r"\bdataset(?:_key)?\s*(?:는|:|=)\s*[\"']?([A-Za-z][A-Za-z0-9_]*)",
    ]
    candidates: list[str] = []
    for pattern in patterns:
        candidates.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return _unique_text(candidates)


def _backfill_structured_fields(payload: dict[str, Any], source_text: str) -> None:
    if not source_text:
        return
    source_config = payload.get("source_config") if isinstance(payload.get("source_config"), dict) else {}
    source_type = _source_type_from_text(source_text)
    if source_type and not _clean(payload.get("source_type")):
        payload["source_type"] = source_type
        source_config["source_type"] = source_type
    elif source_type:
        source_config.setdefault("source_type", source_type)
    db_key = _db_key_from_text(source_text)
    if db_key and not _clean(source_config.get("db_key")):
        source_config["db_key"] = db_key
    query_template = _query_template_from_text(source_text)
    if query_template and _should_replace_query_template(query_template, source_config.get("query_template")):
        source_config["query_template"] = query_template
    doc_id = _goodocs_doc_id_from_text(source_text)
    if doc_id and not _clean(source_config.get("doc_id")):
        source_config["doc_id"] = doc_id
    if _clean(source_config.get("document_id")) and not _clean(source_config.get("doc_id")):
        source_config["doc_id"] = _clean(source_config.get("document_id"))
    payload["source_config"] = source_config

    query_template_text = _clean(source_config.get("query_template"))
    query_columns = _columns_from_query(query_template_text)
    existing_columns = _as_text_list(payload.get("columns"))
    if query_columns and (
        len(existing_columns) < len(query_columns)
        or _has_sql_comment(query_template_text)
        or _columns_have_comment_artifacts(existing_columns)
    ):
        payload["columns"] = query_columns
    text_columns = _columns_from_text_list(source_text)
    if text_columns and len(_as_text_list(payload.get("columns"))) < len(text_columns):
        payload["columns"] = text_columns

    mappings_from_text = _filter_mappings_from_text(source_text)
    if mappings_from_text:
        payload["filter_mappings"] = _merge_mapping(payload.get("filter_mappings"), mappings_from_text)
    aliases_from_text = _standard_column_aliases_from_text(source_text)
    aliases_from_mappings = _standard_column_aliases_from_filter_mappings(mappings_from_text)
    if aliases_from_mappings:
        aliases_from_text = _merge_mapping(aliases_from_text, aliases_from_mappings)
    if aliases_from_text:
        payload["standard_column_aliases"] = _merge_mapping(payload.get("standard_column_aliases"), aliases_from_text)

    date_format = _date_format_from_text(source_text)
    if date_format and not _clean(payload.get("date_format")):
        payload["date_format"] = date_format
    quantity_column = _quantity_column_from_text(source_text)
    if quantity_column and not _clean(payload.get("primary_quantity_column")):
        payload["primary_quantity_column"] = quantity_column
    if _declares_no_required_params(source_text):
        payload["required_params"] = []
        payload["required_param_mappings"] = {}


def _normalize_required_param_fields(payload: dict[str, Any], source_text: str) -> None:
    source_config = payload.get("source_config") if isinstance(payload.get("source_config"), dict) else {}
    placeholders = _unique_text(
        [
            *_query_placeholders(_clean(source_config.get("query_template"))),
            *_query_placeholders(_clean(source_config.get("api_url"))),
        ]
    )
    if _declares_no_required_params(source_text) and not placeholders:
        payload["required_params"] = []
        payload["required_param_mappings"] = {}
        return

    required_params = _normalize_required_param_names(payload.get("required_params"))
    if placeholders:
        required_params = _unique_text([*required_params, *placeholders])
    elif not _mentions_required_params(source_text):
        required_params = []

    filter_mappings = {
        _normalize_required_param_name(key): values
        for key, values in _normalize_mapping(payload.get("filter_mappings")).items()
    }
    required_mappings = {
        _normalize_required_param_name(key): values
        for key, values in _normalize_mapping(payload.get("required_param_mappings")).items()
    }
    for param in required_params:
        if param not in required_mappings and param in filter_mappings:
            required_mappings[param] = list(filter_mappings[param])
    required_set = set(required_params)
    payload["required_params"] = required_params
    payload["required_param_mappings"] = {
        key: values
        for key, values in required_mappings.items()
        if key in required_set
    }


def _query_placeholders(text: str) -> list[str]:
    if not text:
        return []
    return _unique_text(
        _normalize_required_param_name(match)
        for match in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", text)
    )


def _normalize_required_param_names(value: Any) -> list[str]:
    return _unique_text(_normalize_required_param_name(item) for item in _as_text_list(value))


def _normalize_required_param_name(value: Any) -> str:
    return _clean(value).upper()


def _source_type_from_text(text: str) -> str:
    lowered = text.lower()
    for source_type in ("oracle", "datalake", "h_api", "goodocs", "dummy"):
        if re.search(rf"\b{re.escape(source_type)}\b", lowered):
            return source_type
    return ""


def _db_key_from_text(text: str) -> str:
    match = re.search(r"\bdb_key\s*(?:는|:|=)\s*([A-Za-z0-9_.-]+)", text, flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else ""


def _goodocs_doc_id_from_text(text: str) -> str:
    patterns = [
        r"\bdoc_id\s*(?:는|:|=)\s*[\"']?([A-Za-z0-9_.-]+)",
        r"\bdocument_id\s*(?:는|:|=)\s*[\"']?([A-Za-z0-9_.-]+)",
        r"Goodocs\s*문서\s*ID\s*(?:는|:|=)\s*[\"']?([A-Za-z0-9_.-]+)",
        r"문서\s*ID\s*(?:는|:|=)\s*[\"']?([A-Za-z0-9_.-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1)).strip("\"'.")
    return ""


def _query_template_from_text(text: str) -> str:
    lines = str(text or "").splitlines()
    collected: list[str] = []
    collecting = False
    in_fence = False
    for line in lines:
        if not collecting:
            match = re.match(r"\s*query_template\s*:\s*(.*)$", line, flags=re.IGNORECASE)
            if not match:
                continue
            collecting = True
            first = match.group(1).rstrip()
            if first.strip().startswith("```"):
                in_fence = True
                continue
            if first.strip():
                collected.append(first)
            continue
        stripped = line.strip()
        if in_fence:
            if stripped.startswith("```"):
                break
            collected.append(line.rstrip())
            continue
        if stripped.startswith("```"):
            in_fence = True
            continue
        if _is_query_block_stop_line(line):
            break
        collected.append(line.rstrip())
    return _strip_query_template_semicolon("\n".join(_trim_blank_lines(collected)))


def _is_query_block_stop_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    for field in QUERY_BLOCK_STOP_FIELDS:
        if re.match(rf"^{re.escape(field)}\s*(?::|=|는|은)\s*", text, flags=re.IGNORECASE):
            return True
    return False


def _trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _normalize_source_config_query(source_config: dict[str, Any]) -> None:
    lines = source_config.get("query_template_lines")
    if isinstance(lines, list) and not _clean(source_config.get("query_template")):
        joined = "\n".join(str(line) for line in lines)
        if joined.strip():
            source_config["query_template"] = joined
    source_config.pop("query_template_lines", None)
    for alias in ("sql_template", "oracle_sql", "sql", "query"):
        if _clean(source_config.get(alias)) and not _clean(source_config.get("query_template")):
            source_config["query_template"] = source_config.get(alias)
    if _clean(source_config.get("query_template")):
        source_config["query_template"] = _strip_query_template_semicolon(source_config.get("query_template"))


def _should_replace_query_template(candidate: str, current: Any) -> bool:
    current_text = _strip_query_template_semicolon(current)
    candidate_text = _strip_query_template_semicolon(candidate)
    if not candidate_text:
        return False
    if not current_text:
        return True
    if _query_template_looks_truncated(candidate_text) and not _query_template_looks_truncated(current_text):
        return False
    if not _query_template_looks_truncated(candidate_text):
        return True
    return len(candidate_text) >= len(current_text)


def _strip_query_template_semicolon(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    while text.endswith(";"):
        text = text[:-1].rstrip()
    return text


def _query_template_looks_truncated(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(marker.lower() in text for marker in TRUNCATED_QUERY_MARKERS)


def _query_template_tail(value: Any, max_lines: int = 8) -> str:
    lines = [line.rstrip() for line in str(value or "").splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


def _query_template_checks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for item in items:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        source_config = payload.get("source_config") if isinstance(payload.get("source_config"), dict) else {}
        query_template = str(source_config.get("query_template") or "")
        if not query_template:
            continue
        checks.append(
            {
                "dataset_key": item.get("dataset_key", ""),
                "char_count": len(query_template),
                "line_count": len(query_template.splitlines()),
                "contains_truncation_marker": _query_template_looks_truncated(query_template),
                "tail_preview": _query_template_tail(query_template),
            }
        )
    return checks


def _columns_from_query(query: str) -> list[str]:
    sql = _strip_outer_parentheses(_strip_sql_comments_for_parsing(str(query or "").strip()))
    select_bounds = _top_level_select_bounds(sql)
    if not select_bounds:
        return []
    select_start, from_start = select_bounds
    columns = _unique_text(_column_name_from_select_expr(part) for part in _split_select_list(sql[select_start:from_start]))
    columns = [column for column in columns if not _is_wildcard_column(column)]
    if columns:
        return columns
    subquery = _first_from_subquery(sql, from_start)
    return _columns_from_query(subquery) if subquery else []


def _top_level_select_bounds(query: str) -> tuple[int, int] | None:
    sql = str(query or "").strip()
    select_index = _find_top_level_keyword(sql, "select", 0)
    if select_index < 0:
        return None
    from_index = _find_top_level_keyword(sql, "from", select_index + len("select"))
    if from_index < 0:
        return None
    return select_index + len("select"), from_index


def _find_top_level_keyword(sql: str, keyword: str, start: int = 0) -> int:
    depth = 0
    quote = ""
    line_comment = False
    block_comment = False
    index = max(0, start)
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if line_comment:
            if char in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if quote == "]" and char == "]":
                quote = ""
            elif char == quote:
                if quote == "'" and next_char == "'":
                    index += 2
                    continue
                quote = ""
            index += 1
            continue
        if char == "-" and next_char == "-":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if char == "[":
            quote = "]"
            index += 1
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth == 0 and _keyword_at(sql, index, keyword):
            return index
        index += 1
    return -1


def _keyword_at(sql: str, index: int, keyword: str) -> bool:
    end = index + len(keyword)
    if sql[index:end].lower() != keyword.lower():
        return False
    before = sql[index - 1] if index > 0 else ""
    after = sql[end] if end < len(sql) else ""
    return not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_")


def _strip_outer_parentheses(sql: str) -> str:
    text = str(sql or "").strip()
    while text.startswith("(") and text.endswith(")"):
        close_index = _matching_parenthesis_index(text, 0)
        if close_index != len(text) - 1:
            break
        text = text[1:-1].strip()
    return text


def _first_from_subquery(query: str, from_index: int) -> str:
    sql = str(query or "")
    index = from_index + len("from")
    while index < len(sql) and sql[index].isspace():
        index += 1
    if index >= len(sql) or sql[index] != "(":
        return ""
    close_index = _matching_parenthesis_index(sql, index)
    if close_index <= index:
        return ""
    return sql[index + 1 : close_index]


def _matching_parenthesis_index(text: str, open_index: int) -> int:
    depth = 0
    quote = ""
    for index in range(open_index, len(text)):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if quote:
            if quote == "]" and char == "]":
                quote = ""
            elif char == quote:
                if quote == "'" and next_char == "'":
                    continue
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "[":
            quote = "]"
            continue
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_select_list(select_text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote = ""
    index = 0
    while index < len(select_text):
        char = select_text[index]
        next_char = select_text[index + 1] if index + 1 < len(select_text) else ""
        if quote:
            current.append(char)
            if quote == "]" and char == "]":
                quote = ""
            elif char == quote:
                if quote == "'" and next_char == "'":
                    current.append(next_char)
                    index += 2
                    continue
                quote = ""
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "[":
            quote = "]"
            current.append(char)
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    if current:
        parts.append("".join(current))
    return parts


def _column_name_from_select_expr(expr: str) -> str:
    text = _clean(expr).strip('"`[]')
    if not text or text.startswith("--") or text.startswith("/*"):
        return ""
    text = re.sub(r"^\s*distinct\s+", "", text, flags=re.IGNORECASE)
    alias = re.search(r"\s+as\s+([A-Za-z0-9_\"`\[\] ]+)$", text, flags=re.IGNORECASE)
    if alias:
        return _clean(alias.group(1)).strip('"`[]')
    tokens = text.split()
    if len(tokens) > 1:
        return tokens[-1].strip('"`[]')
    return text.split(".")[-1].strip('"`[]')


def _is_wildcard_column(column: str) -> bool:
    text = _clean(column)
    return text in {"*", ".*"} or text.endswith(".*")


def _strip_sql_comments_for_parsing(sql: str) -> str:
    result: list[str] = []
    quote = ""
    line_comment = False
    block_comment = False
    index = 0
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if line_comment:
            if char in "\r\n":
                line_comment = False
                result.append(char)
            index += 1
            continue
        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
                continue
            if char in "\r\n":
                result.append(char)
            else:
                result.append(" ")
            index += 1
            continue
        if quote:
            result.append(char)
            if quote == "]" and char == "]":
                quote = ""
            elif char == quote:
                if quote == "'" and next_char == "'":
                    result.append(next_char)
                    index += 2
                    continue
                quote = ""
            index += 1
            continue
        if char == "-" and next_char == "-":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "[":
            quote = "]"
        result.append(char)
        index += 1
    return "".join(result)


def _has_sql_comment(sql: str) -> bool:
    return _strip_sql_comments_for_parsing(sql) != str(sql or "")


def _columns_have_comment_artifacts(columns: list[str]) -> bool:
    for column in columns:
        text = _clean(column)
        if not text or text in {"-", "--"} or "--" in text or "/*" in text or "*/" in text:
            return True
    return False


def _filter_mappings_from_text(text: str) -> dict[str, list[str]]:
    return _named_mappings_from_text(text, "filter_mappings")


def _standard_column_aliases_from_text(text: str) -> dict[str, list[str]]:
    return _merge_mapping(_named_mappings_from_text(text, "standard_column_aliases"), _standard_quantity_aliases_from_text(text))


def _standard_column_aliases_from_filter_mappings(mappings: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, values in mappings.items():
        standard_key = _clean(key).upper()
        if standard_key not in STANDARD_ALIAS_KEYS:
            continue
        physical_values = [value for value in values if _clean(value) != _clean(key)]
        if physical_values:
            result[standard_key] = _unique_text(physical_values)
    return result


def _standard_quantity_aliases_from_text(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if re.search(r"INPUT계획[^\n.。]*INPUT_PLAN|INPUT_PLAN[^\n.。]*INPUT계획", text, flags=re.IGNORECASE):
        result["INPUT_PLAN"] = ["INPUT계획"]
    if re.search(r"OUT계획[^\n.。]*(?:OUT_PLAN|TARGET)|(?:OUT_PLAN|TARGET)[^\n.。]*OUT계획", text, flags=re.IGNORECASE):
        aliases = ["OUT계획"]
        if re.search(r"OUT계획[^\n.。]*TARGET|TARGET[^\n.。]*OUT계획", text, flags=re.IGNORECASE):
            aliases.append("TARGET")
        result["OUT_PLAN"] = aliases
    return result


def _named_mappings_from_text(text: str, field_name: str) -> dict[str, list[str]]:
    match = re.search(rf"{re.escape(field_name)}\s*(?:는|:)?\s*(.*)", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return {}
    snippet = re.split(r"\n\s*\n", match.group(1), maxsplit=1)[0]
    snippet = re.split(
        r"\n\s*(?:filter_mappings|required_param_mappings|standard_column_aliases|default_detail_columns|columns)\b",
        snippet,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    result: dict[str, list[str]] = {}
    for item in re.finditer(r"([A-Za-z][A-Za-z0-9_ ]*)\s*->\s*([^,\n]+)", snippet):
        key = _clean(item.group(1)).replace(" ", "_")
        values = _mapping_values(item.group(2))
        if key and values:
            result[key] = values
    return result


def _mapping_values(text: str) -> list[str]:
    cleaned = re.sub(r"(?:로|으로)\s*연결.*$", "", _clean(text))
    parts = re.split(r"\s*(?:또는|혹은|\bor\b)\s*", cleaned, flags=re.IGNORECASE)
    return _unique_text(part.strip(" .。;") for part in parts)


def _date_format_from_text(text: str) -> str:
    upper = text.upper()
    if "YYYY-MM-DD" in upper:
        return "YYYY-MM-DD"
    if "YYYYMMDD" in upper:
        return "YYYYMMDD"
    return ""


def _quantity_column_from_text(text: str) -> Any:
    if "계획 수량" in text and "INPUT계획" in text and "OUT계획" in text:
        return ["INPUT_PLAN", "OUT_PLAN"]
    if "기본 목표 수량" in text and "OUT계획" in text:
        return "OUT_PLAN"
    match = re.search(r"(?:수량|quantity).*?([A-Z][A-Z0-9_]+)\s*컬럼", text, flags=re.IGNORECASE)
    if match:
        return _clean(match.group(1)).upper()
    return ""


def _columns_from_text_list(text: str) -> list[str]:
    patterns = [
        r"(?:문서|데이터|테이블)[^\n]*?에는\s*([^\n]+?)\s*(?:항목|컬럼)",
        r"\bcolumns\s*(?:는|:)\s*([^\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        values = [part.strip(" .。;") for part in match.group(1).split(",")]
        columns = _unique_text(values)
        if columns:
            return columns
    return []


def _declares_no_required_params(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    patterns = [
        "필수조회파라미터는없",
        "필수조회파라미터가없",
        "별도필수조회파라미터는없",
        "requiredparams없",
        "required_params없",
    ]
    return any(pattern.lower() in compact.lower() for pattern in patterns)


def _mentions_required_params(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(r"필수\s*(?:조회\s*)?(?:파라미터|parameter|param|변수|기준일)", text, flags=re.IGNORECASE)
        or re.search(r"required[_\s-]*(?:params?|parameters?)", text, flags=re.IGNORECASE)
    )


def _merge_mapping(base: Any, incoming: dict[str, list[str]]) -> dict[str, list[str]]:
    merged = _normalize_mapping(base)
    for key, values in incoming.items():
        merged[key] = _unique_text([*merged.get(key, []), *values])
    return merged


def _repair_filter_mappings_from_standard_aliases(payload: dict[str, Any]) -> None:
    columns = {_clean(column).lower() for column in _as_text_list(payload.get("columns"))}
    if not columns:
        return
    filter_mappings = payload.get("filter_mappings") if isinstance(payload.get("filter_mappings"), dict) else {}
    standard_aliases = payload.get("standard_column_aliases") if isinstance(payload.get("standard_column_aliases"), dict) else {}
    for filter_key, mapped_columns in list(filter_mappings.items()):
        values = _as_text_list(mapped_columns)
        if any(_clean(column).lower() in columns for column in values):
            continue
        alias_values = _mapping_values_for_key(standard_aliases, filter_key)
        selected_aliases = [column for column in alias_values if _clean(column).lower() in columns]
        if selected_aliases:
            filter_mappings[filter_key] = _unique_text(selected_aliases)
    payload["filter_mappings"] = filter_mappings


def _mapping_values_for_key(mapping: dict[str, Any], target_key: str) -> list[str]:
    target = _clean(target_key).upper()
    values: list[str] = []
    for key, raw_values in mapping.items():
        if _clean(key).upper() == target:
            values.extend(_as_text_list(raw_values))
    return _unique_text(values)


def _unique_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text not in result:
            result.append(text)
    return result


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    result = []
    for item in value:
        parts = re.split(r"[\n,;]+", item) if isinstance(item, str) else [item]
        for part in parts:
            text = _clean(part)
            if text and text not in result:
                result.append(text)
    return result


def _normalize_mapping(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        _clean(key): _as_text_list(item)
        for key, item in value.items()
        if _clean(key)
    }


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        for key in ("llm_text", "text", "content", "response"):
            if data.get(key):
                return str(data[key])
    for attr in ("text", "content"):
        if getattr(value, attr, None):
            return str(getattr(value, attr))
    return str(value)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


# 컴포넌트 설명: 04 Table Catalog Authoring Result Normalizer
# Langflow 표시 설명: table catalog authoring LLM JSON을 MongoDB 저장 가능한 dataset item으로 정규화합니다.
class TableCatalogAuthoringResultNormalizer(Component):

    display_name = "04 Table Catalog Authoring Result Normalizer"
    description = "table catalog authoring LLM JSON을 MongoDB 저장 가능한 dataset item으로 정규화합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: table catalog authoring LLM JSON을 MongoDB 저장 가능한 dataset item으로 정규화합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = normalize_table_catalog_authoring_result(getattr(self, "payload", None), getattr(self, "llm_response", ""))

        self.status = {"items": len(result.get("items", [])), "errors": len(result.get("errors", []))}
        return Data(data=result)
