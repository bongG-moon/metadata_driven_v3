# 파일 설명: 06 Selected Flow API Runner Langflow custom component 파일입니다.
# 흐름 역할: 선택된 subflow 하나만 Langflow API로 실행하고 그 결과를 Message/API 응답으로 정리합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

import requests
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


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


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 선택된 subflow 하나만 Langflow API로 실행하고 그 결과를 Message/API 응답으로 정리합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_selected_flow_api_call(
    route_response_value: Any,
) -> dict[str, Any]:
    route_response = _as_dict(route_response_value)
    subflow_call = route_response.get("subflow_call") if isinstance(route_response.get("subflow_call"), dict) else {}
    request = route_response.get("request") if isinstance(route_response.get("request"), dict) else {}
    selected_flow = str(subflow_call.get("selected_flow") or route_response.get("selected_flow") or "data_analysis_flow").strip()
    question = str(
        subflow_call.get("input_value") or subflow_call.get("prompt") or request.get("question") or route_response.get("question") or ""
    ).strip()
    session_id = str(subflow_call.get("session_id") or request.get("session_id") or route_response.get("session_id") or "").strip()
    input_type_value = str(subflow_call.get("input_type") or "chat").strip() or "chat"
    output_type_value = str(subflow_call.get("output_type") or "chat").strip() or "chat"
    base_url = str(os.getenv("LANGFLOW_BASE_URL") or os.getenv("LANGFLOW_API_BASE_URL") or "").strip()
    api_url = _normalize_api_url_or_flow_id(str(subflow_call.get("api_url") or route_response.get("api_url") or "").strip(), base_url)
    if not api_url:
        api_url = _resolve_flow_api_url(selected_flow, route_response)
    return {
        "selected_flow": selected_flow,
        "api_url": api_url,
        "request": {
            "input_value": question,
            "input_type": input_type_value,
            "output_type": output_type_value,
            "session_id": session_id,
        },
    }


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 선택된 subflow 하나만 Langflow API로 실행하고 그 결과를 Message/API 응답으로 정리합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def run_selected_flow_api(
    route_response_value: Any,
    *,
    api_key: str = "",
    timeout_seconds: Any = 180,
    post_func: Any = None,
) -> dict[str, Any]:
    call = build_selected_flow_api_call(
        route_response_value,
    )
    if not call["api_url"]:
        selected_flow = call["selected_flow"]
        return _error_result(
            call,
            f"{selected_flow} API URL is not configured. Set LANGFLOW_BASE_URL plus {FLOW_ID_ENV.get(selected_flow, 'the flow id')}, "
            f"or set {FLOW_API_URL_ENV.get(selected_flow, 'the flow API URL')}.",
        )
    if not call["request"]["input_value"]:
        return _error_result(call, "Selected flow input question is empty.")

    headers = {"Content-Type": "application/json"}
    if str(api_key or "").strip():
        headers["x-api-key"] = str(api_key).strip()
    timeout = _safe_int(timeout_seconds, default=180)
    post = post_func or requests.post
    try:
        response = post(call["api_url"], json=call["request"], headers=headers, timeout=timeout)
        raise_for_status = getattr(response, "raise_for_status", None)
        if callable(raise_for_status):
            raise_for_status()
        parsed = response.json() if callable(getattr(response, "json", None)) else response
    except Exception as exc:
        return _error_result(call, f"Selected flow API call failed: {exc}")

    raw_response = parsed if isinstance(parsed, dict) else {"response": parsed}
    message = _extract_message_text(raw_response) or "Selected flow returned no message."
    return {
        "status": "ok",
        "selected_flow": call["selected_flow"],
        "api_url": call["api_url"],
        "request": call["request"],
        "message": message,
        "raw_response": raw_response,
    }


def _resolve_flow_api_url(
    selected_flow: str,
    route_response: dict[str, Any],
) -> str:
    subflow_call = route_response.get("subflow_call") if isinstance(route_response.get("subflow_call"), dict) else {}
    explicit = str(os.getenv(FLOW_API_URL_ENV.get(selected_flow, "")) or "").strip()
    base_url = str(os.getenv("LANGFLOW_BASE_URL") or os.getenv("LANGFLOW_API_BASE_URL") or "").strip()
    if explicit:
        return _normalize_api_url_or_flow_id(explicit, base_url)
    flow_id_env = str(subflow_call.get("flow_id_env") or route_response.get("flow_id_env") or FLOW_ID_ENV.get(selected_flow, "")).strip()
    flow_id = str(subflow_call.get("flow_id") or route_response.get("flow_id") or os.getenv(flow_id_env) or "").strip()
    if base_url and flow_id:
        return _flow_run_url(base_url, flow_id)
    return ""


