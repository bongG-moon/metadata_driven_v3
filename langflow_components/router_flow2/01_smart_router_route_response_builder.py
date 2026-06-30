# 파일 설명: 01 Smart Router Route Response Builder Langflow custom component 파일입니다.
# 흐름 역할: Langflow 내장 Smart Router의 선택 결과를 subflow API 실행용 route_response로 변환합니다.

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, MessageTextInput, Output
from lfx.schema.data import Data


FLOW_BY_ROUTE = {
    "direct_answer": "metadata_qa_flow",
    "metadata_qa": "metadata_qa_flow",
    "data_analysis": "data_analysis_flow",
    "report_generation": "report_generation_flow",
    "operations_diagnosis": "operations_diagnosis_flow",
}
FLOW_API_URL_ENV = {
    "metadata_qa_flow": "LANGFLOW_METADATA_QA_API_URL",
    "data_analysis_flow": "LANGFLOW_DATA_ANALYSIS_API_URL",
    "report_generation_flow": "LANGFLOW_REPORT_GENERATION_API_URL",
    "operations_diagnosis_flow": "LANGFLOW_OPERATIONS_DIAGNOSIS_API_URL",
}
FLOW_ID_ENV = {
    "metadata_qa_flow": "LANGFLOW_METADATA_QA_FLOW_ID",
    "data_analysis_flow": "LANGFLOW_DATA_ANALYSIS_FLOW_ID",
    "report_generation_flow": "LANGFLOW_REPORT_GENERATION_FLOW_ID",
    "operations_diagnosis_flow": "LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID",
}
ROUTE_ALIASES = {
    "directanswer": "metadata_qa",
    "direct_answer": "metadata_qa",
    "help": "metadata_qa",
    "greeting": "metadata_qa",
    "metadata": "metadata_qa",
    "metadataqa": "metadata_qa",
    "metadata_qa": "metadata_qa",
    "metadataqaflow": "metadata_qa",
    "metadata_qa_flow": "metadata_qa",
    "catalog": "metadata_qa",
    "domain": "metadata_qa",
    "tablecatalog": "metadata_qa",
    "table_catalog": "metadata_qa",
    "analysis": "data_analysis",
    "dataanalysis": "data_analysis",
    "data_analysis": "data_analysis",
    "dataanalysisflow": "data_analysis",
    "data_analysis_flow": "data_analysis",
    "pandas": "data_analysis",
    "retrieval": "data_analysis",
    "query": "data_analysis",
    "report": "report_generation",
    "reportgeneration": "report_generation",
    "report_generation": "report_generation",
    "reportgenerationflow": "report_generation",
    "report_generation_flow": "report_generation",
    "diagnosis": "operations_diagnosis",
    "operationdiagnosis": "operations_diagnosis",
    "operationsdiagnosis": "operations_diagnosis",
    "operations_diagnosis": "operations_diagnosis",
    "operationsdiagnosisflow": "operations_diagnosis",
    "operations_diagnosis_flow": "operations_diagnosis",
}


def build_smart_router_route_payload(
    payload_value: Any,
    smart_router_output_value: Any = "",
    *,
    forced_route: str = "",
    default_route: str = "data_analysis",
    route_catalog_json: str = "",
) -> dict[str, Any]:
    payload = _as_dict(payload_value)
    catalog = _route_catalog(route_catalog_json)
    decision = _decision_from_output(smart_router_output_value)
    route = _resolve_route(forced_route or decision.get("route") or decision.get("selected_route") or decision.get("label") or decision.get("text"), default_route)
    catalog_item = catalog.get(route, {})
    selected_flow = _clean(decision.get("selected_flow") or catalog_item.get("selected_flow") or FLOW_BY_ROUTE.get(route) or "data_analysis_flow")
    metadata_route = {
        "route": route,
        "selected_flow": selected_flow,
        "api_url": _clean(decision.get("api_url") or catalog_item.get("api_url")),
        "flow_id": _clean(decision.get("flow_id") or catalog_item.get("flow_id")),
        "metadata_action": _clean(decision.get("metadata_action") or catalog_item.get("metadata_action")),
        "target_dataset": _clean(decision.get("target_dataset") or catalog_item.get("target_dataset")),
        "target_family": _clean(decision.get("target_family") or catalog_item.get("target_family")),
        "route_confidence": _clean(decision.get("confidence") or decision.get("route_confidence") or catalog_item.get("confidence") or "medium"),
        "route_source": "langflow_smart_router",
        "route_llm_used": True,
        "reason": _clean(decision.get("reason") or catalog_item.get("reason")),
        "raw_smart_router_output": decision.get("raw_output", ""),
    }
    next_payload = deepcopy(payload)
    next_payload.setdefault("info", [])
    next_payload.setdefault("warnings", [])
    next_payload.setdefault("errors", [])
    next_payload["metadata_route"] = metadata_route
    next_payload["selected_flow"] = selected_flow
    next_payload["route_response"] = _route_response(next_payload)
    return next_payload


