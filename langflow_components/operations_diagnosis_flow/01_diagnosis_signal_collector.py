# 파일 설명: 01 Diagnosis Signal Collector Langflow custom component 파일입니다.
# 흐름 역할: 질문과 이전 결과 state에서 진단에 사용할 가벼운 운영 신호를 수집합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


SIGNAL_TERMS = {
    "wip_accumulation": ["재공", "wip", "쌓", "증가"],
    "production_drop": ["생산", "실적", "감소", "drop", "저하"],
    "equipment_issue": ["장비", "eqp", "설비", "고장", "down"],
    "target_gap": ["목표", "달성", "미달", "gap"],
    "hold_lot": ["hold", "홀드", "대기"],
}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 질문과 이전 결과 state에서 진단에 사용할 가벼운 운영 신호를 수집합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def collect_diagnosis_signals(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    question = str((payload.get("request") or {}).get("question") or "")
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    signals = []
    lower = question.lower()
    for signal, terms in SIGNAL_TERMS.items():
        if any(term.lower() in lower for term in terms):
            signals.append({"signal": signal, "source": "question", "confidence": "medium"})
    if current_data:
        signals.append(
            {
                "signal": "previous_result_available",
                "source": "state.current_data",
                "confidence": "high",
                "row_count": int(current_data.get("row_count") or 0),
                "columns": list(current_data.get("columns", [])) if isinstance(current_data.get("columns"), list) else [],
            }
        )

    diagnosis = deepcopy(payload.get("diagnosis")) if isinstance(payload.get("diagnosis"), dict) else {}
    diagnosis.update({"status": "signals_ready", "signals": signals})
    result = deepcopy(payload)
    result["diagnosis"] = diagnosis
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 01 Diagnosis Signal Collector
# Langflow 표시 설명: 질문과 이전 결과 state에서 진단에 사용할 가벼운 운영 신호를 수집합니다.
class DiagnosisSignalCollector(Component):

    display_name = "01 Diagnosis Signal Collector"
    description = "질문과 이전 결과 state에서 진단에 사용할 가벼운 운영 신호를 수집합니다."
    icon = "Radar"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 질문과 이전 결과 state에서 진단에 사용할 가벼운 운영 신호를 수집합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = collect_diagnosis_signals(getattr(self, "payload", None))
        self.status = {"signals": len((result.get("diagnosis") or {}).get("signals", []))}
        return Data(data=result)
