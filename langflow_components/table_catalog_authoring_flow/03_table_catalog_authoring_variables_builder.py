# 파일 설명: 03 Table Catalog Authoring Variables Builder Langflow custom component 파일입니다.
# 흐름 역할: Table Catalog Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: Table Catalog Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_table_catalog_authoring_prompt_variables(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    existing_summary = [
        {
            "dataset_key": item.get("dataset_key"),
            "display_name": item.get("display_name"),
            "dataset_family": item.get("dataset_family"),
            "date_scope": item.get("date_scope"),
            "source_type": item.get("source_type"),
            "columns": item.get("columns", [])[:12],
        }
        for item in payload.get("existing_items", [])[:80]
        if isinstance(item, dict)
    ]
    return {
        "prompt_type": "table_catalog_authoring_json",
        "payload": payload,
        "authoring_context": "\n".join(
            [
                "Existing dataset summary for duplicate awareness:",
                json.dumps(existing_summary, ensure_ascii=False, indent=2),
                "",
                "Original user text:",
                str(payload.get("raw_text") or ""),
                "",
                "Refined text:",
                str(payload.get("refined_text") or ""),
            ]
        ),
    }


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 03 Table Catalog Authoring Variables Builder
# Langflow 표시 설명: Table Catalog Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다.
class TableCatalogAuthoringVariablesBuilder(Component):

    display_name = "03 Table Catalog Authoring Variables Builder"
    description = "Table Catalog Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="authoring_context", display_name="Authoring Context", method="build_authoring_context"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: Table Catalog Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_authoring_context(self) -> Message:
        variables = build_table_catalog_authoring_prompt_variables(getattr(self, "payload", None))
        self.status = {"prompt_type": variables["prompt_type"], "authoring_context_chars": len(variables["authoring_context"])}

        return Message(text=variables["authoring_context"])
