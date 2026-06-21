# 파일 설명: 02 Metadata QA Prompt Builder Langflow custom component 파일입니다.
# 흐름 역할: 사용자 질문에 맞는 metadata QA action과 target을 고르도록 LLM 프롬프트를 만듭니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


ALLOWED_ACTIONS = [
    "greeting",
    "help",
    "catalog_list",
    "dataset_examples",
    "dataset_detail",
    "dataset_query",
    "domain_search",
]
DOMAIN_SECTION_LABELS = {
    "process_groups": "공정 그룹",
    "product_terms": "제품/조건 용어",
    "quantity_terms": "수량/지표 용어",
    "metric_terms": "계산 지표",
    "analysis_recipes": "분석 레시피",
    "status_terms": "상태 용어",
    "product_key_columns": "제품 식별 컬럼",
}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 사용자 질문에 맞는 metadata QA action과 target을 고르도록 LLM 프롬프트를 만듭니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_metadata_qa_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "").strip()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata_route = payload.get("metadata_route") if isinstance(payload.get("metadata_route"), dict) else {}
    prompt = "\n".join(
        [
            "You are the metadata QA planner for a metadata-driven manufacturing data assistant.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Your job is to interpret the user's metadata/help/catalog question and choose how this subflow should answer.",
            "Do not retrieve live manufacturing data. Do not write SQL beyond returning registered query templates.",
            "Use only the registered metadata summary. Do not invent datasets, columns, process rules, or query templates.",
            "",
            "Allowed actions:",
            json.dumps(ALLOWED_ACTIONS, ensure_ascii=False),
            "",
            "Action meanings:",
            "- greeting: greeting or simple hello.",
            "- help: asks what the assistant can do or how to use it.",
            "- catalog_list: asks which datasets/sources are registered or available.",
            "- dataset_examples: asks what questions can be asked with a dataset/family.",
            "- dataset_detail: asks about columns, filters, date format, required params, source type, or dataset meaning.",
            "- dataset_query: asks for the registered query template/API query used to retrieve a dataset.",
            "- domain_search: asks about registered domain definitions, aliases, conditions, process/product/metric rules, or domain sections such as process_groups/공정 그룹.",
            "",
            "Important distinction:",
            "- If the user asks for actual current values, rankings, counts, production, WIP, target achievement, or analysis results, return route=data_analysis.",
            "- If the user asks what query/template/metadata/definition/example exists, return route=metadata_qa.",
            "- If the user asks section-level domain information, set target_term to the registered section key. Example: '공정 그룹 관련 도메인 정보 알려줘' -> target_term='process_groups'.",
            "",
            "Metadata structure guide:",
            "- metadata.table_catalog.datasets[dataset_key] is the registered table/source catalog. Use it for dataset lists, source type, date_scope, required_params, date_format, columns, filter_mappings, standard_column_aliases, and source_config/query_template questions.",
            "- metadata.domain_items.process_groups[GROUP_KEY] defines process group names such as DA/WB. aliases are natural-language names, and processes are the detailed OPER_NAME values included in that group.",
            "- metadata.domain_items.product_terms[TERM_KEY] defines product or business product conditions. aliases are user-facing names, condition/condition_by_family describes how to filter each dataset family.",
            "- metadata.domain_items.quantity_terms[TERM_KEY] maps business quantities such as 생산량, 재공, 목표, 장비 대수 to dataset_family or dataset_key, quantity_column, aggregation, and output_column.",
            "- metadata.domain_items.metric_terms[TERM_KEY] defines calculated metrics such as 달성률. formula, required_quantity_terms, and output_column explain how the metric is derived.",
            "- metadata.domain_items.analysis_recipes[RECIPE_KEY] defines reusable analysis patterns. aliases/question_cues indicate when the recipe applies, required_dataset_families says which data families are needed, and grain_policy explains aggregation grain.",
            "- metadata.domain_items.status_terms[TERM_KEY] defines status aliases and conditions such as HOLD or 작업대기.",
            "- metadata.domain_items.product_key_columns lists the standard product grain columns used to identify products across datasets.",
            "- metadata.main_flow_filters[FIELD_KEY] lists common field concepts and possible physical column names across sources.",
            "",
            "User-facing answer guidance:",
            "- Plan the answer as helpful guidance first, not as a raw registry/table dump.",
            "- Explain what the user can ask or do with the registered metadata in business terms.",
            "- Dataset keys, source types, columns, and query templates are reference details; they should support the answer, not become the main answer unless the user explicitly asks for them.",
            "- For catalog_list, group the explanation by business capability/family and suggest natural-language example questions.",
            "- For dataset_examples, dataset_detail, dataset_query, and domain_search, explain the meaning or use case before technical fields.",
            "- Set reference_table_role=reference_only when table rows should be shown only as supporting reference information.",
            "",
            "Available metadata summary:",
            json.dumps(_metadata_summary(metadata), ensure_ascii=False, indent=2),
            "",
            "Existing route hint, if any:",
            json.dumps(metadata_route, ensure_ascii=False, indent=2),
            "",
            "User question:",
            question,
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "route": "metadata_qa | direct_answer | data_analysis",
                    "metadata_action": "one allowed action for metadata_qa/direct_answer, empty for data_analysis",
                    "target_dataset": "registered dataset_key if the answer concerns one dataset, else empty",
                    "target_family": "registered dataset_family if useful, else empty",
                    "target_term": "domain/search term or registered domain section key such as process_groups if useful, else empty",
                    "answer_style": "descriptive_guidance | examples | dataset_detail | query_template | domain_definition | help",
                    "user_facing_focus": "short Korean sentence describing what the final answer should help the user understand",
                    "suggested_questions": ["optional natural-language follow-up question", "optional natural-language follow-up question"],
                    "reference_table_role": "reference_only | primary_answer",
                    "confidence": "high | medium | low",
                    "reason": "short Korean or English reason",
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "metadata_qa_planner"}


def _metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = table_catalog.get("datasets") if isinstance(table_catalog.get("datasets"), dict) else {}
    dataset_rows = []
    families: list[str] = []
    for key, item in sorted(datasets.items()):
        if not isinstance(item, dict):
            continue
        family = str(item.get("dataset_family") or "")
        if family and family not in families:
            families.append(family)
        dataset_rows.append(
            {
                "dataset_key": key,
                "display_name": item.get("display_name", ""),
                "dataset_family": family,
                "source_type": item.get("source_type", ""),
                "date_scope": item.get("date_scope", ""),
                "date_format": item.get("date_format", ""),
                "primary_quantity_column": item.get("primary_quantity_column", ""),
                "required_params": item.get("required_params", []),
                "required_param_mappings": _compact_mapping(item.get("required_param_mappings"), limit=12),
                "filter_mappings": _compact_mapping(item.get("filter_mappings"), limit=16),
                "standard_column_aliases": _compact_mapping(item.get("standard_column_aliases"), limit=12),
                "query_template_preview": _query_template_preview(item),
                "columns": _compact_list(item.get("columns"), limit=20),
            }
        )
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    domain_summary: dict[str, Any] = {}
    domain_sections = []
    for section, values in domain.items():
        domain_sections.append(
            {
                "section": section,
                "label": DOMAIN_SECTION_LABELS.get(str(section), str(section)),
                "sample_keys": _sample_domain_keys(values),
            }
        )
        if section == "product_key_columns":
            domain_summary[section] = _compact_list(values, limit=20)
            continue
        if not isinstance(values, dict):
            continue
        rows = []
        for key, payload in sorted(values.items())[:30]:
            if not isinstance(payload, dict):
                payload = {"value": payload}
            rows.append(
                {
                    "key": key,
                    "display_name": payload.get("display_name", ""),
                    "aliases": _compact_list(payload.get("aliases"), limit=10),
                    "processes": _compact_list(payload.get("processes"), limit=12),
                    "condition": _compact_value(payload.get("condition")),
                    "condition_by_family": _compact_value(payload.get("condition_by_family")),
                    "dataset_key": payload.get("dataset_key", ""),
                    "dataset_family": payload.get("dataset_family", ""),
                    "quantity_column": payload.get("quantity_column", ""),
                    "aggregation": payload.get("aggregation", ""),
                    "output_column": payload.get("output_column", ""),
                    "formula": payload.get("formula", ""),
                    "required_quantity_terms": _compact_list(payload.get("required_quantity_terms"), limit=10),
                    "required_dataset_families": _compact_list(payload.get("required_dataset_families"), limit=10),
                    "question_cues": _compact_list(payload.get("question_cues"), limit=10),
                    "grain_policy": payload.get("grain_policy", ""),
                }
            )
        domain_summary[section] = rows
    main_flow_filters = metadata.get("main_flow_filters") if isinstance(metadata.get("main_flow_filters"), dict) else {}
    return {
        "datasets": dataset_rows,
        "dataset_families": families,
        "domain_sections": domain_sections,
        "domain_items": domain_summary,
        "main_flow_filters": _main_flow_filter_summary(main_flow_filters),
    }


def _sample_domain_keys(values: Any) -> list[str]:
    if isinstance(values, dict):
        return [str(key) for key in list(values.keys())[:10]]
    if isinstance(values, list):
        return [str(value) for value in values[:10]]
    return []


def _main_flow_filter_summary(filters: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, payload in sorted(filters.items())[:40]:
        if not isinstance(payload, dict):
            payload = {"value": payload}
        rows.append(
            {
                "field_key": key,
                "description": payload.get("description", ""),
                "column_candidates": _compact_list(payload.get("column_candidates"), limit=12),
            }
        )
    return rows


def _query_template_preview(item: dict[str, Any]) -> str:
    source_config = item.get("source_config") if isinstance(item.get("source_config"), dict) else {}
    query = str(source_config.get("query_template") or "").strip()
    if not query:
        return ""
    return query[:500]


def _compact_mapping(value: Any, limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= limit:
            break
        result[str(key)] = item
    return result


def _compact_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _compact_list(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return deepcopy(value[:limit])


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 02 Metadata QA Prompt Builder
# Langflow 표시 설명: 사용자 질문에 맞는 metadata QA action과 target을 고르도록 LLM 프롬프트를 만듭니다.
class MetadataQAPromptBuilder(Component):

    display_name = "02 Metadata QA Prompt Builder"
    description = "사용자 질문에 맞는 metadata QA action과 target을 고르도록 LLM 프롬프트를 만듭니다."
    icon = "MessagesSquare"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="metadata_qa_prompt", display_name="Metadata QA Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 사용자 질문에 맞는 metadata QA action과 target을 고르도록 LLM 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt(self) -> Message:

        prompt_payload = build_metadata_qa_prompt_payload(getattr(self, "payload", None))
        self.status = {
            "prompt_type": prompt_payload.get("prompt_type", ""),
            "chars": len(prompt_payload.get("prompt", "")),
        }
        return Message(text=prompt_payload["prompt"])

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 사용자 질문에 맞는 metadata QA action과 target을 고르도록 LLM 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt_payload(self) -> Data:
        return Data(data=build_metadata_qa_prompt_payload(getattr(self, "payload", None)))
