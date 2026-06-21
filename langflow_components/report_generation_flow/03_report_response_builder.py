# 파일 설명: 03 Report Response Builder Langflow custom component 파일입니다.
# 흐름 역할: 리포트 생성 결과 payload와 Playground용 메시지를 함께 구성합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 리포트 생성 결과 payload와 Playground용 메시지를 함께 구성합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
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


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 리포트 생성 결과 payload와 Playground용 메시지를 함께 구성합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
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
        lines.append("- 이 E2E 리포트 요청을 완성하려면 flow 내부에서 필요한 데이터 확보/분석 단계를 이어 연결해야 합니다.")
    return "\n".join(lines)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 03 Report Response Builder
# Langflow 표시 설명: 리포트 생성 결과 payload와 Playground용 메시지를 함께 구성합니다.
class ReportResponseBuilder(Component):

    display_name = "03 Report Response Builder"
    description = "리포트 생성 결과 payload와 Playground용 메시지를 함께 구성합니다."
    icon = "FileCheck"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="api_response", display_name="API Response", method="build_api_response"),
        Output(name="message", display_name="Message", method="build_message"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 리포트 생성 결과 payload와 Playground용 메시지를 함께 구성합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_api_response(self) -> Data:
        result = build_report_response(getattr(self, "payload", None))
        self.status = {"response_type": result.get("response_type"), "report_status": (result.get("report") or {}).get("status")}
        return Data(data=result)

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 리포트 생성 결과 payload와 Playground용 메시지를 함께 구성합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_message(self) -> Message:

        return Message(text=build_report_message(build_report_response(getattr(self, "payload", None))))
