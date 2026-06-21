from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


DEFAULT_SECTIONS = ["요약", "주요 지표", "상세 근거", "권장 조치"]


def build_report_outline(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    question = str((payload.get("request") or {}).get("question") or "")
    sections = _requested_sections(question) or DEFAULT_SECTIONS
    report = deepcopy(payload.get("report")) if isinstance(payload.get("report"), dict) else {}
    report.update(
        {
            "status": "outline_ready",
            "title": _title(question),
            "sections": [{"title": section, "content": ""} for section in sections],
            "format": _format(question),
        }
    )
    result = deepcopy(payload)
    result["report"] = report
    return result


def _requested_sections(question: str) -> list[str]:
    match = re.search(r"(?:section|섹션|목차)\s*[:：]\s*(.+)", question, flags=re.IGNORECASE)
    if not match:
        return []
    parts = [part.strip(" ,/|") for part in re.split(r"[,/|]", match.group(1)) if part.strip(" ,/|")]
    return parts[:8]


def _title(question: str) -> str:
    if "주간" in question:
        return "주간 운영 리포트"
    if "일일" in question or "오늘" in question:
        return "일일 운영 리포트"
    return "운영 분석 리포트"


def _format(question: str) -> str:
    lower = question.lower()
    if "ppt" in lower or "presentation" in lower or "슬라이드" in question:
        return "slide"
    if "excel" in lower or "xlsx" in lower or "엑셀" in question:
        return "spreadsheet"
    return "markdown"


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class ReportOutlineBuilder(Component):
    display_name = "01 Report Outline Builder"
    description = "Creates a report title, target format, and section outline."
    icon = "ListTree"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = build_report_outline(getattr(self, "payload", None))
        self.status = result.get("report", {})
        return Data(data=result)
