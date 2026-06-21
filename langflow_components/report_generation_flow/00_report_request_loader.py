from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


def build_report_request(question: str, session_id: str = "", state: Any = None, router_payload: Any = None) -> dict[str, Any]:
    router_data = _route_payload(router_payload)
    flow_inputs = _dict_value(router_data.get("flow_inputs"))
    state_data = _dict_value(state) or _dict_value(flow_inputs.get("state")) or _dict_value(router_data.get("state"))
    resolved_session_id = _resolve_session_id(session_id, state_data, router_data, question)
    resolved_question = _resolve_question(question, router_data, flow_inputs)
    return {
        "payload_version": "agent-v1",
        "status": "ok",
        "flow_type": "report_generation",
        "request": {"question": resolved_question, "session_id": resolved_session_id},
        "state": state_data,
        "router_payload": router_data,
        "report": {"status": "drafting", "sections": []},
        "warnings": [],
        "errors": [],
    }


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _route_payload(value: Any) -> dict[str, Any]:
    payload = _dict_value(value)
    route_response = payload.get("route_response") if isinstance(payload.get("route_response"), dict) else {}
    if route_response and not isinstance(payload.get("flow_inputs"), dict):
        return deepcopy(route_response)
    return payload


def _resolve_question(question: Any, router_payload: dict[str, Any], flow_inputs: dict[str, Any]) -> str:
    explicit = _text_value(question).strip()
    if explicit:
        return explicit
    for source in (flow_inputs, router_payload, _dict_value(router_payload.get("request"))):
        text = str(source.get("question") or "").strip()
        if text:
            return text
    return ""


def _resolve_session_id(session_id: Any, state: dict[str, Any], router_payload: dict[str, Any], question: Any = None) -> str:
    explicit = str(session_id or "").strip()
    if explicit:
        return explicit
    return (
        _session_id_from_value(question)
        or _session_id_from_mapping(router_payload.get("flow_inputs") if isinstance(router_payload.get("flow_inputs"), dict) else {})
        or _session_id_from_mapping(router_payload)
        or _session_id_from_mapping(state)
        or "demo-session"
    )


def _session_id_from_mapping(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    request = value.get("request") if isinstance(value.get("request"), dict) else {}
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(request.get(key) or "").strip()
        if text:
            return text
    context = value.get("context") if isinstance(value.get("context"), dict) else {}
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(context.get(key) or "").strip()
        if text:
            return text
    return ""


def _session_id_from_value(value: Any) -> str:
    for attr in ("session_id", "conversation_id", "chat_id"):
        text = str(getattr(value, attr, "") or "").strip()
        if text:
            return text
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return _session_id_from_mapping(data)
    return ""


def _text_value(value: Any) -> str:
    for attr in ("text", "content"):
        text = getattr(value, attr, None)
        if isinstance(text, str):
            return text
    get_text = getattr(value, "get_text", None)
    if callable(get_text):
        try:
            text = get_text()
            if isinstance(text, str):
                return text
        except Exception:
            pass
    if isinstance(value, str):
        return value
    return str(value or "")


class ReportRequestLoader(Component):
    display_name = "00 Report Request Loader"
    description = "Builds the report-generation flow payload from the routed user request."
    icon = "FileText"
    inputs = [
        MessageTextInput(name="question", display_name="Question", required=False),
        MessageTextInput(name="session_id", display_name="Session ID", value="", advanced=True),
        DataInput(name="state", display_name="Previous State", required=False),
        DataInput(name="router_payload", display_name="Router Payload", required=False),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(
            data=build_report_request(
                getattr(self, "question", ""),
                getattr(self, "session_id", ""),
                getattr(self, "state", None),
                getattr(self, "router_payload", None),
            )
        )
