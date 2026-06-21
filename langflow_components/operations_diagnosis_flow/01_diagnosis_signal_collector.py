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


class DiagnosisSignalCollector(Component):
    display_name = "01 Diagnosis Signal Collector"
    description = "Collects lightweight operational signals from the question and previous result state."
    icon = "Radar"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = collect_diagnosis_signals(getattr(self, "payload", None))
        self.status = {"signals": len((result.get("diagnosis") or {}).get("signals", []))}
        return Data(data=result)
