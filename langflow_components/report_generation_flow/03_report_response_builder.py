from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_report_response(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    report = deepcopy(payload.get("report")) if isinstance(payload.get("report"), dict) else {}
    sections = report.get("sections") if isinstance(report.get("sections"), list) else []
    data_selection = report.get("data_selection") if isinstance(report.get("data_selection"), dict) else {}
    answer = _message(report, data_selection)
    return {
        **payload,
        "status": "ok",
        "response_type": "report_generation",
        "direct_response_ready": True,
        "answer_message": answer,
        "report": {**report, "status": "ready"},
        "data": {
            "columns": ["section", "status"],
            "rows": [{"section": item.get("title", ""), "status": "planned"} for item in sections if isinstance(item, dict)],
            "row_count": len(sections),
        },
    }


def build_report_message(payload_value: Any) -> str:
    payload = _payload(payload_value)
    return str(payload.get("answer_message") or json.dumps(payload, ensure_ascii=False, default=str))


def _message(report: dict[str, Any], data_selection: dict[str, Any]) -> str:
    title = str(report.get("title") or "운영 분석 리포트")
    fmt = str(report.get("format") or "markdown")
    row_count = int(data_selection.get("row_count") or 0)
    sections = [str(item.get("title") or "") for item in report.get("sections", []) if isinstance(item, dict)]
    lines = [f"{title} 초안을 생성할 준비가 되었습니다.", f"- 출력 형식: {fmt}", f"- 사용할 수 있는 이전 결과 row 수: {row_count}"]
    if sections:
        lines.append("- 섹션: " + ", ".join(sections))
    if row_count == 0:
        lines.append("- 필요한 데이터가 없으면 먼저 data_analysis_flow를 실행해 결과를 만든 뒤 리포트 flow를 다시 호출합니다.")
    return "\n".join(lines)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class ReportResponseBuilder(Component):
    display_name = "03 Report Response Builder"
    description = "Builds a report-generation response payload and playground message."
    icon = "FileCheck"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="api_response", display_name="API Response", method="build_api_response"),
        Output(name="message", display_name="Message", method="build_message"),
    ]

    def build_api_response(self) -> Data:
        result = build_report_response(getattr(self, "payload", None))
        self.status = {"response_type": result.get("response_type"), "report_status": (result.get("report") or {}).get("status")}
        return Data(data=result)

    def build_message(self) -> Message:
        return Message(text=build_report_message(build_report_response(getattr(self, "payload", None))))
