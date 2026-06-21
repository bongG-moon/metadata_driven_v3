# 파일 설명: 03 Diagnosis Response Builder Langflow custom component 파일입니다.
# 흐름 역할: 운영 진단 결과 payload를 구성하고 다음 adapter/API 노드가 재사용할 수 있게 정리합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 운영 진단 결과 payload를 구성하고 다음 adapter/API 노드가 재사용할 수 있게 정리합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_diagnosis_response(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    diagnosis = deepcopy(payload.get("diagnosis")) if isinstance(payload.get("diagnosis"), dict) else {}
    findings = [item for item in diagnosis.get("findings", []) if isinstance(item, dict)] if isinstance(diagnosis.get("findings"), list) else []
    answer = _message(findings)
    return {
        **payload,
        "status": "ok",
        "response_type": "operations_diagnosis",
        "direct_response_ready": True,
        "answer_message": answer,
        "diagnosis": {**diagnosis, "status": "ready"},
        "data": {
            "columns": ["signal", "severity", "recommendation"],
            "rows": [
                {
                    "signal": item.get("signal", ""),
                    "severity": item.get("severity", ""),
                    "recommendation": item.get("recommendation", ""),
                }
                for item in findings
            ],
            "row_count": len(findings),
        },
    }


def _message(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "운영 진단에 사용할 신호가 아직 충분하지 않습니다. 공정, 제품, 기간, 지표 중 하나를 더 지정하면 진단 범위를 좁힐 수 있습니다."
    warning_count = sum(1 for item in findings if str(item.get("severity") or "").lower() == "warning")
    if warning_count:
        return f"운영 진단 관점에서 우선 확인이 필요한 경고 신호 {warning_count}건을 포함해 총 {len(findings)}건의 진단 신호를 찾았습니다."
    return f"운영 진단 관점에서 참고할 수 있는 진단 신호 {len(findings)}건을 찾았습니다."


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 03 Diagnosis Response Builder
# Langflow 표시 설명: 운영 진단 결과 payload를 구성하고 다음 adapter/API 노드가 재사용할 수 있게 정리합니다.
class DiagnosisResponseBuilder(Component):

    display_name = "03 Diagnosis Response Builder"
    description = "운영 진단 결과 payload를 구성하고 다음 adapter/API 노드가 재사용할 수 있게 정리합니다."
    icon = "ClipboardCheck"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 운영 진단 결과 payload를 구성하고 다음 adapter/API 노드가 재사용할 수 있게 정리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = build_diagnosis_response(getattr(self, "payload", None))
        self.status = {"response_type": result.get("response_type"), "findings": (result.get("data") or {}).get("row_count", 0)}
        return Data(data=result)
