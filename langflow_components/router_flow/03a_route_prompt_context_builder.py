# 파일 설명: 03A Route Prompt Context Builder Langflow custom component 파일입니다.
# 흐름 역할: 기본 Prompt Template에 넣을 route 분류 context 하나를 compact JSON 문자열로 준비합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message


DOMAIN_SECTION_LABELS = {
    "process_groups": "공정 그룹",
    "product_terms": "제품/조건 용어",
    "quantity_terms": "수량/지표 용어",
    "metric_terms": "계산 지표",
    "analysis_recipes": "분석 레시피",
    "pandas_function_cases": "pandas 함수 케이스",
    "status_terms": "상태 용어",
    "product_key_columns": "제품 식별 컬럼",
}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 기본 Prompt Template에 넣을 route 분류 context 하나를 compact JSON 문자열로 준비합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_route_prompt_context(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata_route = payload.get("metadata_route") if isinstance(payload.get("metadata_route"), dict) else {}
    question = str(request.get("question") or "")
    route_context = {
        "question": question,
        "route_llm_required": bool(metadata_route.get("route_llm_required")),
        "route_candidate": metadata_route,
        "provisional_route": _provisional_route(metadata_route),
        "metadata_summary": _metadata_summary(metadata),
    }
    return {
        "prompt_type": "route_prompt_context",
        "payload": payload,
        "route_context": route_context,
        "route_prompt_context_json": _json(route_context),
    }


def _provisional_route(metadata_route: dict[str, Any]) -> dict[str, Any]:
    action = str(metadata_route.get("metadata_action") or "")
    return {
        "route": metadata_route.get("route", "data_analysis"),
        "metadata_action": action,
        "metadata_question_type": action,
        "target_dataset": metadata_route.get("target_dataset", ""),
        "target_family": metadata_route.get("target_family", ""),
        "target_term": metadata_route.get("target_term", ""),
        "selected_flow": metadata_route.get("selected_flow", ""),
        "api_url": metadata_route.get("api_url", ""),
        "confidence": metadata_route.get("confidence", "medium"),
        "reason": metadata_route.get("reason", "The route candidate was produced by metadata-backed rules."),
    }


def _metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = table_catalog.get("datasets") if isinstance(table_catalog.get("datasets"), dict) else {}
    dataset_rows = []
    for key, item in sorted(datasets.items()):
        if not isinstance(item, dict):
            continue
        dataset_rows.append(
            {
                "dataset_key": key,
                "display_name": item.get("display_name", ""),
                "dataset_family": item.get("dataset_family", ""),
                "source_type": item.get("source_type", ""),
                "date_scope": item.get("date_scope", ""),
                "has_query_template": bool(
                    isinstance(item.get("source_config"), dict)
                    and str(item.get("source_config", {}).get("query_template") or "").strip()
                ),
            }
        )
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    return {
        "datasets": dataset_rows,
        "domain_sections": [
            {
                "section": str(section),
                "label": DOMAIN_SECTION_LABELS.get(str(section), str(section)),
                "sample_keys": _sample_domain_keys(values),
            }
            for section, values in domain.items()
        ],
        "quantity_terms": _quantity_terms(domain),
    }


def _quantity_terms(domain: dict[str, Any]) -> list[dict[str, Any]]:
    terms = domain.get("quantity_terms") if isinstance(domain.get("quantity_terms"), dict) else {}
    rows = []
    for key, item in sorted(terms.items()):
        if not isinstance(item, dict):
            continue
        aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
        rows.append(
            {
                "term_key": key,
                "aliases": aliases[:6],
                "dataset_key": item.get("dataset_key", ""),
                "dataset_family": item.get("dataset_family", ""),
                "quantity_column": item.get("quantity_column", ""),
            }
        )
    return rows


def _sample_domain_keys(values: Any) -> list[str]:
    if isinstance(values, dict):
        return [str(key) for key in list(values.keys())[:10]]
    if isinstance(values, list):
        return [str(value) for value in values[:10]]
    return []


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _message(text: Any) -> Message:
    return Message(text=str(text or ""))


# 컴포넌트 설명: 03A Route Prompt Context Builder
# Langflow 표시 설명: 기본 Prompt Template에 넣을 route 분류 context 하나를 compact JSON 문자열로 준비합니다.
class RoutePromptContextBuilder(Component):

    display_name = "03A Route Prompt Context Builder"
    description = "기본 Prompt Template에 넣을 route 분류 context 하나를 compact JSON 문자열로 준비합니다."
    icon = "Braces"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="route_prompt_context", display_name="Route Prompt Context", method="build_route_prompt_context", types=["Message"]),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 기본 Prompt Template에 넣을 route 분류 context 하나를 compact JSON 문자열로 준비합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def _context(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_context", None)

        if isinstance(cached, dict):
            return cached
        result = build_route_prompt_context(getattr(self, "payload", None))
        self._cached_context = result
        self.status = {
            "prompt_type": result.get("prompt_type"),
            "context_chars": len(result.get("route_prompt_context_json", "")),
        }
        return result

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 기본 Prompt Template에 넣을 route 분류 context 하나를 compact JSON 문자열로 준비합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_route_prompt_context(self) -> Message:
        return _message(self._context().get("route_prompt_context_json", ""))
