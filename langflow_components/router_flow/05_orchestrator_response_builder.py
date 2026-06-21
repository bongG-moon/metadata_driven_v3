# 파일 설명: 05 Orchestrator Response Builder Langflow custom component 파일입니다.
# 흐름 역할: 확정된 route를 selected subflow 이름과 Langflow API 호출 정보로 변환합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
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


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 확정된 route를 selected subflow 이름과 Langflow API 호출 정보로 변환합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_orchestrator_response(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    metadata_route = payload.get("metadata_route") if isinstance(payload.get("metadata_route"), dict) else {}
    route = str(metadata_route.get("route") or "data_analysis").strip()
    selected_flow = str(metadata_route.get("selected_flow") or FLOW_BY_ROUTE.get(route, "data_analysis_flow")).strip()
    session_id = _resolve_session_id(request, state)
    question = str(request.get("question") or "")
    api_url = _normalize_api_url_or_flow_id(metadata_route.get("api_url") or metadata_route.get("target_api_url"))
    if not api_url:
        api_url = _resolve_subflow_api_url(selected_flow, flow_id_override=metadata_route.get("flow_id"))
    flow_id_env = _flow_id_env(selected_flow)
    api_url_env = _flow_api_url_env(selected_flow)
    input_type = os.getenv("LANGFLOW_SUBFLOW_INPUT_TYPE") or os.getenv("LANGFLOW_INPUT_TYPE") or "chat"
    output_type = os.getenv("LANGFLOW_SUBFLOW_OUTPUT_TYPE") or os.getenv("LANGFLOW_OUTPUT_TYPE") or "chat"

    return {
        "status": "ok",
        "response_type": "route_decision",
        "request": {"question": question, "session_id": session_id},
        "route": route,
        "selected_flow": selected_flow,
        "api_url": api_url,
        "api_url_env": api_url_env,
        "flow_id_env": flow_id_env,
        "subflow_call": {
            "selected_flow": selected_flow,
            "api_url": api_url,
            "api_url_env": api_url_env,
            "flow_id_env": flow_id_env,
            "prompt": question,
            "input_value": question,
            "input_type": input_type,
            "output_type": output_type,
            "session_id": session_id,
        },
        "route_confidence": metadata_route.get("route_confidence") or metadata_route.get("confidence") or "low",
        "route_source": metadata_route.get("route_source", ""),
        "route_llm_used": bool(metadata_route.get("route_llm_used")),
        "metadata_action": metadata_route.get("metadata_action", ""),
        "target_dataset": metadata_route.get("target_dataset", ""),
        "target_family": metadata_route.get("target_family", ""),
        "reason": metadata_route.get("reason", ""),
        "warnings": list(payload.get("warnings", [])) if isinstance(payload.get("warnings"), list) else [],
        "errors": list(payload.get("errors", [])) if isinstance(payload.get("errors"), list) else [],
    }


def _resolve_session_id(request: dict[str, Any], state: dict[str, Any]) -> str:
    return _session_id_from_mapping(request) or _session_id_from_mapping(state) or "demo-session"


def _session_id_from_mapping(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    nested_request = value.get("request") if isinstance(value.get("request"), dict) else {}
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(nested_request.get(key) or "").strip()
        if text:
            return text
    context = value.get("context") if isinstance(value.get("context"), dict) else {}
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(context.get(key) or "").strip()
        if text:
            return text
    return ""


def _flow_id_env(selected_flow: str) -> str:
    return FLOW_ID_ENV.get(selected_flow, "LANGFLOW_DATA_ANALYSIS_FLOW_ID")


def _flow_api_url_env(selected_flow: str) -> str:
    return FLOW_API_URL_ENV.get(selected_flow, "LANGFLOW_DATA_ANALYSIS_API_URL")


def _resolve_subflow_api_url(selected_flow: str, flow_id_override: Any = "") -> str:
    explicit = str(os.getenv(_flow_api_url_env(selected_flow)) or "").strip()
    base_url = str(os.getenv("LANGFLOW_BASE_URL") or os.getenv("LANGFLOW_API_BASE_URL") or "").strip()
    if explicit:
        if _is_http_url(explicit):
            return explicit
        if base_url:
            return _flow_run_url(base_url, explicit)
        return ""
    flow_id = str(flow_id_override or os.getenv(_flow_id_env(selected_flow)) or "").strip()
    if base_url and flow_id:
        return _flow_run_url(base_url, flow_id)
    return ""


def _normalize_api_url_or_flow_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null", "n/a", "na"}:
        return ""
    if text.startswith("<") and text.endswith(">"):
        return ""
    if _is_http_url(text):
        return text
    base_url = str(os.getenv("LANGFLOW_BASE_URL") or os.getenv("LANGFLOW_API_BASE_URL") or "").strip()
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


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 05 Orchestrator Response Builder
# Langflow 표시 설명: 확정된 route를 selected subflow 이름과 Langflow API 호출 정보로 변환합니다.
class OrchestratorResponseBuilder(Component):

    display_name = "05 Orchestrator Response Builder"
    description = "확정된 route를 selected subflow 이름과 Langflow API 호출 정보로 변환합니다."
    icon = "Workflow"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="route_response", display_name="Route Response", method="build_route_response")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 확정된 route를 selected subflow 이름과 Langflow API 호출 정보로 변환합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_route_response(self) -> Data:
        result = build_orchestrator_response(getattr(self, "payload", None))
        self.status = {
            "route": result.get("route"),

            "selected_flow": result.get("selected_flow"),
            "flow_id_env": result.get("flow_id_env"),
        }
        return Data(data=result)