def _normalize_api_url_or_flow_id(value: str, base_url: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _is_http_url(text):
        return text
    if base_url:
        return _flow_run_url(base_url, text)
    return ""


def _is_http_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _flow_run_url(base_url: str, flow_id_or_path: str) -> str:
    base = base_url.rstrip("/")
    target = str(flow_id_or_path or "").strip()
    if target.startswith("/"):
        return base + target
    if target.startswith("api/v1/run/"):
        return f"{base}/{target}"
    return f"{base}/api/v1/run/{target}"


def _extract_message_text(value: Any) -> str:
    if value is None:
        return ""
    for attr in ("text", "content", "message"):
        text = getattr(value, attr, None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("answer_message", "message", "response", "text", "content", "answer", "output"):
            nested = value.get(key)
            text = _extract_message_text(nested)
            if text:
                return text
        for key in ("api_response", "data", "result", "results", "outputs", "artifacts"):
            nested = value.get(key)
            text = _extract_message_text(nested)
            if text:
                return text
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                text = _extract_message_text(nested)
                if text:
                    return text
    if isinstance(value, list):
        for item in value:
            text = _extract_message_text(item)
            if text:
                return text
    return ""


def _error_result(call: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "selected_flow": call.get("selected_flow", ""),
        "api_url": call.get("api_url", ""),
        "request": call.get("request", {}),
        "message": message,
        "raw_response": {},
        "errors": [message],
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _safe_int(value: Any, default: int) -> int:
    try:
        return max(1, int(str(value or "").strip()))
    except Exception:
        return default


def _make_message(text: str) -> Message:
    try:
        return Message(text=text)
    except TypeError:
        return Message(content=text)


def _make_data(payload: dict[str, Any]) -> Data:
    try:
        return Data(data=payload)
    except TypeError:
        return Data(payload)


# 컴포넌트 설명: 06 Selected Flow API Runner
# Langflow 표시 설명: 선택된 subflow 하나만 Langflow API로 실행하고 그 결과를 Message/API 응답으로 정리합니다.
class SelectedFlowApiRunner(Component):

    display_name = "06 Selected Flow API Runner"
    description = "선택된 subflow 하나만 Langflow API로 실행하고 그 결과를 Message/API 응답으로 정리합니다."
    icon = "Workflow"
    name = "SelectedFlowApiRunner"

    inputs = [
        DataInput(name="route_response", display_name="Route Response", required=True),
        MessageTextInput(name="api_key", display_name="API Key", value="", advanced=True),
        MessageTextInput(name="timeout_seconds", display_name="Timeout Seconds", value="180", advanced=True),
    ]
    outputs = [
        Output(name="message", display_name="Message", method="build_message", types=["Message"]),
        Output(name="api_response", display_name="API Response", method="build_api_response", types=["Data"]),
    ]


    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 선택된 subflow 하나만 Langflow API로 실행하고 그 결과를 Message/API 응답으로 정리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def _result(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_result", None)
        if isinstance(cached, dict):
            return cached
        result = run_selected_flow_api(
            getattr(self, "route_response", None),
            api_key=getattr(self, "api_key", ""),
            timeout_seconds=getattr(self, "timeout_seconds", "180"),
        )
        self._cached_result = result
        return result

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 선택된 subflow 하나만 Langflow API로 실행하고 그 결과를 Message/API 응답으로 정리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_message(self) -> Message:
        result = self._result()
        self.status = {
            "status": result.get("status"),
            "selected_flow": result.get("selected_flow"),
            "has_message": bool(result.get("message")),
        }
        return _make_message(str(result.get("message") or ""))

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 선택된 subflow 하나만 Langflow API로 실행하고 그 결과를 Message/API 응답으로 정리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_api_response(self) -> Data:
        result = self._result()
        self.status = {
            "status": result.get("status"),
            "selected_flow": result.get("selected_flow"),
            "has_message": bool(result.get("message")),
        }
        return _make_data(result)
