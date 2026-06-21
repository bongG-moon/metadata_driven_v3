# 파일 설명: Langflow API 호출을 빠르게 검증하기 위한 테스트용 custom component입니다.
# 흐름 역할: API URL과 Langflow key만 넣어도 기본 입력값으로 /api/v1/run 호출을 실행하고 결과를 확인합니다.

from __future__ import annotations

import json
import time
from typing import Any

import requests
from lfx.custom.custom_component.component import Component
from lfx.io import MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


DEFAULT_INPUT_VALUE = "테스트 호출입니다. 가능한 간단히 응답해줘."


# 함수 설명: Langflow Run API를 실제로 호출하는 핵심 테스트 함수입니다.
# 처리 역할: api_url/key/input 값을 표준 Langflow run payload로 변환하고 HTTP POST 결과를 dict로 반환합니다.
def run_langflow_api_test(
    api_url: Any,
    langflow_key: Any = "",
    input_value: Any = DEFAULT_INPUT_VALUE,
    input_type: Any = "chat",
    output_type: Any = "chat",
    session_id: Any = "",
    timeout_seconds: Any = 180,
) -> dict[str, Any]:
    resolved_url = str(api_url or "").strip()
    if not resolved_url:
        return _error_result("api_url is required.", request_payload={})

    request_payload = {
        "input_value": str(input_value or DEFAULT_INPUT_VALUE).strip() or DEFAULT_INPUT_VALUE,
        "input_type": str(input_type or "chat").strip() or "chat",
        "output_type": str(output_type or "chat").strip() or "chat",
    }
    resolved_session_id = str(session_id or "").strip()
    if resolved_session_id:
        request_payload["session_id"] = resolved_session_id

    headers = {"Content-Type": "application/json"}
    resolved_key = str(langflow_key or "").strip()
    if resolved_key:
        headers["x-api-key"] = resolved_key

    started_at = time.perf_counter()
    try:
        response = requests.post(
            resolved_url,
            json=request_payload,
            headers=headers,
            timeout=_safe_int(timeout_seconds, default=180),
        )
        elapsed_seconds = round(time.perf_counter() - started_at, 3)
        try:
            parsed_response: Any = response.json()
        except Exception:
            parsed_response = {"text": response.text}

        result = {
            "status": "ok" if response.ok else "error",
            "status_code": response.status_code,
            "elapsed_seconds": elapsed_seconds,
            "api_url": resolved_url,
            "request_payload": request_payload,
            "message": _extract_message_text(parsed_response),
            "raw_response": parsed_response,
        }
        if not response.ok:
            result["error"] = f"HTTP {response.status_code}: {response.text[:1000]}"
        return result
    except Exception as exc:
        return _error_result(
            f"Langflow API call failed: {exc}",
            request_payload=request_payload,
            api_url=resolved_url,
            elapsed_seconds=round(time.perf_counter() - started_at, 3),
        )


def _error_result(
    message: str,
    *,
    request_payload: dict[str, Any],
    api_url: str = "",
    elapsed_seconds: float = 0.0,
) -> dict[str, Any]:
    return {
        "status": "error",
        "status_code": None,
        "elapsed_seconds": elapsed_seconds,
        "api_url": api_url,
        "request_payload": request_payload,
        "message": message,
        "error": message,
        "raw_response": {},
    }


def _extract_message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value or "")

    candidates = [
        value.get("message"),
        value.get("answer_message"),
        value.get("result"),
        value.get("text"),
    ]
    api_response = value.get("api_response")
    if isinstance(api_response, dict):
        candidates.extend(
            [
                api_response.get("answer_message"),
                api_response.get("message"),
                api_response.get("result"),
            ]
        )

    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text

    outputs = value.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            text = _extract_message_text(output)
            if text:
                return text

    results = value.get("results")
    if isinstance(results, dict):
        for result_value in results.values():
            text = _extract_message_text(result_value)
            if text:
                return text

    data = value.get("data")
    if isinstance(data, dict):
        return _extract_message_text(data)
    return ""


def _safe_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except Exception:
        return default


def _message(text: str) -> Message:
    return Message(text=text)


def _data(payload: dict[str, Any]) -> Data:
    return Data(data=payload)


# 컴포넌트 설명: 00 Langflow API Test Component
# Langflow 표시 설명: API URL과 Langflow key만으로 Langflow Run API 호출을 테스트합니다.
class LangflowApiTestComponent(Component):
    display_name = "00 Langflow API Test Component"
    description = "API URL과 Langflow key만으로 Langflow Run API 호출을 테스트합니다."
    icon = "PlugZap"
    inputs = [
        MessageTextInput(name="api_url", display_name="API URL", value="", required=True),
        MessageTextInput(name="langflow_key", display_name="Langflow Key", value="", required=False),
        MessageTextInput(name="input_value", display_name="Test Input", value=DEFAULT_INPUT_VALUE, advanced=True),
        MessageTextInput(name="input_type", display_name="Input Type", value="chat", advanced=True),
        MessageTextInput(name="output_type", display_name="Output Type", value="chat", advanced=True),
        MessageTextInput(name="session_id", display_name="Session ID", value="", advanced=True),
        MessageTextInput(name="timeout_seconds", display_name="Timeout Seconds", value="180", advanced=True),
    ]
    outputs = [
        Output(name="message", display_name="Message", method="build_message"),
        Output(name="result", display_name="Result", method="build_result"),
    ]

    def _result(self) -> dict[str, Any]:
        return run_langflow_api_test(
            api_url=getattr(self, "api_url", ""),
            langflow_key=getattr(self, "langflow_key", ""),
            input_value=getattr(self, "input_value", DEFAULT_INPUT_VALUE),
            input_type=getattr(self, "input_type", "chat"),
            output_type=getattr(self, "output_type", "chat"),
            session_id=getattr(self, "session_id", ""),
            timeout_seconds=getattr(self, "timeout_seconds", 180),
        )

    # 함수 설명: Chat Output에 바로 연결할 수 있는 간단한 메시지를 만듭니다.
    def build_message(self) -> Message:
        result = self._result()
        self.status = result
        if result.get("status") == "ok":
            message = result.get("message") or json.dumps(result.get("raw_response", {}), ensure_ascii=False, indent=2)
            return _message(f"API 호출 성공\n\n{message}")
        return _message(f"API 호출 실패\n\n{result.get('error') or result.get('message')}")

    # 함수 설명: API 응답 전체를 Data로 내보내 디버깅/후속 노드에서 사용할 수 있게 합니다.
    def build_result(self) -> Data:
        result = self._result()
        self.status = result
        return _data(result)
