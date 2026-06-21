# 파일 설명: 01 Domain Text Refinement Variables Builder Langflow custom component 파일입니다.
# 흐름 역할: Domain Text Refinement Prompt Template에 넣을 raw_text 변수를 준비합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: Domain Text Refinement Prompt Template에 넣을 raw_text 변수를 준비합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_domain_refinement_prompt_variables(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    return {
        "prompt_type": "domain_text_refinement",
        "payload": payload,
        "raw_text": str(payload.get("raw_text") or ""),
    }


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 01 Domain Text Refinement Variables Builder
# Langflow 표시 설명: Domain Text Refinement Prompt Template에 넣을 raw_text 변수를 준비합니다.
class DomainTextRefinementVariablesBuilder(Component):

    display_name = "01 Domain Text Refinement Variables Builder"
    description = "Domain Text Refinement Prompt Template에 넣을 raw_text 변수를 준비합니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="raw_text", display_name="Raw Text", method="build_raw_text"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: Domain Text Refinement Prompt Template에 넣을 raw_text 변수를 준비합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_raw_text(self) -> Message:
        variables = build_domain_refinement_prompt_variables(getattr(self, "payload", None))
        self.status = {"prompt_type": variables["prompt_type"], "raw_text_chars": len(variables["raw_text"])}

        return Message(text=variables["raw_text"])
