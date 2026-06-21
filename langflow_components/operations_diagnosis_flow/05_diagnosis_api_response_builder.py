# 파일 설명: 05 Diagnosis API Response Builder Langflow custom component 파일입니다.
# 흐름 역할: 운영 진단 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 운영 진단 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_diagnosis_api_response(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    data = _as_dict(payload.get("data"))
    diagnosis = _as_dict(payload.get("diagnosis"))
    errors = _as_list(payload.get("errors"))
    status = str(payload.get("status") or ("error" if errors else "ok"))
    answer_message = _first_text(payload, ["answer_message", "message", "response", "answer", "text", "content"])
    api_response = {
        "status": status,
        "success": status.lower() not in {"error", "failed", "failure"} and not errors,
        "response_type": str(payload.get("response_type") or "operations_diagnosis"),
        "direct_response_ready": bool(payload.get("direct_response_ready", True)),
        "message": answer_message,
        "response": answer_message,
        "answer_message": answer_message,
        "data": data,
        "columns": list(data.get("columns", [])) if isinstance(data.get("columns"), list) else [],
        "row_count": int(data.get("row_count") or 0),
        "diagnosis": diagnosis,
        "state": _as_dict(payload.get("state")),
        "warnings": _as_list(payload.get("warnings")),
        "errors": errors,
    }
    return {"api_response": api_response}


def _make_data(payload: dict[str, Any]) -> Any:
    try:
        return Data(data=payload)
    except TypeError:
        return Data(payload)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple, set)) else []


def _first_text(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# 컴포넌트 설명: 05 Diagnosis API Response Builder
# Langflow 표시 설명: 운영 진단 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
class DiagnosisApiResponseBuilder(Component):

    display_name = "05 Diagnosis API Response Builder"
    description = "운영 진단 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다."
    icon = "Braces"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="api_response", display_name="API Response", method="build_api_response_output", types=["Data"])]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 운영 진단 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_api_response_output(self) -> Data:
        payload = build_diagnosis_api_response(getattr(self, "payload", None))
        api_response = _as_dict(payload.get("api_response"))
        self.status = {

            "status": api_response.get("status"),
            "row_count": api_response.get("row_count", 0),
        }
        return _make_data(payload)