def build_route_response(
    payload_value: Any,
    smart_router_output_value: Any = "",
    *,
    forced_route: str = "",
    default_route: str = "data_analysis",
    route_catalog_json: str = "",
) -> dict[str, Any]:
    routed_payload = build_smart_router_route_payload(
        payload_value,
        smart_router_output_value,
        forced_route=forced_route,
        default_route=default_route,
        route_catalog_json=route_catalog_json,
    )
    return routed_payload["route_response"]


def _route_response(payload: dict[str, Any]) -> dict[str, Any]:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    metadata_route = payload.get("metadata_route") if isinstance(payload.get("metadata_route"), dict) else {}
    route = _clean(metadata_route.get("route") or "data_analysis")
    selected_flow = _clean(metadata_route.get("selected_flow") or FLOW_BY_ROUTE.get(route) or "data_analysis_flow")
    question = _clean(request.get("question"))
    session_id = _session_id_from_mapping(request) or _session_id_from_mapping(state) or "demo-session"
    api_url = _normalize_api_url_or_flow_id(metadata_route.get("api_url") or metadata_route.get("target_api_url"))
    if not api_url:
        api_url = _resolve_subflow_api_url(selected_flow, flow_id_override=metadata_route.get("flow_id"))
    input_type = os.getenv("LANGFLOW_SUBFLOW_INPUT_TYPE") or os.getenv("LANGFLOW_INPUT_TYPE") or "chat"
    output_type = os.getenv("LANGFLOW_SUBFLOW_OUTPUT_TYPE") or os.getenv("LANGFLOW_OUTPUT_TYPE") or "chat"
    return {
        "status": "ok",
        "response_type": "route_decision",
        "request": {"question": question, "session_id": session_id},
        "route": route,
        "selected_flow": selected_flow,
        "api_url": api_url,
        "api_url_env": _flow_api_url_env(selected_flow),
        "flow_id_env": _flow_id_env(selected_flow),
        "subflow_call": {
            "selected_flow": selected_flow,
            "api_url": api_url,
            "api_url_env": _flow_api_url_env(selected_flow),
            "flow_id_env": _flow_id_env(selected_flow),
            "prompt": question,
            "input_value": question,
            "input_type": input_type,
            "output_type": output_type,
            "session_id": session_id,
        },
        "route_confidence": metadata_route.get("route_confidence") or "medium",
        "route_source": metadata_route.get("route_source") or "langflow_smart_router",
        "route_llm_used": bool(metadata_route.get("route_llm_used", True)),
        "metadata_action": metadata_route.get("metadata_action", ""),
        "target_dataset": metadata_route.get("target_dataset", ""),
        "target_family": metadata_route.get("target_family", ""),
        "reason": metadata_route.get("reason", ""),
        "warnings": list(payload.get("warnings", [])) if isinstance(payload.get("warnings"), list) else [],
        "errors": list(payload.get("errors", [])) if isinstance(payload.get("errors"), list) else [],
    }


def _decision_from_output(value: Any) -> dict[str, Any]:
    data = _as_dict(value)
    text = _text(value)
    parsed = _extract_json(text)
    if parsed:
        data = _deep_merge(data, parsed)
    if not data:
        data = {"text": text}
    for key in ("route", "selected_route", "label", "output_name", "branch", "result", "selected", "name"):
        if _clean(data.get(key)):
            data.setdefault("route", data.get(key))
            break
    data["raw_output"] = text or json.dumps(data, ensure_ascii=False)
    return data


def _resolve_route(value: Any, default_route: str) -> str:
    text = _clean(value)
    parsed = _extract_json(text)
    if parsed:
        for key in ("route", "selected_route", "label", "selected_flow"):
            if _clean(parsed.get(key)):
                text = _clean(parsed.get(key))
                break
    normalized = _route_key(text)
    if normalized in ROUTE_ALIASES:
        return ROUTE_ALIASES[normalized]
    for alias, route in ROUTE_ALIASES.items():
        if alias and alias in normalized:
            return route
    fallback = ROUTE_ALIASES.get(_route_key(default_route), "")
    return fallback or "data_analysis"


def _route_catalog(value: str) -> dict[str, dict[str, Any]]:
    parsed = _extract_json(value)
    if not parsed:
        return {}
    raw_items = parsed.get("routes") if isinstance(parsed.get("routes"), list) else parsed
    if isinstance(raw_items, dict):
        iterable = []
        for key, item in raw_items.items():
            item_dict = dict(item) if isinstance(item, dict) else {"selected_flow": item}
            item_dict.setdefault("route", key)
            iterable.append(item_dict)
    elif isinstance(raw_items, list):
        iterable = [item for item in raw_items if isinstance(item, dict)]
    else:
        iterable = []
    catalog: dict[str, dict[str, Any]] = {}
    for item in iterable:
        route = _resolve_route(item.get("route") or item.get("label") or item.get("name") or item.get("selected_flow"), "data_analysis")
        catalog[route] = dict(item)
    return catalog


