# 파일 설명: 04 Domain Authoring Result Normalizer Langflow custom component 파일입니다.
# 흐름 역할: domain authoring LLM JSON을 MongoDB 저장 가능한 domain item 구조로 정규화합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


ALLOWED_SECTIONS = {
    "process_groups",
    "product_terms",
    "quantity_terms",
    "metric_terms",
    "status_terms",
    "analysis_recipes",
    "pandas_function_cases",
    "product_key_columns",
}
SECTION_ALIASES = {
    "products": "product_terms",
    "product": "product_terms",
    "metrics": "metric_terms",
    "metric": "metric_terms",
    "recipe": "analysis_recipes",
    "recipes": "analysis_recipes",
    "function_case": "pandas_function_cases",
    "function_cases": "pandas_function_cases",
    "pandas_function_case": "pandas_function_cases",
    "pandas_function_cases": "pandas_function_cases",
}
DOMAIN_LIST_FIELDS = {
    "aliases",
    "processes",
    "required_quantity_terms",
    "required_dataset_families",
    "required_datasets",
    "metric_terms",
    "source_columns",
    "required_columns",
    "group_by_columns",
    "column_candidates",
    "question_cues",
    "forbidden_question_cues",
    "override_analysis_kinds",
    "blocked_filter_fields",
    "output_columns",
    "output_order",
    "result_columns",
    "detail_columns",
    "required_source_columns",
    "token_columns",
    "candidate_columns",
    "source_aliases",
    "dataset_families",
    "activation_cues",
    "pandas_code_instructions",
    "clear_filters",
    "trigger_terms",
    "excluded_terms",
    "applies_to",
}
CONDITION_FILTER_KEYS = {
    "exists",
    "not_in",
    "is_empty",
    "starts_with",
    "ends_with",
    "last_char_in",
    "contains",
    "equals",
    "eq",
    "in",
    "gt",
    "gte",
    "lt",
    "lte",
    "ne",
    "not_eq",
    "between",
}
FORMULA_FUNCTION_WORDS = {
    "SUM",
    "MAX",
    "MIN",
    "MEAN",
    "AVG",
    "COUNT",
    "NUNIQUE",
    "IF",
    "WHEN",
    "THEN",
    "ELSE",
    "NULL",
    "NONE",
    "TRUE",
    "FALSE",
}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: domain authoring LLM JSON을 MongoDB 저장 가능한 domain item 구조로 정규화합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def normalize_domain_authoring_result(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    parsed = _extract_json_object(_text(llm_response_value))
    errors = []
    warnings = []
    items = []
    if not parsed:
        errors.append("저장 형식 변환 LLM 응답에서 JSON을 찾지 못했습니다.")
    raw_items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    source_text = _source_text(payload)
    raw_source_text = _clean(payload.get("raw_text")) or source_text
    metadata_context = payload.get("metadata_context") if isinstance(payload.get("metadata_context"), dict) else {}
    for index, raw_item in enumerate(raw_items):
        item, item_errors, item_warnings = _normalize_item(raw_item, index, source_text, metadata_context, raw_source_text)
        if item:
            items.append(item)
        errors.extend(item_errors)
        warnings.extend(item_warnings)

    next_payload = dict(payload)
    next_payload["items"] = items
    next_payload["authoring"] = {
        "missing_information": _as_list(parsed.get("missing_information")),
        "warnings": [*_as_list(parsed.get("warnings")), *warnings],
        "raw_item_count": len(raw_items),
    }
    next_payload["errors"] = list(next_payload.get("errors", [])) + errors
    next_payload["warnings"] = list(next_payload.get("warnings", [])) + [str(item) for item in _as_list(parsed.get("warnings"))] + warnings
    return next_payload


def _normalize_item(
    raw_item: Any,
    index: int,
    source_text: str = "",
    metadata_context: dict[str, Any] | None = None,
    raw_source_text: str = "",
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    errors = []
    warnings = []
    if not isinstance(raw_item, dict):
        return None, [f"items[{index}]가 object가 아닙니다."], []
    key = _clean(raw_item.get("key") or raw_item.get("name"))
    payload = deepcopy(raw_item.get("payload")) if isinstance(raw_item.get("payload"), dict) else {}
    section = _normalize_section(raw_item, payload)
    if section == "process_groups" and not _as_text_list(payload.get("processes")) and _looks_like_analysis_recipe_payload(payload):
        section = "analysis_recipes"
    if section not in ALLOWED_SECTIONS:
        errors.append(f"items[{index}] section이 허용값이 아닙니다: {section}")
    if not key and section != "product_key_columns":
        errors.append(f"items[{index}] key가 없습니다.")
    if section == "product_key_columns":
        if not _source_mentions_product_key_columns(source_text):
            return None, [], [f"items[{index}] product_key_columns item was ignored because it is not grounded in the worker input."]
        columns = _as_text_list(raw_item.get("columns") or payload.get("columns") or payload.get("product_key_columns"))
        if not columns:
            errors.append("product_key_columns에는 columns 목록이 필요합니다.")
        key = key or "default"
        payload = {"columns": columns, "product_key_columns": columns}
    else:
        payload.setdefault("aliases", _as_text_list(payload.get("aliases")))
        _normalize_payload_lists(payload)
        _normalize_condition_fields(payload)
        if _is_derived_metric_artifact(section, key, payload, source_text):
            return None, [], [f"items[{index}] {section}/{key} was ignored because it is a derived metric artifact, not a standalone domain term."]
        if section in {"product_terms", "quantity_terms", "status_terms", "metric_terms"}:
            _normalize_condition_overrides(payload, errors, key)
        if section == "process_groups" and not _as_text_list(payload.get("processes")):
            inferred_processes = _process_values_from_payload(payload)
            if inferred_processes:
                payload["processes"] = inferred_processes
        if section == "process_groups" and not _is_process_group_grounded_in_source(key, payload, raw_source_text or source_text):
            return None, [], [f"items[{index}] process_groups/{key} was ignored because it was not grounded in the worker input."]
        if section == "process_groups" and not _as_text_list(payload.get("processes")):
            if _source_mentions_process_group(source_text):
                errors.append(f"{key} process_groups에는 processes 목록이 필요합니다.")
            else:
                return None, [], [f"items[{index}] process_groups/{key} was ignored because the worker input did not define a process group."]
        if section in {"quantity_terms", "status_terms"} and payload.get("aggregation") == "count_distinct":
            payload["aggregation"] = "nunique"
        if section == "quantity_terms":
            key = _normalize_quantity_payload(key, payload, source_text, metadata_context or {})
        if section in {"quantity_terms", "metric_terms"} and payload.get("quantity_column") is not None:
            quantity_columns = _as_text_list(payload.get("quantity_column"))
            payload["quantity_column"] = quantity_columns[0] if len(quantity_columns) == 1 else quantity_columns
        if section in {"quantity_terms", "status_terms", "metric_terms", "analysis_recipes"}:
            if payload.get("required_quantity_terms") is not None:
                payload["required_quantity_terms"] = _as_text_list(payload.get("required_quantity_terms"))
            if payload.get("output_column") is not None:
                payload["output_column"] = _clean(payload.get("output_column"))
        if section == "analysis_recipes":
            _normalize_analysis_recipe_payload(payload)
        if section == "pandas_function_cases":
            _normalize_pandas_function_case_payload(payload)
        if section == "metric_terms":
            _normalize_metric_role_filters(payload)
            _normalize_metric_payload(payload, metadata_context or {})
    if not payload:
        errors.append(f"items[{index}] payload가 비어 있습니다.")
    item = {
        "section": section,
        "key": key,
        "status": _clean(raw_item.get("status") or "active"),
        "payload": payload,
        "confidence": _clean(raw_item.get("confidence") or "medium"),
    }
    if raw_item.get("columns"):
        item["columns"] = _as_text_list(raw_item.get("columns"))
    return item, errors, warnings


def _normalize_section(raw_item: dict[str, Any], payload: dict[str, Any]) -> str:
    section = _clean(raw_item.get("section") or raw_item.get("gbn") or payload.get("section") or payload.get("gbn")).lower()
    return SECTION_ALIASES.get(section, section)


def _looks_like_analysis_recipe_payload(payload: dict[str, Any]) -> bool:
    recipe_fields = {
        "grain_policy",
        "output_columns",
        "step_plan_template",
        "required_dataset_families",
        "override_analysis_kinds",
        "blocked_filter_fields",
        "default_analysis_kind",
        "intent_type",
        "result_mode",
    }
    return any(payload.get(field) not in (None, "", [], {}) for field in recipe_fields)


def _process_values_from_payload(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []

    def add(value: Any) -> None:
        for item in _as_list(value):
            text = _clean(item)
            if text and text not in values:
                values.append(text)

    for container_key in ("filters", "filter"):
        container = payload.get(container_key)
        if isinstance(container, dict):
            add(container.get("OPER_NAME"))
    condition = payload.get("condition")
    if isinstance(condition, dict):
        add(condition.get("OPER_NAME"))
        nested_filters = condition.get("filters")
        if isinstance(nested_filters, dict):
            add(nested_filters.get("OPER_NAME"))
        for value in condition.values():
            if isinstance(value, dict):
                add(value.get("OPER_NAME"))
    return values


def _is_process_group_grounded_in_source(key: str, payload: dict[str, Any], source_text: str) -> bool:
    normalized_source = _match_text(source_text)
    if not normalized_source:
        return True
    candidates = [key, payload.get("display_name")]
    candidates.extend(_as_text_list(payload.get("aliases")))
    candidates.extend(_as_text_list(payload.get("processes")))
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    candidates.extend(_as_text_list(filters.get("OPER_NAME")))
    condition = payload.get("condition") if isinstance(payload.get("condition"), dict) else {}
    candidates.extend(_as_text_list(condition.get("OPER_NAME")))
    nested_filters = condition.get("filters") if isinstance(condition.get("filters"), dict) else {}
    candidates.extend(_as_text_list(nested_filters.get("OPER_NAME")))
    for candidate in candidates:
        normalized = _match_text(candidate)
        if normalized and normalized in normalized_source:
            return True
    return False


def _match_text(value: Any) -> str:
    return re.sub(r"[\s_\-./,()]+", "", _clean(value).lower())


def _normalize_payload_lists(payload: dict[str, Any]) -> None:
    for key in DOMAIN_LIST_FIELDS:
        if payload.get(key) is not None:
            values = _as_text_list(payload.get(key))
            if values:
                payload[key] = values


def _normalize_analysis_recipe_payload(payload: dict[str, Any]) -> None:
    for key in (
        "required_dataset_families",
        "output_columns",
        "metric_terms",
        "question_cues",
        "forbidden_question_cues",
        "override_analysis_kinds",
        "blocked_filter_fields",
    ):
        if payload.get(key) is not None:
            payload[key] = _as_text_list(payload.get(key))
    for key in ("source_aliases_by_family", "dataset_role_by_family", "defaults", "required_columns_by_family"):
        if not isinstance(payload.get(key, {}), dict):
            payload[key] = {}
    for key in ("replace_datasets", "replace_retrieval_jobs", "override_step_plan", "force_analysis_kind"):
        if payload.get(key) is not None:
            payload[key] = bool(payload.get(key))
    if payload.get("step_plan_template") is not None and not isinstance(payload.get("step_plan_template"), list):
        payload["step_plan_template"] = []
    if payload.get("intent_type") is not None:
        payload["intent_type"] = _clean(payload.get("intent_type"))
    if payload.get("default_analysis_kind") is not None:
        payload["default_analysis_kind"] = _clean(payload.get("default_analysis_kind"))
    if payload.get("grain_policy") is not None:
        payload["grain_policy"] = _clean(payload.get("grain_policy"))
    if payload.get("top_n_policy") is not None:
        payload["top_n_policy"] = _clean(payload.get("top_n_policy"))


def _normalize_pandas_function_case_payload(payload: dict[str, Any]) -> None:
    for key in (
        "required_source_columns",
        "token_columns",
        "candidate_columns",
        "source_aliases",
        "dataset_families",
        "activation_cues",
        "question_cues",
        "forbidden_question_cues",
        "output_columns",
        "output_order",
        "pandas_code_instructions",
    ):
        if payload.get(key) is not None:
            payload[key] = _as_text_list(payload.get(key))
    for key in ("function_name", "use_when", "input_text", "calculation_rule"):
        if payload.get(key) is not None:
            payload[key] = _clean(payload.get(key))
    if payload.get("function_code") is not None:
        payload["function_code"] = _normalize_function_code(payload.get("function_code"))


def _normalize_function_code(value: Any) -> str | list[str]:
    if isinstance(value, list):
        return [str(line).rstrip() for line in value]
    return str(value or "").strip()


def _normalize_condition_fields(payload: dict[str, Any]) -> None:
    if payload.get("condition") not in (None, "", [], {}):
        condition = _normalize_condition_object(payload.get("condition"))
        if condition:
            payload["condition"] = condition
    for filter_key in ("filters", "filter"):
        if payload.get(filter_key) in (None, "", [], {}):
            continue
        filters, conditions, changed = _normalize_filter_descriptors(payload.get(filter_key))
        if not changed:
            continue
        if filters:
            payload["filters"] = filters
        payload.pop("filter", None)
        if conditions:
            current_condition = payload.get("condition") if isinstance(payload.get("condition"), dict) else {}
            current_condition = deepcopy(current_condition)
            for column, condition in conditions.items():
                _merge_condition(current_condition, column, condition)
            payload["condition"] = current_condition


def _normalize_condition_overrides(payload: dict[str, Any], errors: list[str], key: str) -> None:
    for field_name in ("condition_by_dataset", "condition_by_family"):
        value = payload.get(field_name)
        if value is None:
            continue
        if not isinstance(value, dict):
            errors.append(f"{key} {field_name}는 object여야 합니다.")
            payload.pop(field_name, None)
            continue
        clean_value = {}
        for target_key, condition in value.items():
            clean_key = _clean(target_key)
            if not clean_key:
                continue
            if isinstance(condition, dict):
                clean_value[clean_key] = _normalize_condition_object(condition) or condition
            else:
                errors.append(f"{key} {field_name}.{clean_key}는 condition object여야 합니다.")
        payload[field_name] = clean_value


def _normalize_metric_role_filters(payload: dict[str, Any]) -> None:
    for roles_key in ("source_roles", "comparison_roles"):
        roles = payload.get(roles_key)
        if not isinstance(roles, dict):
            continue
        for role in roles.values():
            if not isinstance(role, dict):
                continue
            _normalize_condition_fields(role)


def _normalize_metric_payload(payload: dict[str, Any], metadata_context: dict[str, Any] | None = None) -> None:
    metric_text = _metric_text(payload)
    source_columns = _as_text_list(payload.get("source_columns"))
    output_columns = _as_text_list(payload.get("output_columns"))
    output_column = _clean(payload.get("output_column"))
    if output_column:
        output_columns = _unique_text([*output_columns, output_column])

    inferred_outputs = _output_columns_from_metric_text(metric_text)
    if inferred_outputs:
        output_columns = _unique_text([*output_columns, *inferred_outputs])
        if not output_column and len(inferred_outputs) == 1:
            payload["output_column"] = inferred_outputs[0]
    if output_columns:
        payload["output_columns"] = output_columns

    inferred_sources = [
        column
        for column in _identifier_columns_from_metric_text(metric_text)
        if column not in set(output_columns)
    ]
    if inferred_sources:
        payload["source_columns"] = _unique_text([*source_columns, *inferred_sources])

    source_columns_set = set(_as_text_list(payload.get("source_columns")))
    inferred_family = _infer_dataset_family(metric_text, source_columns_set, metadata_context or {})
    if inferred_family and not _clean(payload.get("dataset_family")):
        payload["dataset_family"] = inferred_family
        _merge_text_list_field(payload, "required_dataset_families", [inferred_family])
    if _has_unique_count_cue(metric_text) and _has_equipment_count_cue(metric_text, source_columns_set):
        payload.setdefault("dataset_family", "equipment")
        _merge_text_list_field(payload, "required_dataset_families", ["equipment"])
        payload["source_columns"] = [_preferred_equipment_column(source_columns_set)]
        source_columns_set = set(_as_text_list(payload.get("source_columns")))
        payload.setdefault("aggregation", "nunique")
        payload.setdefault("output_column", "EQP_COUNT")
        output_columns = _unique_text([*output_columns, "EQP_COUNT"])
        payload["output_columns"] = output_columns
        _merge_text_list_field(payload, "aliases", ["장비 대수", "설비 대수", "equipment count"])
    lowered_metric_text = metric_text.lower()
    production_cues = {"PRODUCTION", "NETDIE_300_CNT"}.intersection(source_columns_set) or any(
        cue in lowered_metric_text
        for cue in ("production", "생산량", "생산 실적", "생산실적", "생산량 조회", "생산량조회")
    )
    if production_cues:
        if not _clean(payload.get("dataset_family")):
            payload["dataset_family"] = "production"
        _merge_text_list_field(payload, "required_dataset_families", ["production"])
        _merge_text_list_field(payload, "required_quantity_terms", ["production"])

    if "NETDIE_300_CNT" in source_columns_set and "PRODUCTION" in source_columns_set:
        payload.setdefault("calculation_rule", "row_level_then_aggregate")
        payload.setdefault("zero_division_rule", "when NETDIE_300_CNT <= 0 or null, do not divide and put PRODUCTION into FAIL_UNIT_QTY")
        if "WAFER_OUT_QTY" in output_columns or "FAIL_UNIT_QTY" in output_columns:
            payload.setdefault(
                "pandas_code_instructions",
                [
                    "For each row, calculate WAFER_OUT_QTY = PRODUCTION / NETDIE_300_CNT only when NETDIE_300_CNT > 0.",
                    "When NETDIE_300_CNT is 0 or null, set WAFER_OUT_QTY to 0 or null according to answer needs and put PRODUCTION into FAIL_UNIT_QTY.",
                    "Aggregate WAFER_OUT_QTY and FAIL_UNIT_QTY by the question grain.",
                ],
            )


def _normalize_quantity_payload(key: str, payload: dict[str, Any], source_text: str, metadata_context: dict[str, Any]) -> str:
    # 수량 항목은 같은 raw input 블록 안에 여러 개가 함께 들어올 수 있습니다.
    # 전체 원문을 기준으로 보완하면 장비/INPUT 같은 다른 항목의 단서가 모든 quantity item에 섞이므로,
    # item payload 자체에 포함된 이름, 별칭, 컬럼, 계산 규칙만 기준으로 정규화합니다.
    quantity_text = _term_text(key, payload)
    source_columns = _as_text_list(payload.get("source_columns"))
    quantity_columns = _as_text_list(payload.get("quantity_column"))
    inferred_columns = _identifier_columns_from_metric_text(quantity_text)
    if inferred_columns:
        payload["source_columns"] = _unique_text([*source_columns, *inferred_columns])
    all_columns = {column.upper() for column in [*quantity_columns, *_as_text_list(payload.get("source_columns"))]}
    inferred_family = _infer_dataset_family(quantity_text, all_columns, metadata_context)
    if inferred_family and not _clean(payload.get("dataset_family")):
        payload["dataset_family"] = inferred_family

    compact = _compact_text(quantity_text)
    if _has_input_production_cue(quantity_text):
        key = "input_production" if not key or key in {"production", "input"} else key
        payload.setdefault("dataset_family", "production")
        payload.setdefault("quantity_column", "PRODUCTION")
        payload.setdefault("aggregation", "sum")
        payload.setdefault("output_column", "INPUT_QTY")
        payload.setdefault("condition", {"OPER_DESC": "INPUT"})

    if _has_unique_count_cue(quantity_text) and _has_equipment_count_cue(quantity_text, all_columns):
        key = "equipment_count" if not key or key in {"count", "equipment"} else key
        payload.setdefault("dataset_family", "equipment")
        payload["quantity_column"] = _preferred_equipment_column(all_columns)
        payload.setdefault("aggregation", "nunique")
        payload.setdefault("output_column", "EQP_COUNT")
        _merge_text_list_field(payload, "aliases", ["장비 대수", "설비 대수", "equipment count"])

    return key


def _metric_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "display_name",
        "description",
        "formula",
        "calculation_rule",
        "zero_division_rule",
        "pandas_code_instructions",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            parts.extend(_clean(item) for item in value)
        else:
            parts.append(_clean(value))
    parts.extend(_as_text_list(payload.get("aliases")))
    parts.extend(_as_text_list(payload.get("source_columns")))
    parts.extend(_as_text_list(payload.get("output_columns")))
    if payload.get("output_column"):
        parts.append(_clean(payload.get("output_column")))
    return "\n".join(part for part in parts if part)


def _term_text(key: str, payload: dict[str, Any], source_text: str = "") -> str:
    parts = [key, source_text]
    for field in (
        "display_name",
        "description",
        "formula",
        "calculation_rule",
        "aggregation",
        "quantity_column",
        "source_columns",
        "output_column",
        "output_columns",
    ):
        value = payload.get(field)
        if isinstance(value, list):
            parts.extend(_clean(item) for item in value)
        else:
            parts.append(_clean(value))
    parts.extend(_as_text_list(payload.get("aliases")))
    return "\n".join(part for part in parts if part)


def _output_columns_from_metric_text(text: str) -> list[str]:
    outputs: list[str] = []
    for match in re.finditer(r"\b([A-Z][A-Z0-9_]{2,})\s*=", text):
        outputs.append(match.group(1))
    for match in re.finditer(r"\b([A-Z][A-Z0-9_]{2,})\b[^\n.。]*(?:output|출력|결과|보여)", text, flags=re.IGNORECASE):
        outputs.append(match.group(1))
    for match in re.finditer(r"(?:output_columns?|출력\s*컬럼|결과\s*컬럼)[^\n:：=]*[:：=]?\s*([A-Z0-9_,\s]+)", text, flags=re.IGNORECASE):
        outputs.extend(_as_text_list(match.group(1)))
    return _unique_text(outputs)


def _identifier_columns_from_metric_text(text: str) -> list[str]:
    bracketed = re.findall(r"\[([A-Za-z][A-Za-z0-9_]*)\]", text)
    identifiers = re.findall(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]{2,})(?![A-Za-z0-9_])", text)
    candidates = [*bracketed, *identifiers]
    result = []
    for column in candidates:
        column_text = _clean(column).upper()
        if not column_text or column_text in FORMULA_FUNCTION_WORDS:
            continue
        if column_text.endswith("_QTY") and column_text not in {"PRODUCTION", "FAIL_UNIT_QTY"}:
            # Output quantity names are handled separately unless they are explicitly used as source terms.
            continue
        result.append(column_text)
    return _unique_text(result)


def _infer_dataset_family(text: str, columns: set[str], metadata_context: dict[str, Any]) -> str:
    compact = _compact_text(text)
    table_items = metadata_context.get("table_catalog", []) if isinstance(metadata_context.get("table_catalog"), list) else []
    for item in table_items:
        if not isinstance(item, dict):
            continue
        family = _clean(item.get("dataset_family"))
        if not family:
            continue
        candidates = [item.get("dataset_key"), item.get("description"), item.get("primary_quantity_column")]
        candidates.extend(_as_text_list(item.get("aliases")))
        candidates.extend(_as_text_list(item.get("columns")))
        for candidate in candidates:
            candidate_compact = _compact_text(candidate)
            if candidate_compact and candidate_compact in compact:
                return family
        mapping_columns = _columns_from_mapping_dict(item.get("filter_mappings"))
        mapping_columns.extend(_columns_from_mapping_dict(item.get("standard_column_aliases")))
        if columns and columns.intersection({column.upper() for column in mapping_columns}):
            return family
    if {"INPUT_PLAN", "OUT_PLAN"}.intersection(columns) or any(cue in compact for cue in ("계획", "스케줄", "스케쥴", "schedule", "target")):
        return "target"
    if {"WIP"}.intersection(columns) or "재공" in compact:
        return "wip"
    if {"EQP_ID", "EQPID", "EQP_MODEL"}.intersection(columns) or any(cue in compact for cue in ("장비", "설비", "equipment", "assign")):
        return "equipment"
    if {"PRODUCTION", "NETDIE_300_CNT"}.intersection(columns) or any(cue in compact for cue in ("production", "생산", "실적")):
        return "production"
    return ""


def _columns_from_mapping_dict(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    result: list[str] = []
    for key, mapped in value.items():
        result.extend(_as_text_list(key))
        result.extend(_as_text_list(mapped))
    return _unique_text(result)


def _source_text(payload: dict[str, Any]) -> str:
    return "\n".join(_clean(payload.get(key)) for key in ("refined_text", "raw_text") if _clean(payload.get(key)))


def _source_mentions_product_key_columns(text: str) -> bool:
    compact = _compact_text(text)
    return any(cue in compact for cue in ("productkey", "product_key", "productkeycolumns", "제품키", "제품기준", "조인키", "결합키"))


def _source_mentions_process_group(text: str) -> bool:
    compact = _compact_text(text)
    return any(cue in compact for cue in ("processgroup", "공정그룹", "포함공정", "공정은", "공정목록"))


def _is_derived_metric_artifact(section: str, key: str, payload: dict[str, Any], source_text: str) -> bool:
    if not _has_formula_metric_cue(source_text, {"PRODUCTION", "NETDIE_300_CNT"}):
        return False
    compact_key = _compact_text(key)
    compact_payload = _compact_text(_term_text(key, payload, source_text))
    if section == "product_terms" and compact_key in {"wafer", "wafers"}:
        return True
    if section == "quantity_terms" and compact_key in {"failunitqty", "failunitquantity"}:
        return True
    return section == "quantity_terms" and "failunitqty" in compact_payload and "output" in compact_payload


def _has_formula_metric_cue(text: str, required_columns: set[str]) -> bool:
    upper = str(text or "").upper()
    return all(column in upper for column in required_columns)


def _has_input_production_cue(text: str) -> bool:
    compact = _compact_text(text)
    return ("input" in compact or "투입" in compact) and ("production" in compact or "생산" in compact or "실적" in compact)


def _has_unique_count_cue(text: str) -> bool:
    compact = _compact_text(text)
    return any(cue in compact for cue in ("uniquecount", "nunique", "distinct", "중복제거", "고유", "유니크", "대수"))


def _has_equipment_count_cue(text: str, columns: set[str]) -> bool:
    compact = _compact_text(text)
    return bool({"EQP_ID", "EQPID", "EQP_MODEL"}.intersection(columns)) or any(cue in compact for cue in ("장비", "설비", "equipment", "eqpid", "eqp_id", "assign"))


def _preferred_equipment_column(columns: set[str]) -> str:
    for column in ("EQP_ID", "EQPID", "EQP_MODEL"):
        if column in columns:
            return column
    return "EQP_ID"


def _compact_text(value: Any) -> str:
    return re.sub(r"[\s_\-./]+", "", str(value or "").strip().lower())


def _merge_text_list_field(payload: dict[str, Any], key: str, values: list[str]) -> None:
    payload[key] = _unique_text([*_as_text_list(payload.get(key)), *values])


def _normalize_condition_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if any(key in value for key in ("column", "columns", "field", "fields", "op", "operator")):
        filters, conditions, changed = _normalize_column_condition_filter(value)
        if changed and conditions:
            return conditions
        if changed and filters:
            return filters
    result: dict[str, Any] = {}
    for column, condition_value in value.items():
        column_text = _clean(column)
        if not column_text:
            continue
        if column_text in {"$and", "$or"}:
            nested = [_normalize_condition_object(item) for item in _as_list(condition_value)]
            nested = [item for item in nested if item]
            if nested:
                result[column_text] = nested
            continue
        if isinstance(condition_value, dict):
            if any(_clean(key) in CONDITION_FILTER_KEYS for key in condition_value):
                result[column_text] = deepcopy(condition_value)
            else:
                result[column_text] = _normalize_condition_object(condition_value) or deepcopy(condition_value)
            continue
        parsed_condition = _condition_from_text(condition_value)
        result[column_text] = parsed_condition or deepcopy(condition_value)
    return result


def _normalize_filter_descriptors(value: Any) -> tuple[dict[str, Any], dict[str, Any], bool]:
    if isinstance(value, dict):
        if any(key in value for key in ("column", "columns", "field", "fields", "op", "operator")):
            return _normalize_column_condition_filter(value)
        filters: dict[str, Any] = {}
        conditions: dict[str, Any] = {}
        for field, raw_value in value.items():
            field_text = _clean(field)
            if not field_text:
                continue
            if isinstance(raw_value, dict) and any(_clean(key) in CONDITION_FILTER_KEYS for key in raw_value):
                _merge_condition(conditions, field_text, raw_value)
            else:
                _merge_filter_values(filters, field_text, raw_value)
        return filters, conditions, bool(filters or conditions)
    if not isinstance(value, list):
        return {}, {}, False

    merged_filters: dict[str, Any] = {}
    merged_conditions: dict[str, Any] = {}
    for item in value:
        filters, conditions, changed = _normalize_column_condition_filter(item)
        if not changed:
            return {}, {}, False
        for field, filter_values in filters.items():
            _merge_filter_values(merged_filters, field, filter_values)
        for column, condition in conditions.items():
            _merge_condition(merged_conditions, column, condition)
    return merged_filters, merged_conditions, bool(merged_filters or merged_conditions)


def _normalize_column_condition_filter(value: Any) -> tuple[dict[str, Any], dict[str, Any], bool]:
    if not isinstance(value, dict):
        return {}, {}, False
    columns = _as_text_list(value.get("column") or value.get("columns") or value.get("field") or value.get("fields"))
    if not columns:
        return {}, {}, False
    op = _clean(value.get("op") or value.get("operator")).lower()
    raw_values = value.get("values") if value.get("values") is not None else value.get("value")
    raw_condition = value.get("condition") or value.get("conditions")
    filters: dict[str, Any] = {}
    conditions: dict[str, Any] = {}

    if op in {"eq", "equals", "="}:
        for column in columns:
            _merge_filter_values(filters, column, raw_values)
        return filters, {}, True
    if op == "in":
        for column in columns:
            _merge_filter_values(filters, column, raw_values)
        return filters, {}, True
    if op in {"not_empty", "exists", "not_null", "is_not_null"}:
        for column in columns:
            _merge_condition(conditions, column, {"exists": True, "not_in": [None, ""]})
        return {}, conditions, True
    if op in {"is_empty", "is_null", "null"}:
        for column in columns:
            _merge_condition(conditions, column, {"is_empty": True})
        return {}, conditions, True
    if op in {"starts_with", "ends_with", "contains", "gt", "gte", "lt", "lte", "ne", "not_eq", "between"}:
        for column in columns:
            _merge_condition(conditions, column, {op: deepcopy(raw_values)})
        return {}, conditions, True

    if raw_condition not in (None, "", [], {}):
        filter_values = _filter_values_from_condition_text(raw_condition)
        if filter_values:
            for column in columns:
                _merge_filter_values(filters, column, filter_values)
            return filters, {}, True
        condition = _condition_from_text(raw_condition)
        if condition:
            for column in columns:
                _merge_condition(conditions, column, condition)
            return {}, conditions, True
    return {}, {}, False


def _condition_from_text(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and any(_clean(key) in CONDITION_FILTER_KEYS for key in value):
        return deepcopy(value)
    text = str(value or "").strip()
    lowered = text.lower().replace('"', "'")
    if not lowered:
        return {}
    condition: dict[str, Any] = {}
    if "is not null" in lowered or "not null" in lowered or "exists" in lowered or "존재" in lowered:
        condition["exists"] = True
    if "!= ''" in lowered or "<> ''" in lowered or "not empty" in lowered or "not blank" in lowered or "빈칸" in lowered:
        condition["not_in"] = [None, ""]
    if "is null" in lowered or "null" == lowered or "비어" in lowered:
        condition["is_empty"] = True
    starts_with = re.search(r"(?:starts?_?with|prefix)\s*['\"]?([^'\",\s]+)", text, flags=re.IGNORECASE)
    if not starts_with:
        starts_with = re.search(r"([0-9A-Za-z가-힣_./-]+)\s*로\s*시작", text, flags=re.IGNORECASE)
    if starts_with:
        condition["starts_with"] = starts_with.group(1)
    ends_with = re.search(r"(?:ends?_?with|suffix)\s*['\"]?([^'\",\s]+)", text, flags=re.IGNORECASE)
    if ends_with:
        condition["ends_with"] = ends_with.group(1)
    contains = re.search(r"(?:contains|include|포함)\s*['\"]?([^'\",\s]+)", text, flags=re.IGNORECASE)
    if contains:
        condition["contains"] = contains.group(1)
    return condition


def _filter_values_from_condition_text(value: Any) -> list[str]:
    if isinstance(value, dict):
        for key in ("equals", "eq", "in"):
            if value.get(key) is not None:
                return _as_text_list(value.get(key))
        return []
    text = str(value or "").strip()
    if not text:
        return []
    match = re.match(r"^(?:=|==)\s*(.+)$", text)
    if not match:
        match = re.match(r"^[A-Za-z0-9_./ -]+\s*=\s*(.+)$", text)
    if not match:
        match = re.match(r"(?i)^in\s*\((.*)\)$", text)
    if not match:
        return []
    raw_values = match.group(1).strip().strip("()[]")
    return [_clean(item).strip("'\"") for item in _as_text_list(raw_values) if _clean(item).strip("'\"")]


def _merge_filter_values(target: dict[str, Any], field: str, values: Any) -> None:
    field_text = _clean(field)
    if not field_text:
        return
    merged = _as_text_list(target.get(field_text)) + _as_text_list(values)
    result = []
    for value in merged:
        if value and value not in result:
            result.append(value)
    if result:
        target[field_text] = result


def _merge_condition(target: dict[str, Any], column: str, condition: dict[str, Any]) -> None:
    column_text = _clean(column)
    if not column_text or not condition:
        return
    existing = target.get(column_text)
    if isinstance(existing, dict):
        merged = deepcopy(existing)
        merged.update(deepcopy(condition))
        target[column_text] = merged
    else:
        target[column_text] = deepcopy(condition)


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


def _unique_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in _as_list(values):
        text = _clean(value)
        if text and text not in result:
            result.append(text)
    return result


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


# 컴포넌트 설명: 04 Domain Authoring Result Normalizer
# Langflow 표시 설명: domain authoring LLM JSON을 MongoDB 저장 가능한 domain item 구조로 정규화합니다.
class DomainAuthoringResultNormalizer(Component):

    display_name = "04 Domain Authoring Result Normalizer"
    description = "domain authoring LLM JSON을 MongoDB 저장 가능한 domain item 구조로 정규화합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: domain authoring LLM JSON을 MongoDB 저장 가능한 domain item 구조로 정규화합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = normalize_domain_authoring_result(getattr(self, "payload", None), getattr(self, "llm_response", ""))

        self.status = {"items": len(result.get("items", [])), "errors": len(result.get("errors", []))}
        return Data(data=result)
