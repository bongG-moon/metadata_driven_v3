# 파일 설명: 04 Diagnosis Message Adapter Langflow custom component 파일입니다.
# 흐름 역할: 운영 진단 payload를 Chat Output에 연결하기 좋은 리포트형 Message로 변환합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message


SIGNAL_LABELS = {
    "wip_accumulation": "재공 증가 가능성",
    "production_drop": "생산 실적 저하 가능성",
    "equipment_issue": "장비/설비 이슈 가능성",
    "target_gap": "목표 대비 미달 가능성",
    "hold_lot": "HOLD/대기 LOT 영향 가능성",
    "previous_result_available": "이전 분석 결과 활용 가능",
    "needs_more_context": "진단 범위 추가 지정 필요",
}

SEVERITY_LABELS = {
    "warning": "주의",
    "info": "참고",
    "critical": "긴급",
}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 운영 진단 payload를 Chat Output에 연결하기 좋은 리포트형 Message로 변환합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_diagnosis_playground_message(payload_value: Any) -> str:
    payload = _payload(payload_value)
    diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
    findings = [item for item in diagnosis.get("findings", []) if isinstance(item, dict)] if isinstance(diagnosis.get("findings"), list) else []
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    sections: list[str] = []
    sections.append(_summary_section(findings, request, state))
    signal_section = _signal_section(findings)
    if signal_section:
        sections.append(signal_section)
    sections.append(_recommendation_section(findings))
    next_questions = _next_question_section(findings, state)
    if next_questions:
        sections.append(next_questions)
    if sections:
        return "\n\n".join(sections)
    return ""


def _summary_section(findings: list[dict[str, Any]], request: dict[str, Any], state: dict[str, Any]) -> str:
    question = str(request.get("question") or "").strip()
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    row_count = current_data.get("row_count")
    warning_count = sum(1 for item in findings if str(item.get("severity") or "").lower() == "warning")
    lines = ["### 운영 진단 리포트", "#### 요약"]
    if question:
        lines.append(f"- 요청: {question}")
    if findings:
        if warning_count:
            lines.append(f"- 판단: 주의 신호 {warning_count}건을 포함해 총 {len(findings)}건의 운영 진단 신호가 감지되었습니다.")
        else:
            lines.append(f"- 판단: 즉시 위험 신호보다는 후속 분석에 활용할 수 있는 참고 신호 {len(findings)}건이 감지되었습니다.")
    else:
        lines.append("- 판단: 현재 질문만으로는 진단 신호가 충분하지 않습니다.")
    if row_count not in (None, "", [], {}):
        lines.append(f"- 사용 가능한 이전 분석 결과: {row_count}행")
    return "\n".join(lines)


def _signal_section(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return ""
    lines = ["#### 관찰 신호"]
    for index, item in enumerate(findings[:5], start=1):
        signal = str(item.get("signal") or "")
        severity = _severity_label(item.get("severity"))
        source = str(item.get("source") or "").strip()
        source_text = f", 근거={source}" if source else ""
        lines.append(f"{index}. [{severity}] {_signal_label(signal)}{source_text}")
    return "\n".join(lines)


def _recommendation_section(findings: list[dict[str, Any]]) -> str:
    lines = ["#### 권장 확인 순서"]
    if not findings:
        lines.append("1. 진단하려는 공정, 제품, 기간, 지표 중 하나를 먼저 지정합니다.")
        lines.append("2. 필요한 데이터 분석 flow를 실행해 기준 결과를 만든 뒤, 그 결과를 기준으로 추가 진단을 이어갑니다.")
        return "\n".join(lines)
    for index, item in enumerate(findings[:5], start=1):
        recommendation = str(item.get("recommendation") or "").strip()
        if not recommendation:
            recommendation = "관련 데이터를 같은 기준으로 맞춰 추가 확인합니다."
        lines.append(f"{index}. {recommendation}")
    return "\n".join(lines)


def _next_question_section(findings: list[dict[str, Any]], state: dict[str, Any]) -> str:
    examples = _next_questions(findings, state)
    if not examples:
        return ""
    return "#### 이어서 물어볼 수 있는 질문\n" + "\n".join(f"- {example}" for example in examples[:4])


def _next_questions(findings: list[dict[str, Any]], state: dict[str, Any]) -> list[str]:
    signals = {str(item.get("signal") or "") for item in findings}
    examples: list[str] = []
    if "previous_result_available" in signals or state.get("current_data"):
        examples.append("방금 결과를 기준으로 원인 후보를 더 좁혀줘")
        examples.append("방금 결과의 제품들에 대해 장비 현황도 같이 확인해줘")
    if "wip_accumulation" in signals:
        examples.append("재공이 많이 쌓인 공정과 제품을 우선순위로 보여줘")
    if "production_drop" in signals or "target_gap" in signals:
        examples.append("목표 대비 생산 미달 제품과 부족 수량을 보여줘")
    if "equipment_issue" in signals:
        examples.append("관련 장비별 상태와 할당 대수를 확인해줘")
    if "hold_lot" in signals:
        examples.append("HOLD LOT의 사유와 대기 시간을 같이 보여줘")
    if not examples:
        examples.append("오늘 DA공정에서 생산량, 재공, 목표값을 비교해줘")
    return _unique(examples)


def _signal_label(signal: str) -> str:
    return SIGNAL_LABELS.get(signal, signal or "미분류 신호")


def _severity_label(severity: Any) -> str:
    text = str(severity or "info").lower()
    return SEVERITY_LABELS.get(text, text)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 04 Diagnosis Message Adapter
# Langflow 표시 설명: 운영 진단 payload를 Chat Output에 연결하기 좋은 리포트형 Message로 변환합니다.
class DiagnosisMessageAdapter(Component):

    display_name = "04 Diagnosis Message Adapter"
    description = "운영 진단 payload를 Chat Output에 연결하기 좋은 리포트형 Message로 변환합니다."
    icon = "MessagesSquare"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="message", display_name="Message", method="build_message")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 운영 진단 payload를 Chat Output에 연결하기 좋은 리포트형 Message로 변환합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_message(self) -> Message:
        return Message(text=build_diagnosis_playground_message(getattr(self, "payload", None)))
