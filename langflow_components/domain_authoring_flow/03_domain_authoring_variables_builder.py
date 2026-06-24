# 파일 설명: 03 Domain Authoring Variables Builder Langflow custom component 파일입니다.
# 흐름 역할: Domain Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: Domain Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_domain_authoring_prompt_variables(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    metadata_context = payload.get("metadata_context") if isinstance(payload.get("metadata_context"), dict) else {}
    existing_summary = [
        {
            "section": item.get("section"),
            "key": item.get("key"),
            "aliases": item.get("aliases", [])[:8],
            "processes": item.get("processes", [])[:8],
            "columns": item.get("columns", [])[:8],
        }
        for item in payload.get("existing_items", [])[:80]
        if isinstance(item, dict)
    ]
    table_catalog_summary = [
        {
            "dataset_key": item.get("dataset_key"),
            "dataset_family": item.get("dataset_family"),
            "aliases": item.get("aliases", [])[:8],
            "description": item.get("description"),
            "primary_quantity_column": item.get("primary_quantity_column"),
            "columns": item.get("columns", [])[:24],
            "filter_mappings": item.get("filter_mappings", {}),
            "standard_column_aliases": item.get("standard_column_aliases", {}),
        }
        for item in metadata_context.get("table_catalog", [])[:80]
        if isinstance(item, dict)
    ]
    main_filter_summary = [
        {
            "filter_key": item.get("filter_key"),
            "aliases": item.get("aliases", [])[:8],
            "column_candidates": item.get("column_candidates", [])[:12],
            "semantic_role": item.get("semantic_role"),
            "description": item.get("description"),
        }
        for item in metadata_context.get("main_flow_filters", [])[:80]
        if isinstance(item, dict)
    ]
    return {
        "prompt_type": "domain_authoring_json",
        "payload": payload,
        "authoring_context": "\n".join(
            [
                "Existing domain item summary for duplicate awareness:",
                "Use this summary only to choose an existing key or detect duplicates. Do not create items from this summary unless the refined text explicitly asks for them.",
                json.dumps(existing_summary, ensure_ascii=False, indent=2),
                "",
                "Table catalog summary for source-family inference:",
                "Use this to infer dataset_family, source columns, and table wording from the worker text. Do not require dataset_key for reusable domain rules when dataset_family/source_columns are enough.",
                json.dumps(table_catalog_summary, ensure_ascii=False, indent=2),
                "",
                "Main flow filter summary for standard field inference:",
                "Use this to map business words and physical columns to standard field keys. Do not create main_flow_filter items in this domain flow.",
                json.dumps(main_filter_summary, ensure_ascii=False, indent=2),
                "",
                "Refined text:",
                str(payload.get("refined_text") or payload.get("raw_text") or ""),
            ]
        ),
    }


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


def _metadata_context_counts(payload_value: Any) -> dict[str, int]:
    payload = _payload(payload_value)
    metadata_context = payload.get("metadata_context") if isinstance(payload.get("metadata_context"), dict) else {}

    def _count(key: str) -> int:
        value = metadata_context.get(key)
        return len(value) if isinstance(value, list) else 0

    existing_items = payload.get("existing_items")
    return {
        "existing_items": len(existing_items) if isinstance(existing_items, list) else 0,
        "table_catalog": _count("table_catalog"),
        "main_flow_filters": _count("main_flow_filters"),
    }


# 컴포넌트 설명: 03 Domain Authoring Variables Builder
# Langflow 표시 설명: Domain Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다.
class DomainAuthoringVariablesBuilder(Component):

    display_name = "03 Domain Authoring Variables Builder"
    description = "Domain Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="authoring_context", display_name="Authoring Context", method="build_authoring_context"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: Domain Authoring Prompt Template에 넣을 authoring_context 변수를 준비합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_authoring_context(self) -> Message:
        payload_value = getattr(self, "payload", None)
        variables = build_domain_authoring_prompt_variables(payload_value)
        counts = _metadata_context_counts(payload_value)
        self.status = {
            "prompt_type": variables["prompt_type"],
            "authoring_context_chars": len(variables["authoring_context"]),
            "loaded_existing_items": counts["existing_items"],
            "loaded_table_catalog": counts["table_catalog"],
            "loaded_main_flow_filters": counts["main_flow_filters"],
        }

        return Message(text=variables["authoring_context"])
