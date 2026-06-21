from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


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


def build_diagnosis_message(payload_value: Any) -> str:
    payload = _payload(payload_value)
    return str(payload.get("answer_message") or json.dumps(payload, ensure_ascii=False, default=str))


def _message(findings: list[dict[str, Any]]) -> str:
    lines = ["운영 진단 초안을 만들었습니다."]
    for index, item in enumerate(findings[:5], start=1):
        lines.append(f"{index}. {item.get('signal', '')}: {item.get('recommendation', '')}")
    return "\n".join(lines)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class DiagnosisResponseBuilder(Component):
    display_name = "03 Diagnosis Response Builder"
    description = "Builds an operations-diagnosis response payload and playground message."
    icon = "ClipboardCheck"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="api_response", display_name="API Response", method="build_api_response"),
        Output(name="message", display_name="Message", method="build_message"),
    ]

    def build_api_response(self) -> Data:
        result = build_diagnosis_response(getattr(self, "payload", None))
        self.status = {"response_type": result.get("response_type"), "findings": (result.get("data") or {}).get("row_count", 0)}
        return Data(data=result)

    def build_message(self) -> Message:
        return Message(text=build_diagnosis_message(build_diagnosis_response(getattr(self, "payload", None))))
