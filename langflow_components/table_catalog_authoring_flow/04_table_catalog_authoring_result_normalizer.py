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
    "DEVICE_DESC",
    "TSV_DIE_TYP",
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
    payload["source_config"] = source_config
    if raw_item_count == 1:
        _backfill_structured_fields(payload, source_text)
    for field in SOURCE_REQUIRED_FIELDS.get(source_type, []):
        if not _clean(source_config.get(field)):
            errors.append(f"{dataset_key} source_type={source_type}에는 source_config.{field}가 필요합니다.")
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
    if query_template and not _clean(source_config.get("query_template")):
        source_config["query_template"] = query_template
    doc_id = _goodocs_doc_id_from_text(source_text)
    if doc_id and not _clean(source_config.get("doc_id")):
        source_config["doc_id"] = doc_id
    if _clean(source_config.get("document_id")) and not _clean(source_config.get("doc_id")):
        source_config["doc_id"] = _clean(source_config.get("document_id"))
    payload["source_config"] = source_config

    query_columns = _columns_from_query(_clean(source_config.get("query_template")))
    existing_columns = _as_text_list(payload.get("columns"))
    if query_columns and len(existing_columns) < len(query_columns):
        payload["columns"] = query_columns
    text_columns = _columns_from_text_list(source_text)
    if text_columns and len(_as_text_list(payload.get("columns"))) < len(text_columns):
        payload["columns"] = text_columns

    mappings_from_text = _filter_mappings_from_text(source_text)
    if mappings_from_text:
        payload["filter_mappings"] = _merge_mapping(payload.get("filter_mappings"), mappings_from_text)
        if "DATE" in mappings_from_text and not _declares_no_required_params(source_text):
            payload["required_param_mappings"] = _merge_mapping(payload.get("required_param_mappings"), {"DATE": mappings_from_text["DATE"]})
            required_params = _as_text_list(payload.get("required_params"))
            if "DATE" not in required_params:
                payload["required_params"] = [*required_params, "DATE"]
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
    for line in lines:
        if not collecting:
            match = re.match(r"\s*query_template\s*:\s*(.*)$", line, flags=re.IGNORECASE)
            if not match:
                continue
            collecting = True
            first = _clean(match.group(1))
            if first:
                collected.append(first)
            continue
        stripped = _clean(line)
        if not stripped and collected:
            break
        if re.match(r"\s*(filter_mappings|default_detail_columns|columns|standard_column_aliases)\b", line, flags=re.IGNORECASE):
            break
        if stripped:
            collected.append(stripped)
    return " ".join(collected)


def _columns_from_query(query: str) -> list[str]:
    sql = _strip_outer_parentheses(str(query or "").strip())
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
    for char in select_text:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _column_name_from_select_expr(expr: str) -> str:
    text = _clean(expr).strip('"`[]')
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
