# 파일 설명: 22 API Response Builder Langflow custom component 파일입니다.
# 흐름 역할: 최종 데이터 분석 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 최종 데이터 분석 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_main_flow_api_response(payload_value: Any) -> dict[str, Any]:
    payload = _payload_from_value(payload_value)
    data = _build_data_view(payload)
    applied_scope = _as_dict(payload.get("applied_scope"))
    intent_plan = _as_dict(payload.get("intent_plan"))
    analysis = _build_analysis_view(payload, data)
    state = deepcopy(payload.get("state")) if isinstance(payload.get("state"), dict) else {}
    warnings = _unique_values([*_as_list(payload.get("warnings")), *_as_list(analysis.get("warnings"))])
    errors = _unique_values([*_as_list(payload.get("errors")), *_as_list(analysis.get("errors"))])
    status = str(payload.get("status") or analysis.get("status") or ("error" if errors else "ok")).strip() or "ok"
    answer_message = _first_text(payload, ["answer_message", "message", "response", "answer", "text", "content"])
    data_refs = _collect_data_refs(payload, data, analysis, state)
    developer = _developer_view(payload, analysis, data_refs)
    metadata_qa = _as_dict(payload.get("metadata_qa"))
    metadata_route = _as_dict(payload.get("metadata_route"))
    direct_response_ready = bool(payload.get("direct_response_ready") or metadata_qa)
    response_type = "metadata_qa" if direct_response_ready else "analysis"

    api_response = {
        "status": status,
        "success": status.lower() not in {"error", "failed", "failure"} and not errors,
        "response_type": response_type,
        "direct_response_ready": direct_response_ready,
        "message": answer_message,
        "response": answer_message,
        "answer_message": answer_message,
        "data": data,
        "columns": data.get("columns", []),
        "row_count": data.get("row_count", 0),
        "data_ref": data.get("data_ref", {}),
        "applied_scope": applied_scope,
        "intent": _build_intent_view(intent_plan, applied_scope),
        "intent_plan": intent_plan,
        "analysis": analysis,
        "state": state,
        "warnings": warnings,
        "errors": errors,
        "data_refs": data_refs,
    }
    if metadata_qa:
        api_response["metadata_qa"] = metadata_qa
    if metadata_route:
        api_response["metadata_route"] = metadata_route
    if developer:
        api_response["developer"] = developer
    return {"api_response": api_response}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 최종 데이터 분석 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_api_response(payload_value: Any) -> dict[str, Any]:
    return build_main_flow_api_response(payload_value)


def _make_data(payload: dict[str, Any]) -> Any:
    try:
        return Data(data=payload)
    except TypeError:
        return Data(payload)


def _payload_from_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return deepcopy(data)
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
        except Exception:
            return {"text": text}
        return deepcopy(parsed) if isinstance(parsed, dict) else {"text": text}
    return {}


def _build_data_view(payload: dict[str, Any]) -> dict[str, Any]:
    source = _as_dict(payload.get("data"))
    analysis = _as_dict(payload.get("analysis"))
    source_rows = _row_list(source.get("rows"))
    analysis_rows = _row_list(analysis.get("rows"))
    source_columns = _string_list(source.get("columns")) or _columns_from_rows(source_rows)
    analysis_columns = _string_list(analysis.get("columns")) or _columns_from_rows(analysis_rows)
    use_analysis = _should_prefer_analysis_data(source_rows, source_columns, analysis_rows, analysis_columns)

    if use_analysis:
        rows = analysis_rows
        columns = analysis_columns
        row_count = _int_value(analysis.get("row_count"), len(rows))
        data_ref = _normalize_data_ref(analysis.get("data_ref") or source.get("data_ref"))
    else:
        rows = source_rows or analysis_rows
        columns = source_columns or analysis_columns or _columns_from_rows(rows)
        row_count = _int_value(source.get("row_count"), _int_value(analysis.get("row_count"), len(rows)))
        data_ref = _normalize_data_ref(source.get("data_ref") or analysis.get("data_ref"))

    data = {
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
        "data_ref": data_ref,
    }
    for key in ("data_is_reference", "data_is_preview", "data_ref_loaded", "data_ref_load_mode", "rows_are_preview"):
        value = source.get(key)
        if value in (None, "", [], {}):
            value = analysis.get(key)
        if value not in (None, "", [], {}):
            data[key] = deepcopy(value)
    if "data_is_preview" not in data and row_count > len(rows):
        data["data_is_preview"] = True
    if "data_is_reference" not in data and data_ref:
        data["data_is_reference"] = True
    return data


