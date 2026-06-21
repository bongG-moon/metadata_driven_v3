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
    "product_key_columns",
}


def normalize_domain_authoring_result(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    parsed = _extract_json_object(_text(llm_response_value))
    errors = []
    items = []
    if not parsed:
        errors.append("저장 형식 변환 LLM 응답에서 JSON을 찾지 못했습니다.")
    raw_items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
    for index, raw_item in enumerate(raw_items):
        item, item_errors = _normalize_item(raw_item, index)
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


def _normalize_item(raw_item: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors = []
    if not isinstance(raw_item, dict):
        return None, [f"items[{index}]가 object가 아닙니다."]
    section = _clean(raw_item.get("section") or raw_item.get("gbn")).lower()
    key = _clean(raw_item.get("key") or raw_item.get("name"))
    payload = deepcopy(raw_item.get("payload")) if isinstance(raw_item.get("payload"), dict) else {}
    if section not in ALLOWED_SECTIONS:
        errors.append(f"items[{index}] section이 허용값이 아닙니다: {section}")
    if not key and section != "product_key_columns":
        errors.append(f"items[{index}] key가 없습니다.")
    if section == "product_key_columns":
        columns = _as_text_list(raw_item.get("columns") or payload.get("columns") or payload.get("product_key_columns"))
        if not columns:
            errors.append("product_key_columns에는 columns 목록이 필요합니다.")
        key = key or "default"
        payload = {"columns": columns, "product_key_columns": columns}
    else:
        payload.setdefault("aliases", _as_text_list(payload.get("aliases")))
        if section in {"product_terms", "status_terms"}:
            _normalize_condition_overrides(payload, errors, key)
        if section == "process_groups" and not _as_text_list(payload.get("processes")):
            errors.append(f"{key} process_groups에는 processes 목록이 필요합니다.")
        if section in {"quantity_terms", "status_terms"} and payload.get("aggregation") == "count_distinct":
            payload["aggregation"] = "nunique"
        if section in {"quantity_terms", "status_terms", "metric_terms", "analysis_recipes"}:
            if payload.get("required_quantity_terms") is not None:
                payload["required_quantity_terms"] = _as_text_list(payload.get("required_quantity_terms"))
            if payload.get("output_column") is not None:
                payload["output_column"] = _clean(payload.get("output_column"))
        if section == "analysis_recipes":
            _normalize_analysis_recipe_payload(payload)
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
    return item, errors


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
                clean_value[clean_key] = condition
            else:
                errors.append(f"{key} {field_name}.{clean_key}는 condition object여야 합니다.")
        payload[field_name] = clean_value


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
        text = _clean(item)
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


class DomainAuthoringResultNormalizer(Component):
    display_name = "04 Domain Authoring Result Normalizer"
    description = "Normalizes the domain authoring LLM JSON into MongoDB-ready domain items."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = normalize_domain_authoring_result(getattr(self, "payload", None), getattr(self, "llm_response", ""))
        self.status = {"items": len(result.get("items", [])), "errors": len(result.get("errors", []))}
        return Data(data=result)
