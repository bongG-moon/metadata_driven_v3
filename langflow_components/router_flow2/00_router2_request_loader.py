# 파일 설명: 00 Router2 Request Loader Langflow custom component 파일입니다.
# 흐름 역할: Smart Router 기반 router_flow2가 사용할 사용자 질문 payload를 만듭니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output
from lfx.schema.data import Data


def build_router2_request_payload(question: Any, session_id: str = "", state: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_session_id = _clean(session_id) or _session_id_from_value(question) or _session_id_from_mapping(state or {}) or "demo-session"
    return {
        "payload_version": "agent-v1",
        "status": "ok",
        "router_mode": "smart_router",
        "request": {
            "question": _text_value(question),
            "session_id": resolved_session_id,
            "timezone": "Asia/Seoul",
        },
        "state": _compact_state(state),
        "info": [],
        "warnings": [],
        "errors": [],
    }


def _compact_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {"chat_history": [], "context": {}, "current_data": {}, "followup_source_results": []}
    result = deepcopy(state)
    result["chat_history"] = result.get("chat_history") if isinstance(result.get("chat_history"), list) else []
    result["context"] = result.get("context") if isinstance(result.get("context"), dict) else {}
    result["current_data"] = result.get("current_data") if isinstance(result.get("current_data"), dict) else {}
    result["followup_source_results"] = result.get("followup_source_results") if isinstance(result.get("followup_source_results"), list) else []
    return result


def _session_id_from_value(value: Any) -> str:
    for attr in ("session_id", "conversation_id", "chat_id"):
        text = _clean(getattr(value, attr, ""))
        if text:
            return text
    data = getattr(value, "data", None)
    return _session_id_from_mapping(data) if isinstance(data, dict) else ""


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


def _clean(value: Any) -> str:
    return str(value or "").strip()


class Router2RequestLoader(Component):

    display_name = "00 Router2 Request Loader"
    description = "Smart Router 기반 router_flow2가 사용할 사용자 질문 payload를 만듭니다."
    icon = "Route"

    inputs = [
        MessageTextInput(name="question", display_name="Question", required=True),
        MessageTextInput(name="session_id", display_name="Session ID", value="", advanced=True),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        payload = build_router2_request_payload(
            getattr(self, "question", ""),
            session_id=getattr(self, "session_id", ""),
        )
        self.status = {"session_id": payload["request"]["session_id"], "mode": "smart_router"}
        return Data(data=payload)
