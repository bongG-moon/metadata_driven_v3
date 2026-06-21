from __future__ import annotations

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


def build_orchestrator_response(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    metadata_route = payload.get("metadata_route") if isinstance(payload.get("metadata_route"), dict) else {}
    route = str(metadata_route.get("route") or "data_analysis").strip()
    selected_flow = FLOW_BY_ROUTE.get(route, "data_analysis_flow")
    session_id = _resolve_session_id(request, state)

    return {
        "status": "ok",
        "response_type": "route_decision",
        "request": {"question": str(request.get("question") or ""), "session_id": session_id},
        "route": route,
        "selected_flow": selected_flow,
        "flow_id_env": _flow_id_env(selected_flow),
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
    return {
        "metadata_qa_flow": "LANGFLOW_METADATA_QA_FLOW_ID",
        "data_analysis_flow": "LANGFLOW_DATA_ANALYSIS_FLOW_ID",
        "report_generation_flow": "LANGFLOW_REPORT_GENERATION_FLOW_ID",
        "operations_diagnosis_flow": "LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID",
    }.get(selected_flow, "LANGFLOW_DATA_ANALYSIS_FLOW_ID")


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class OrchestratorResponseBuilder(Component):
    display_name = "05 Orchestrator Response Builder"
    description = "Converts the router decision into the selected subflow name."
    icon = "Workflow"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="route_response", display_name="Route Response", method="build_route_response")]

    def build_route_response(self) -> Data:
        result = build_orchestrator_response(getattr(self, "payload", None))
        self.status = {
            "route": result.get("route"),
            "selected_flow": result.get("selected_flow"),
            "flow_id_env": result.get("flow_id_env"),
        }
        return Data(data=result)
