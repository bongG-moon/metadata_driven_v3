from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_final_payload(
    question: str,
    session_id: str,
    state: dict[str, Any],
    metadata_context: dict[str, Any],
    intent_plan: dict[str, Any],
    source_results: list[dict[str, Any]],
    analysis_result: dict[str, Any],
) -> dict[str, Any]:
    data = {
        "columns": list(analysis_result.get("columns", [])),
        "rows": deepcopy(analysis_result.get("rows", [])),
        "row_count": int(analysis_result.get("row_count", 0)),
        "data_ref": f"memory://{session_id}/current_data",
    }
    applied_scope = _build_applied_scope(intent_plan, source_results, metadata_context)
    answer_message = _answer_text(intent_plan, data, applied_scope, analysis_result)
    next_state = _build_next_state(question, answer_message, state, data, applied_scope, source_results)

    return {
        "payload_version": "agent-v1",
        "status": "ok" if not analysis_result.get("errors") else "warning",
        "request": {"session_id": session_id, "question": question, "timezone": "Asia/Seoul"},
        "metadata_context": metadata_context,
        "intent_plan": intent_plan,
        "retrieval_jobs": deepcopy(intent_plan.get("retrieval_jobs", [])),
        "source_results": source_results,
        "analysis": {
            "status": analysis_result.get("status"),
            "analysis_kind": analysis_result.get("analysis_kind"),
            "analysis_code": analysis_result.get("analysis_code", ""),
            "intermediate_refs": analysis_result.get("intermediate_refs", {}),
        },
        "answer_message": answer_message,
        "data": data,
        "applied_scope": applied_scope,
        "state": next_state,
        "warnings": [],
        "errors": list(analysis_result.get("errors", [])),
    }


def build_metadata_context(metadata: dict[str, Any], intent_plan: dict[str, Any]) -> dict[str, Any]:
    dataset_keys = []
    for job in intent_plan.get("retrieval_jobs", []):
        dataset_key = job.get("dataset_key")
        if dataset_key and dataset_key not in dataset_keys:
            dataset_keys.append(dataset_key)
    domain_refs = []
    if intent_plan.get("product_grain"):
        domain_refs.append({"key": "product_grain", "columns": intent_plan["product_grain"]})
    if any("OPER_NAME" in str(job.get("filters", [])) for job in intent_plan.get("retrieval_jobs", [])):
        domain_refs.append({"key": "process_group", "source": "domain_items.process_groups"})
    return {
        "domain_refs": domain_refs,
        "table_refs": [{"dataset_key": key} for key in dataset_keys],
        "filter_refs": _filter_refs(intent_plan),
    }


def _build_applied_scope(
    intent_plan: dict[str, Any],
    source_results: list[dict[str, Any]],
    metadata_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "intent_type": intent_plan.get("intent_type"),
        "analysis_kind": intent_plan.get("analysis_kind"),
        "datasets": [result["dataset_key"] for result in source_results],
        "source_aliases": [result["source_alias"] for result in source_results],
        "params_by_source": {result["source_alias"]: result.get("applied_params", {}) for result in source_results},
        "filters_by_source": {result["source_alias"]: result.get("applied_filters", []) for result in source_results},
        "step_ids": [step.get("step_id") for step in intent_plan.get("step_plan", [])],
        "metadata_refs": metadata_context,
    }


def _answer_text(
    intent_plan: dict[str, Any],
    data: dict[str, Any],
    applied_scope: dict[str, Any],
    analysis_result: dict[str, Any],
) -> str:
    if analysis_result.get("errors"):
        return "요청을 처리했지만 일부 분석 단계에서 확인이 필요합니다: " + "; ".join(analysis_result["errors"])

    row_count = data["row_count"]
    datasets = ", ".join(applied_scope.get("datasets", []))
    if row_count == 0:
        return f"조건에 맞는 데이터가 없습니다. 사용 dataset: {datasets}"

    first_rows = data["rows"][:3]
    preview = "; ".join(_compact_row_text(row) for row in first_rows)
    suffix = "" if row_count <= 3 else f" 외 {row_count - 3}건"
    return f"{row_count}건을 찾았습니다. 사용 dataset: {datasets}. 결과 예시: {preview}{suffix}"


def _compact_row_text(row: dict[str, Any]) -> str:
    items = []
    for key, value in row.items():
        if value not in (None, ""):
            items.append(f"{key}={value}")
        if len(items) >= 5:
            break
    return "(" + ", ".join(items) + ")"


def _build_next_state(
    question: str,
    answer_message: str,
    state: dict[str, Any],
    data: dict[str, Any],
    applied_scope: dict[str, Any],
    source_results: list[dict[str, Any]],
) -> dict[str, Any]:
    next_state = deepcopy(state or {})
    history = list(next_state.get("chat_history", []))
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer_message})
    next_state["chat_history"] = history[-10:]
    next_state["context"] = {
        "last_intent_type": applied_scope.get("intent_type"),
        "last_analysis_kind": applied_scope.get("analysis_kind"),
        "last_datasets": applied_scope.get("datasets", []),
    }
    next_state["current_data"] = deepcopy(data)
    next_state["current_data"]["source_dataset_keys"] = applied_scope.get("datasets", [])
    next_state["current_data"]["source_aliases"] = applied_scope.get("source_aliases", [])
    next_state["current_data"]["source_refs"] = [
        {
            "source_alias": result["source_alias"],
            "dataset_key": result["dataset_key"],
            "data_ref": result["data_ref"],
            "row_count": result["row_count"],
        }
        for result in source_results
    ]
    next_state["current_data"]["dataset_required_params"] = {
        result["source_alias"]: result.get("applied_params", {}) for result in source_results
    }
    next_state["followup_source_results"] = [
        {
            "source_alias": result["source_alias"],
            "dataset_key": result["dataset_key"],
            "data_ref": result["data_ref"],
            "row_count": result["row_count"],
            "applied_params": result.get("applied_params", {}),
            "applied_filters": result.get("applied_filters", []),
            "applied_column_filters": result.get("applied_column_filters", []),
        }
        for result in source_results
    ]
    return next_state


def _filter_refs(intent_plan: dict[str, Any]) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for job in intent_plan.get("retrieval_jobs", []):
        for condition in job.get("filters", []):
            field = condition.get("field")
            if field and field not in seen:
                seen.add(field)
                refs.append({"filter_key": field})
    return refs
