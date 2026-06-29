# 파일 설명: 06 Table Catalog Review Variables Builder Langflow custom component 파일입니다.
# 흐름 역할: Table Catalog Review Prompt Template에 넣을 review_input_json 변수를 준비합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: Table Catalog Review Prompt Template에 넣을 review_input_json 변수를 준비합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_table_catalog_review_prompt_variables(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    review_input = {
        "items": payload.get("items", []),
        "missing_information": _unresolved_missing_information((payload.get("authoring") or {}).get("missing_information", []), payload),
        "normalizer_errors": payload.get("errors", []),
        "existing_matches": payload.get("existing_matches", []),
        "conflict_warnings": payload.get("conflict_warnings", []),
        "duplicate_decision": payload.get("duplicate_decision", {}),
    }
    return {
        "prompt_type": "table_catalog_save_review",
        "payload": payload,
        "review_input_json": json.dumps(review_input, ensure_ascii=False, indent=2),
    }


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


def _unresolved_missing_information(items: Any, payload: dict[str, Any]) -> list[Any]:
    result = []
    for item in items if isinstance(items, list) else []:
        field = _missing_field(item).lower()
        if field in {"dataset_key", "key"} and _has_dataset_key(payload):
            continue
        result.append(item)
    return result


def _missing_field(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("field") or "").strip()
    text = str(item or "").strip()
    return text.split(":", 1)[0].strip() if ":" in text else text


def _has_dataset_key(payload: dict[str, Any]) -> bool:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return any(
        isinstance(item, dict) and bool(str(item.get("dataset_key") or item.get("key") or "").strip())
        for item in items
    )


# 컴포넌트 설명: 06 Table Catalog Review Variables Builder
# Langflow 표시 설명: Table Catalog Review Prompt Template에 넣을 review_input_json 변수를 준비합니다.
class TableCatalogReviewVariablesBuilder(Component):

    display_name = "06 Table Catalog Review Variables Builder"
    description = "Table Catalog Review Prompt Template에 넣을 review_input_json 변수를 준비합니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="review_input_json", display_name="Review Input JSON", method="build_review_input_json"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: Table Catalog Review Prompt Template에 넣을 review_input_json 변수를 준비합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_review_input_json(self) -> Message:
        variables = build_table_catalog_review_prompt_variables(getattr(self, "payload", None))
        self.status = {"prompt_type": variables["prompt_type"], "review_input_chars": len(variables["review_input_json"])}

        return Message(text=variables["review_input_json"])
