# 파일 설명: 00 Metadata QA Request Loader Langflow custom component 파일입니다.
# 흐름 역할: metadata QA 질문과 session/state를 compact QA request payload로 정리합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: metadata QA 질문과 session/state를 compact QA request payload로 정리합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_metadata_qa_request(
    question: str,
    session_id: str = "",
    state: Any = None,
) -> dict[str, Any]:
    state_data = _dict_value(state)
    resolved_session_id = _resolve_session_id(session_id, state_data, question)
    return {
        "payload_version": "agent-v1",
        "status": "ok",
        "request": {"session_id": resolved_session_id, "question": _text_value(question).strip(), "timezone": "Asia/Seoul"},
        "state": state_data,
        "info": [],
        "warnings": [],
        "errors": [],
    }


def _dict_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _resolve_session_id(session_id: Any, state: dict[str, Any], question: Any = None) -> str:
    explicit = str(session_id or "").strip()
    if explicit:
        return explicit
    return (
        _session_id_from_value(question)
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


# 컴포넌트 설명: 00 Metadata QA Request Loader
# Langflow 표시 설명: metadata QA 질문과 session/state를 compact QA request payload로 정리합니다.
class MetadataQARequestLoader(Component):

    display_name = "00 Metadata QA Request Loader"
    description = "metadata QA 질문과 session/state를 compact QA request payload로 정리합니다."
    icon = "SearchCheck"
    inputs = [
        MessageTextInput(name="question", display_name="Question", required=False),
        DataInput(name="state", display_name="Previous State", required=False),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: metadata QA 질문과 session/state를 compact QA request payload로 정리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:

        payload = build_metadata_qa_request(
            getattr(self, "question", ""),
            state=getattr(self, "state", None),
        )
        self.status = {
            "session_id": payload.get("request", {}).get("session_id"),
            "has_previous_state": bool(payload.get("state")),
        }
        return Data(data=payload)
