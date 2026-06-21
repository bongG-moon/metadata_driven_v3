from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


RECOMMENDATIONS = {
    "wip_accumulation": "공정별 WIP와 생산 실적을 같이 조회해 병목 공정을 먼저 확인합니다.",
    "production_drop": "목표 대비 생산량, 장비 가동 상태, hold lot을 같은 기준일로 비교합니다.",
    "equipment_issue": "장비 현황 detail과 EQPID 기준 장비 대수, down/hold 상태를 분리해서 확인합니다.",
    "target_gap": "목표값, 생산량, 달성률을 같은 grain으로 맞춘 뒤 미달 항목을 우선순위화합니다.",
    "hold_lot": "hold lot 사유와 대기 시간, 해당 lot의 현재 공정 위치를 같이 확인합니다.",
    "previous_result_available": "이전 분석 결과를 조건으로 삼아 필요한 추가 source만 조회합니다.",
}


def evaluate_diagnosis_rules(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    diagnosis = deepcopy(payload.get("diagnosis")) if isinstance(payload.get("diagnosis"), dict) else {}
    signals = [item for item in diagnosis.get("signals", []) if isinstance(item, dict)] if isinstance(diagnosis.get("signals"), list) else []
    findings = []
    for item in signals:
        signal = str(item.get("signal") or "")
        if signal in RECOMMENDATIONS:
            findings.append(
                {
                    "signal": signal,
                    "severity": _severity(signal),
                    "recommendation": RECOMMENDATIONS[signal],
                    "source": item.get("source", ""),
                }
            )
    if not findings:
        findings.append(
            {
                "signal": "needs_more_context",
                "severity": "info",
                "recommendation": "진단하려는 공정, 제품, 기간, 지표 중 최소 하나를 지정하면 적절한 data_analysis_flow 조회로 이어갈 수 있습니다.",
                "source": "fallback",
            }
        )
    diagnosis.update({"status": "evaluated", "findings": findings})
    result = deepcopy(payload)
    result["diagnosis"] = diagnosis
    return result


def _severity(signal: str) -> str:
    if signal in {"production_drop", "equipment_issue", "target_gap"}:
        return "warning"
    return "info"


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class DiagnosisRuleEvaluator(Component):
    display_name = "02 Diagnosis Rule Evaluator"
    description = "Turns collected operational signals into diagnosis findings and recommended next checks."
    icon = "Stethoscope"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = evaluate_diagnosis_rules(getattr(self, "payload", None))
        self.status = {"findings": len((result.get("diagnosis") or {}).get("findings", []))}
        return Data(data=result)