def _route_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9_가-힣]+", "", _clean(value).lower())


def _flow_id_env(selected_flow: str) -> str:
    return FLOW_ID_ENV.get(selected_flow, "LANGFLOW_DATA_ANALYSIS_FLOW_ID")


def _flow_api_url_env(selected_flow: str) -> str:
    return FLOW_API_URL_ENV.get(selected_flow, "LANGFLOW_DATA_ANALYSIS_API_URL")


def _resolve_subflow_api_url(selected_flow: str, flow_id_override: Any = "") -> str:
    explicit = _clean(os.getenv(_flow_api_url_env(selected_flow)))
    base_url = _clean(os.getenv("LANGFLOW_BASE_URL") or os.getenv("LANGFLOW_API_BASE_URL"))
    if explicit:
        if _is_http_url(explicit):
            return explicit
        if base_url:
            return _flow_run_url(base_url, explicit)
        return ""
    flow_id = _clean(flow_id_override or os.getenv(_flow_id_env(selected_flow)))
    if base_url and flow_id:
        return _flow_run_url(base_url, flow_id)
    return ""


def _normalize_api_url_or_flow_id(value: Any) -> str:
    text = _clean(value)
    if not text or text.lower() in {"none", "null", "n/a", "na"}:
        return ""
    if text.startswith("<") and text.endswith(">"):
        return ""
    if _is_http_url(text):
        return text
    base_url = _clean(os.getenv("LANGFLOW_BASE_URL") or os.getenv("LANGFLOW_API_BASE_URL"))
    if base_url:
        return _flow_run_url(base_url, text)
    return ""


def _is_http_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _flow_run_url(base_url: str, flow_id_or_path: str) -> str:
    base = base_url.rstrip("/")
    target = _clean(flow_id_or_path)
    if target.startswith("/"):
        return base + target
    if target.startswith("api/v1/run/"):
        return f"{base}/{target}"
    return f"{base}/api/v1/run/{target}"


def _session_id_from_mapping(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("session_id", "conversation_id", "chat_id"):
        text = _clean(value.get(key))
        if text:
            return text
    request = value.get("request") if isinstance(value.get("request"), dict) else {}
    for key in ("session_id", "conversation_id", "chat_id"):
        text = _clean(request.get(key))
        if text:
            return text
    context = value.get("context") if isinstance(value.get("context"), dict) else {}
    for key in ("session_id", "conversation_id", "chat_id"):
        text = _clean(context.get(key))
        if text:
            return text
    return ""


def _extract_json(value: Any) -> dict[str, Any]:
    raw = _clean(value)
    if not raw:
        return {}
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


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for attr in ("text", "content", "message"):
        text = getattr(value, attr, None)
        if isinstance(text, str):
            return text
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        for key in ("route", "selected_route", "label", "text", "message", "content", "result", "output"):
            if _clean(data.get(key)):
                return _clean(data.get(key))
        return json.dumps(data, ensure_ascii=False)
    return str(value or "")


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _clean(value: Any) -> str:
    return str(value or "").strip()


class SmartRouterRouteResponseBuilder(Component):

    display_name = "01 Smart Router Route Response Builder"
    description = "Langflow 내장 Smart Router의 선택 결과를 subflow API 실행용 route_response로 변환합니다."
    icon = "Route"

    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="smart_router_output", display_name="Smart Router Output", required=False, value=""),
        DropdownInput(
            name="forced_route",
            display_name="Forced Route",
            options=["", "metadata_qa", "data_analysis", "report_generation", "operations_diagnosis"],
            value="",
            advanced=True,
        ),
        DropdownInput(
            name="default_route",
            display_name="Default Route",
            options=["metadata_qa", "data_analysis", "report_generation", "operations_diagnosis"],
            value="data_analysis",
            advanced=True,
        ),
        MessageTextInput(name="route_catalog_json", display_name="Route Catalog JSON", value="", advanced=True),
    ]
    outputs = [
        Output(name="payload_out", display_name="Payload", method="build_payload"),
        Output(name="route_response", display_name="Route Response", method="build_route_response"),
    ]

    def _result(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_result", None)
        if isinstance(cached, dict):
            return cached
        result = build_smart_router_route_payload(
            getattr(self, "payload", None),
            getattr(self, "smart_router_output", ""),
            forced_route=getattr(self, "forced_route", ""),
            default_route=getattr(self, "default_route", "data_analysis"),
            route_catalog_json=getattr(self, "route_catalog_json", ""),
        )
        self._cached_result = result
        return result

    def build_payload(self) -> Data:
        result = self._result()
        route = (result.get("metadata_route") or {}).get("route", "")
        self.status = {"route": route, "selected_flow": result.get("selected_flow")}
        return Data(data=result)

    def build_route_response(self) -> Data:
        result = self._result().get("route_response", {})
        self.status = {"route": result.get("route"), "selected_flow": result.get("selected_flow")}
        return Data(data=result)
