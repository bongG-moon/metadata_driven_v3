from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


def normalize_main_flow_filter_authoring_result(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
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
    filter_key = _clean(raw_item.get("filter_key") or raw_item.get("key") or raw_item.get("parameter_key"))
    payload = deepcopy(raw_item.get("payload")) if isinstance(raw_item.get("payload"), dict) else {}
    if not filter_key:
        errors.append(f"items[{index}] filter_key가 없습니다.")
    aliases = _as_text_list(payload.get("aliases"))
    columns = _as_text_list(payload.get("column_candidates"))
    if not aliases:
        errors.append(f"{filter_key} aliases가 필요합니다.")
    if not columns:
        errors.append(f"{filter_key} column_candidates가 필요합니다.")
    if not _clean(payload.get("semantic_role")):
        errors.append(f"{filter_key} semantic_role이 필요합니다.")
    payload["aliases"] = aliases
    payload["column_candidates"] = columns
    payload.setdefault("value_type", "string")
    payload.setdefault("value_shape", "scalar")
    payload.setdefault("operator", "eq")
    if payload.get("required_params") is not None:
        payload["required_params"] = _as_text_list(payload.get("required_params"))
    if payload.get("sample_values") is not None:
        payload["sample_values"] = _as_text_list(payload.get("sample_values"))
    if not isinstance(payload.get("value_mappings", {}), dict):
        payload["value_mappings"] = {}
    return {
        "filter_key": filter_key,
        "key": filter_key,
        "status": _clean(raw_item.get("status") or "active"),
        "payload": payload,
        "confidence": _clean(raw_item.get("confidence") or "medium"),
    }, errors


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


class MainFlowFilterAuthoringResultNormalizer(Component):
    display_name = "04 Main Flow Filter Authoring Result Normalizer"
    description = "Normalizes the main-flow-filter authoring LLM JSON into MongoDB-ready filter items."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = normalize_main_flow_filter_authoring_result(getattr(self, "payload", None), getattr(self, "llm_response", ""))
        self.status = {"items": len(result.get("items", [])), "errors": len(result.get("errors", []))}
        return Data(data=result)