def _should_prefer_analysis_data(
    source_rows: list[dict[str, Any]],
    source_columns: list[str],
    analysis_rows: list[dict[str, Any]],
    analysis_columns: list[str],
) -> bool:
    if not analysis_rows:
        return False
    if not source_rows:
        return True
    if analysis_columns and source_columns and analysis_columns != source_columns:
        return True
    return False


def _build_analysis_view(payload: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    source = _as_dict(payload.get("analysis"))
    debug = _as_dict(payload.get("debug")) or _as_dict(payload.get("developer"))
    pandas_code_json = _as_dict(source.get("pandas_code_json")) or _as_dict(debug.get("pandas_code_json"))
    analysis_code = source.get("analysis_code") or debug.get("analysis_code") or pandas_code_json.get("code")
    analysis_rows = _row_list(source.get("rows"))
    analysis_columns = _string_list(source.get("columns")) or _columns_from_rows(analysis_rows)
    analysis_row_count = None
    if source.get("row_count") not in (None, "", [], {}) or analysis_rows:
        analysis_row_count = _int_value(source.get("row_count"), len(analysis_rows))
    view = {
        "status": source.get("status") or debug.get("analysis_status") or payload.get("analysis_status"),
        "safety_passed": source.get("safety_passed"),
        "executed": source.get("executed"),
        "columns": analysis_columns,
        "rows": analysis_rows,
        "row_count": analysis_row_count,
        "analysis_code": analysis_code or "",
        "pandas_code_json": pandas_code_json,
        "reasoning_steps": _as_list(source.get("reasoning_steps") or debug.get("reasoning_steps")),
        "function_case_trace": source.get("function_case_trace") or debug.get("function_case_trace"),
        "warnings": _as_list(source.get("warnings") or debug.get("warnings")),
        "errors": _as_list(source.get("errors") or debug.get("errors")),
    }
    for key in ("data_ref", "data_is_reference", "data_is_preview", "data_ref_loaded", "data_ref_load_mode"):
        if source.get(key) not in (None, "", [], {}):
            view[key] = deepcopy(source[key])
    return {key: value for key, value in view.items() if value not in (None, "", [], {})}


def _build_intent_view(intent_plan: dict[str, Any], applied_scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": intent_plan.get("route"),
        "intent_type": applied_scope.get("intent_type") or intent_plan.get("intent_type"),
        "analysis_kind": applied_scope.get("analysis_kind") or intent_plan.get("analysis_kind"),
        "datasets": applied_scope.get("datasets") or intent_plan.get("datasets") or [],
        "source_aliases": applied_scope.get("source_aliases") or [],
        "step_ids": applied_scope.get("step_ids") or [step.get("step_id") for step in _as_list(intent_plan.get("step_plan")) if isinstance(step, dict)],
        "metadata_action": intent_plan.get("metadata_action"),
        "target_dataset": intent_plan.get("target_dataset"),
        "target_family": intent_plan.get("target_family"),
        "target_term": intent_plan.get("target_term"),
    }


def _developer_view(payload: dict[str, Any], analysis: dict[str, Any], data_refs: list[dict[str, Any]]) -> dict[str, Any]:
    intent_plan = _as_dict(payload.get("intent_plan"))
    source_results = [_source_result_summary(item) for item in _as_list(payload.get("source_results")) if isinstance(item, dict)]
    view = {
        "analysis_code": analysis.get("analysis_code"),
        "pandas_code_json": analysis.get("pandas_code_json"),
        "reasoning_steps": analysis.get("reasoning_steps"),
        "function_case_trace": analysis.get("function_case_trace"),
        "retrieval_jobs": intent_plan.get("retrieval_jobs"),
        "source_results": source_results,
        "data_ref_load": payload.get("data_ref_load"),
        "mongo_data_store": payload.get("mongo_data_store"),
    }
    return {key: deepcopy(value) for key, value in view.items() if value not in (None, "", [], {})}


def _source_result_summary(source: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(source.get(key))
        for key in (
            "source_alias",
            "dataset_key",
            "row_count",
            "columns",
            "data_ref",
            "applied_filters",
            "applied_params",
            "errors",
            "warnings",
        )
        if source.get(key) not in (None, "", [], {})
    }


def _collect_data_refs(payload: dict[str, Any], data: dict[str, Any], analysis: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in _as_list(payload.get("data_refs")):
        _append_data_ref(refs, ref)
    _append_data_ref(refs, data.get("data_ref"))
    _append_data_ref(refs, analysis.get("data_ref"))
    current_data = _as_dict(state.get("current_data"))
    _append_data_ref(refs, current_data.get("data_ref"))
    for source in _as_list(payload.get("source_results")):
        if isinstance(source, dict):
            _append_data_ref(refs, source.get("data_ref"), source)
    for source in _as_list(state.get("followup_source_results")):
        if isinstance(source, dict):
            _append_data_ref(refs, source.get("data_ref"), source)
    runtime_source_refs = _as_dict(state.get("runtime_source_refs"))
    for alias, ref in runtime_source_refs.items():
        _append_data_ref(refs, ref, {"source_alias": alias})
    return refs


def _append_data_ref(refs: list[dict[str, Any]], ref: Any, source: dict[str, Any] | None = None) -> None:
    normalized = _normalize_data_ref(ref)
    if not normalized:
        return
    source = source if isinstance(source, dict) else {}
    for key in ("dataset_key", "source_alias", "job_key"):
        if normalized.get(key) in (None, "", [], {}) and source.get(key) not in (None, "", [], {}):
            normalized[key] = deepcopy(source[key])
    signature = "|".join(str(normalized.get(key) or "") for key in ("ref_id", "path", "collection_name", "store"))
    for existing in refs:
        existing_signature = "|".join(str(existing.get(key) or "") for key in ("ref_id", "path", "collection_name", "store"))
        if existing_signature == signature:
            return
    refs.append(normalized)


def _normalize_data_ref(ref: Any) -> dict[str, Any]:
    if isinstance(ref, dict) and ref:
        return deepcopy(ref)
    if isinstance(ref, str) and ref.strip():
        text = ref.strip()
        return {"store": "memory" if text.startswith("memory://") else "external", "ref_id": text}
    return {}


def _first_text(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple, set)) else []


def _row_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(row) for row in value if isinstance(row, dict)]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _int_value(value: Any, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == value:
        return int(value)
    try:
        return int(str(value))
    except Exception:
        return fallback


def _unique_values(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    signatures: set[str] = set()
    for value in values:
        if value in (None, "", [], {}):
            continue
        signature = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if signature in signatures:
            continue
        signatures.add(signature)
        result.append(deepcopy(value))
    return result


# 컴포넌트 설명: 22 API Response Builder
# Langflow 표시 설명: 최종 데이터 분석 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
class MainFlowApiResponseBuilder(Component):

    display_name = "22 API Response Builder"
    description = "최종 데이터 분석 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다."
    icon = "Braces"
    name = "MainFlowApiResponseBuilder"

    inputs = [
        DataInput(name="payload", display_name="Payload", info="Payload output from 20 Answer Response Builder.", input_types=["Data", "JSON"], required=True),
    ]

    outputs = [Output(name="api_response", display_name="API Response", method="build_api_response_output", types=["Data"])]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 최종 데이터 분석 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def _payload(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_payload", None)
        if isinstance(cached, dict):
            return cached

        payload = build_main_flow_api_response(getattr(self, "payload", None))
        self._cached_payload = payload
        return payload

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 최종 데이터 분석 payload를 web/API client가 쓰기 쉬운 compact JSON 응답으로 투영합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_api_response_output(self) -> Data:
        payload = self._payload()
        api_response = _as_dict(payload.get("api_response"))
        self.status = {
            "status": api_response.get("status"),
            "row_count": api_response.get("row_count", 0),
            "column_count": len(api_response.get("columns", [])),
        }
        return _make_data(payload)
