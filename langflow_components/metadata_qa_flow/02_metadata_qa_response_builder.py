from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_metadata_qa_response(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    metadata_route = payload.get("metadata_route") if isinstance(payload.get("metadata_route"), dict) else {}
    route = str(metadata_route.get("route") or "data_analysis")
    if route not in {"metadata_qa", "direct_answer"}:
        return payload

    action = str(metadata_route.get("metadata_action") or "")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    datasets = _datasets(metadata)
    if action == "catalog_list":
        answer_message, data = _catalog_list_response(datasets)
    elif action == "dataset_examples":
        answer_message, data = _dataset_examples_response(metadata_route, datasets, metadata)
    elif action == "dataset_detail":
        answer_message, data = _dataset_detail_response(metadata_route, datasets)
    elif action == "dataset_query":
        answer_message, data = _dataset_query_response(metadata_route, datasets)
    elif action == "domain_search":
        answer_message, data = _domain_search_response(metadata_route, metadata)
    elif action == "greeting":
        answer_message, data = _help_response("안녕하세요. 제조 데이터 분석과 등록된 메타데이터 조회를 도와드릴 수 있습니다.")
    else:
        answer_message, data = _help_response("사용 가능한 질문 유형을 안내드릴게요.")

    metadata_qa = {
        "handled": True,
        "route": route,
        "metadata_action": action,
        "target_dataset": metadata_route.get("target_dataset", ""),
        "target_family": metadata_route.get("target_family", ""),
        "target_term": metadata_route.get("target_term", ""),
        "confidence": metadata_route.get("confidence", ""),
        "route_source": metadata_route.get("route_source", ""),
        "route_llm_used": metadata_route.get("route_llm_used", False),
        "reason": metadata_route.get("reason", ""),
    }
    applied_scope = {
        "intent_type": "metadata_lookup" if route == "metadata_qa" else "direct_answer",
        "analysis_kind": action or "none",
        "datasets": _scope_datasets(data),
        "source_aliases": [],
        "step_ids": [],
        "filters_by_source": {},
        "params_by_source": {},
        "metadata_refs": payload.get("metadata_context", {}),
    }
    intent_plan = {
        "route": route,
        "intent_type": applied_scope["intent_type"],
        "analysis_kind": applied_scope["analysis_kind"],
        "datasets": applied_scope["datasets"],
        "source_aliases": [],
        "metadata_action": action,
        "target_dataset": metadata_qa.get("target_dataset", ""),
        "target_family": metadata_qa.get("target_family", ""),
        "target_term": metadata_qa.get("target_term", ""),
        "step_plan": [],
        "reasoning_steps": [metadata_route.get("reason") or "메타데이터 QA 라우터에서 직접 답변 대상으로 분류했습니다."],
    }
    analysis = {
        "status": "ok",
        "analysis_kind": applied_scope["analysis_kind"],
        "columns": data.get("columns", []),
        "rows": data.get("rows", []),
        "row_count": data.get("row_count", 0),
        "reasoning_steps": intent_plan["reasoning_steps"],
        "safety_passed": True,
        "executed": False,
        "errors": [],
    }

    next_payload = deepcopy(payload)
    next_payload["direct_response_ready"] = True
    next_payload["metadata_qa"] = metadata_qa
    next_payload["intent_plan"] = intent_plan
    next_payload["analysis"] = analysis
    next_payload["data"] = data
    next_payload["applied_scope"] = applied_scope
    next_payload["answer_message"] = answer_message
    next_payload["status"] = "ok"
    next_payload["errors"] = list(next_payload.get("errors", [])) if isinstance(next_payload.get("errors"), list) else []
    next_payload["state"] = _state_with_chat_history(payload, answer_message, metadata_qa)
    return next_payload


def _catalog_list_response(datasets: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    rows = []
    for key, item in sorted(datasets.items()):
        rows.append(
            {
                "DATASET_KEY": key,
                "DISPLAY_NAME": item.get("display_name", ""),
                "DATASET_FAMILY": item.get("dataset_family", ""),
                "SOURCE_TYPE": item.get("source_type", ""),
                "DATE_SCOPE": item.get("date_scope", ""),
                "QUANTITY_COLUMN": _compact_value(item.get("primary_quantity_column")),
                "REQUIRED_PARAMS": _compact_value(item.get("required_params", [])),
            }
        )
    answer = (
        f"현재 등록된 조회 가능 데이터는 {len(rows)}개입니다. "
        "특정 데이터의 활용 예시는 `production_today 활용 예시 알려줘`처럼 물어보면 됩니다."
    )
    return answer, _data(rows)


def _dataset_examples_response(
    metadata_route: dict[str, Any],
    datasets: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    selected = _select_datasets(metadata_route, datasets)
    if not selected:
        rows = [{"DATASET_KEY": key, "DISPLAY_NAME": item.get("display_name", "")} for key, item in sorted(datasets.items())]
        return "어떤 데이터의 활용 예시가 필요한지 dataset_key를 함께 알려주세요.", _data(rows)

    rows = []
    sections = []
    for key, item in selected:
        examples = _examples_for_dataset(key, item, metadata)
        sections.append(f"{key} 활용 예시:\n" + "\n".join(f"- {example}" for example in examples))
        for index, example in enumerate(examples, start=1):
            rows.append({"DATASET_KEY": key, "EXAMPLE_NO": index, "EXAMPLE_QUESTION": example})
    answer = "\n\n".join(sections)
    return answer, _data(rows)


def _dataset_detail_response(metadata_route: dict[str, Any], datasets: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    selected = _select_datasets(metadata_route, datasets)
    if not selected:
        rows = [{"DATASET_KEY": key, "DISPLAY_NAME": item.get("display_name", "")} for key, item in sorted(datasets.items())]
        return "확인할 데이터셋을 dataset_key로 지정해 주세요.", _data(rows)

    key, item = selected[0]
    fields = {
        "display_name": item.get("display_name", ""),
        "dataset_family": item.get("dataset_family", ""),
        "date_scope": item.get("date_scope", ""),
        "source_type": item.get("source_type", ""),
        "db_key": (item.get("source_config") or {}).get("db_key", "") if isinstance(item.get("source_config"), dict) else "",
        "required_params": item.get("required_params", []),
        "required_param_mappings": item.get("required_param_mappings", {}),
        "date_format": item.get("date_format", ""),
        "primary_quantity_column": item.get("primary_quantity_column", ""),
        "filter_mappings": item.get("filter_mappings", {}),
        "default_detail_columns": item.get("default_detail_columns", []),
        "columns": item.get("columns", []),
    }
    rows = [{"DATASET_KEY": key, "FIELD": field, "VALUE": _compact_value(value)} for field, value in fields.items()]
    answer = (
        f"`{key}`는 {fields['source_type']} 기반 `{fields['dataset_family']}` 계열 데이터입니다. "
        f"수량 기준 컬럼은 `{_compact_value(fields['primary_quantity_column'])}`이고, "
        f"필수 파라미터는 `{_compact_value(fields['required_params'])}`입니다."
    )
    return answer, _data(rows)


def _dataset_query_response(metadata_route: dict[str, Any], datasets: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    selected = _select_datasets(metadata_route, datasets)
    if not selected:
        rows = [{"DATASET_KEY": key, "DISPLAY_NAME": item.get("display_name", "")} for key, item in sorted(datasets.items())]
        return "조회 쿼리를 볼 데이터셋을 dataset_key로 지정해 주세요.", _data(rows)

    key, item = selected[0]
    source_config = item.get("source_config") if isinstance(item.get("source_config"), dict) else {}
    query = str(source_config.get("query_template") or "").strip()
    rows = [
        {
            "DATASET_KEY": key,
            "SOURCE_TYPE": item.get("source_type", ""),
            "DB_KEY": source_config.get("db_key", ""),
            "QUERY_TEMPLATE": query,
        }
    ]
    if not query:
        return f"`{key}`에는 query_template이 등록되어 있지 않습니다.", _data(rows)
    answer = f"`{key}` 조회 쿼리 템플릿입니다.\n\n```sql\n{query}\n```"
    return answer, _data(rows)


def _domain_search_response(metadata_route: dict[str, Any], metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    term = str(metadata_route.get("target_term") or "").strip()
    question_terms = [term] if term else []
    if not question_terms:
        question_terms = [str(metadata_route.get("reason") or "")]
    matches = _find_domain_matches(metadata, question_terms)
    if not matches:
        return f"`{term or '요청어'}`와 직접 매칭되는 도메인 등록 정보를 찾지 못했습니다.", _data([])
    rows = matches[:10]
    labels = ", ".join(f"{row['SECTION']}/{row['KEY']}" for row in rows[:5])
    answer = f"`{term or '요청어'}` 관련 도메인 등록 정보는 {len(matches)}건 찾았습니다. 주요 항목: {labels}"
    return answer, _data(rows)


def _help_response(intro: str) -> tuple[str, dict[str, Any]]:
    examples = [
        "현재 조회 가능한 DATA LIST 알려줘",
        "production_today 활용 예시 알려줘",
        "production_today 조회 쿼리문 알려줘",
        "AUTO향 관련 등록 정보 알려줘",
        "오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성률을 보여줘",
    ]
    rows = [{"CATEGORY": "example", "EXAMPLE_QUESTION": example} for example in examples]
    answer = intro + "\n\n바로 써볼 수 있는 질문 예시는 아래와 같습니다.\n" + "\n".join(f"- {example}" for example in examples)
    return answer, _data(rows)


def _find_domain_matches(metadata: dict[str, Any], terms: list[str]) -> list[dict[str, Any]]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    normalized_terms = [_normalize(term) for term in terms if str(term or "").strip()]
    rows: list[dict[str, Any]] = []
    for section, values in domain.items():
        if section == "product_key_columns":
            text = " ".join(str(item) for item in values) if isinstance(values, list) else str(values)
            if _matches_terms(text, normalized_terms):
                rows.append({"SECTION": section, "KEY": section, "DISPLAY_NAME": "제품 식별 컬럼", "MATCHED_TERMS": ", ".join(terms), "SUMMARY": text})
            continue
        if not isinstance(values, dict):
            continue
        for key, payload in values.items():
            if not isinstance(payload, dict):
                payload = {"value": payload}
            search_text = " ".join(
                [
                    str(key),
                    str(payload.get("display_name", "")),
                    " ".join(str(alias) for alias in payload.get("aliases", []) if alias is not None)
                    if isinstance(payload.get("aliases"), list)
                    else "",
                    _compact_value(payload.get("condition", "")),
                    _compact_value(payload.get("condition_by_family", "")),
                    _compact_value(payload.get("processes", "")),
                    str(payload.get("formula", "")),
                    str(payload.get("dataset_family", "")),
                    str(payload.get("dataset_key", "")),
                    str(payload.get("output_column", "")),
                ]
            )
            if not _matches_terms(search_text, normalized_terms):
                continue
            rows.append(
                {
                    "SECTION": section,
                    "KEY": key,
                    "DISPLAY_NAME": payload.get("display_name", ""),
                    "MATCHED_TERMS": ", ".join(terms),
                    "SUMMARY": _domain_summary(payload),
                }
            )
    return rows


def _matches_terms(text: str, normalized_terms: list[str]) -> bool:
    normalized_text = _normalize(text)
    if not normalized_terms:
        return False
    return any(term and term in normalized_text for term in normalized_terms)


def _domain_summary(payload: dict[str, Any]) -> str:
    parts = []
    if payload.get("aliases"):
        parts.append("aliases=" + _compact_value(payload.get("aliases")))
    if payload.get("condition"):
        parts.append("condition=" + _compact_value(payload.get("condition")))
    if payload.get("processes"):
        parts.append("processes=" + _compact_value(payload.get("processes")))
    if payload.get("dataset_family"):
        parts.append("dataset_family=" + str(payload.get("dataset_family")))
    if payload.get("dataset_key"):
        parts.append("dataset_key=" + str(payload.get("dataset_key")))
    if payload.get("quantity_column"):
        parts.append("quantity_column=" + _compact_value(payload.get("quantity_column")))
    if payload.get("formula"):
        parts.append("formula=" + str(payload.get("formula")))
    return "; ".join(parts)[:600]


def _select_datasets(metadata_route: dict[str, Any], datasets: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    target_dataset = str(metadata_route.get("target_dataset") or "")
    target_family = str(metadata_route.get("target_family") or "")
    if target_dataset and target_dataset in datasets:
        return [(target_dataset, datasets[target_dataset])]
    if target_family:
        matched = [(key, item) for key, item in datasets.items() if str(item.get("dataset_family") or "") == target_family]
        return sorted(matched, key=lambda pair: (str(pair[1].get("date_scope") or "") != "current_day", pair[0]))[:3]
    return []


def _examples_for_dataset(dataset_key: str, item: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    configured = item.get("usage_examples")
    if isinstance(configured, list) and configured:
        return [str(example) for example in configured[:6] if str(example or "").strip()]

    family = str(item.get("dataset_family") or "")
    product = _first_product_alias(metadata) or "LPDDR5"
    if family == "production":
        return [
            "오늘 DA공정 생산량을 제품별로 보여줘",
            "오늘 W/B공정 생산량이 가장 많은 제품 알려줘",
            f"현재 {product} 제품의 생산량을 알려줘",
            f"{dataset_key} 상세 데이터 보여줘",
            f"{dataset_key} 조회 쿼리문 알려줘",
        ]
    if family == "wip":
        return [
            "현재 DA공정 재공 수량 알려줘",
            "현재 W/B공정에서 재공이 가장 많은 제품 알려줘",
            f"현재 {product} 제품의 재공을 보여줘",
            f"{dataset_key} 상세 데이터 보여줘",
            f"{dataset_key} 조회 쿼리문 알려줘",
        ]
    if family == "target":
        return [
            "오늘 생산 목표값을 제품별로 보여줘",
            f"{product} 제품의 오늘 목표값 알려줘",
            "오늘 생산량, 재공, 목표값과 생산달성률을 보여줘",
            f"{dataset_key} 정보 알려줘",
        ]
    if family == "lot":
        return [
            "현재 작업대기 Lot 수량을 공정별로 알려줘",
            "현재 작업중 Lot 수량을 공정별로 알려줘",
            "현재 DA공정에서 lot, wafer, die 수량을 알려줘",
            "hold된 lot list 알려줘",
        ]
    if family == "hold":
        return [
            "T1234567GEN1 LOT의 HOLD 이력 알려줘",
            "특정 LOT의 HOLD 사유와 해제 이력을 보여줘",
            f"{dataset_key} 조회 쿼리문 알려줘",
        ]
    if family == "equipment":
        return [
            "HBM 장비 보유 현황을 EQP_MODEL별로 알려줘",
            "이 제품에 할당된 장비 현황 알려줘",
            "이 제품의 이 공정에 할당된 장비 대수를 알려줘",
            f"{dataset_key} 상세 데이터 보여줘",
        ]
    if family == "capacity":
        return [
            "HBM 장비 모델별 capacity 알려줘",
            "특정 recipe의 UPH 정보를 보여줘",
            f"{dataset_key} 조회 쿼리문 알려줘",
        ]
    return [f"{dataset_key} 정보 알려줘", f"{dataset_key} 상세 데이터 보여줘", f"{dataset_key} 조회 쿼리문 알려줘"]


def _first_product_alias(metadata: dict[str, Any]) -> str:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    product_terms = domain.get("product_terms") if isinstance(domain.get("product_terms"), dict) else {}
    preferred = product_terms.get("lpddr5") if isinstance(product_terms.get("lpddr5"), dict) else {}
    aliases = preferred.get("aliases") if isinstance(preferred.get("aliases"), list) else []
    if aliases:
        return str(aliases[0])
    for item in product_terms.values():
        if isinstance(item, dict) and isinstance(item.get("aliases"), list) and item["aliases"]:
            return str(item["aliases"][0])
    return ""


def _state_with_chat_history(payload: dict[str, Any], answer_message: str, metadata_qa: dict[str, Any]) -> dict[str, Any]:
    state = deepcopy(payload.get("state", {})) if isinstance(payload.get("state"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    history = list(state.get("chat_history", [])) if isinstance(state.get("chat_history"), list) else []
    if question:
        history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer_message})
    state["chat_history"] = history[-10:]
    context = deepcopy(state.get("context", {})) if isinstance(state.get("context"), dict) else {}
    context["last_route"] = "metadata_qa"
    context["last_metadata_action"] = metadata_qa.get("metadata_action")
    if metadata_qa.get("target_dataset"):
        context["last_metadata_dataset"] = metadata_qa.get("target_dataset")
    if metadata_qa.get("target_term"):
        context["last_metadata_term"] = metadata_qa.get("target_term")
    state["context"] = context
    return state


def _scope_datasets(data: dict[str, Any]) -> list[str]:
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    result = []
    for row in rows:
        if isinstance(row, dict):
            value = row.get("DATASET_KEY")
            if value and value not in result:
                result.append(str(value))
    return result


def _data(rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(str(key))
    return {"columns": columns, "rows": rows, "row_count": len(rows), "data_ref": {}}


def _datasets(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = table_catalog.get("datasets") if isinstance(table_catalog.get("datasets"), dict) else {}
    return {str(key): item for key, item in datasets.items() if isinstance(item, dict)}


def _compact_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _normalize(text: Any) -> str:
    return re.sub(r"[\s\-_/.]+", "", str(text or "").lower())


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _make_message(text: str) -> Message:
    try:
        return Message(text=text)
    except TypeError:
        return Message(content=text)


class MetadataQAResponseBuilder(Component):
    display_name = "02 Metadata QA Response Builder"
    description = "Builds direct Korean answers for metadata/catalog/help routes without data retrieval or pandas execution."
    icon = "MessagesSquare"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="payload_out", display_name="Payload", method="build_payload"),
        Output(name="message", display_name="Message", method="build_message"),
    ]

    def _result(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_result", None)
        if isinstance(cached, dict):
            return cached
        result = build_metadata_qa_response(getattr(self, "payload", None))
        self._cached_result = result
        return result

    def build_payload(self) -> Data:
        result = self._result()
        data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
        metadata_qa = result.get("metadata_qa", {}) if isinstance(result.get("metadata_qa"), dict) else {}
        self.status = {
            "handled": metadata_qa.get("handled", False),
            "action": metadata_qa.get("metadata_action", ""),
            "row_count": data.get("row_count", 0),
        }
        return Data(data=result)

    def build_message(self) -> Message:
        return _make_message(str(self._result().get("answer_message") or ""))
