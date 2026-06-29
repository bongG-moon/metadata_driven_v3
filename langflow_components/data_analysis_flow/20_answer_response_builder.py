# 파일 설명: 20 Answer Response Builder Langflow custom component 파일입니다.
# 흐름 역할: LLM 답변과 result data, 적용 scope, 다음 턴 state를 하나의 최종 payload로 결합합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: LLM 답변과 result data, 적용 scope, 다음 턴 state를 하나의 최종 payload로 결합합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_answer_response_payload(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    if payload.get("direct_response_ready"):
        return payload
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    data = _build_data(payload, analysis)
    applied_scope = _build_applied_scope(payload)
    answer_message = _answer_text_from_llm(llm_response_value) or _fallback_answer_text(data, applied_scope, analysis)
    answer_message = _strip_embedded_result_tables(answer_message, data)
    state = _next_state(payload, data, applied_scope, answer_message)

    next_payload = dict(payload)
    next_payload.pop("runtime_sources", None)
    next_payload["analysis"] = _compact_analysis_after_data(analysis)
    next_payload["data"] = data
    next_payload["applied_scope"] = applied_scope
    next_payload["answer_message"] = answer_message
    next_payload["state"] = state
    next_payload["status"] = "ok" if not analysis.get("errors") else "warning"
    next_payload["errors"] = list(payload.get("errors", [])) + list(analysis.get("errors", []))
    return next_payload


def _compact_analysis_after_data(analysis: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(analysis)
    if isinstance(result.get("rows"), list):
        result.pop("rows", None)
        result["rows_moved_to_data"] = True
    return result


def _build_data(payload: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    session_id = ((payload.get("request") or {}).get("session_id") or "demo-session") if isinstance(payload.get("request"), dict) else "demo-session"
    data_ref = analysis.get("data_ref") if isinstance(analysis.get("data_ref"), dict) else f"memory://{session_id}/current_data"
    data = {
        "columns": list(analysis.get("columns", [])),
        "rows": deepcopy(analysis.get("rows", [])),
        "row_count": int(analysis.get("row_count", 0) or 0),
        "data_ref": deepcopy(data_ref),
    }
    for key in ("data_is_reference", "data_is_preview", "data_ref_loaded", "data_ref_load_mode"):
        if key in analysis:
            data[key] = deepcopy(analysis[key])
    return data


def _build_applied_scope(payload: dict[str, Any]) -> dict[str, Any]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    source_results = payload.get("source_results") if isinstance(payload.get("source_results"), list) else []
    filters_by_source = {}
    params_by_source = {}
    datasets = []
    source_aliases = []
    for result in source_results:
        if not isinstance(result, dict):
            continue
        alias = result.get("source_alias")
        dataset_key = result.get("dataset_key")
        if dataset_key:
            datasets.append(dataset_key)
        if alias:
            source_aliases.append(alias)
            filters_by_source[alias] = result.get("applied_filters", [])
            params_by_source[alias] = result.get("applied_params", {})
    return {
        "intent_type": plan.get("intent_type"),
        "analysis_kind": plan.get("analysis_kind"),
        "datasets": _unique(datasets),
        "source_aliases": _unique(source_aliases),
        "step_ids": [step.get("step_id") for step in plan.get("step_plan", []) if isinstance(step, dict)],
        "filters_by_source": filters_by_source,
        "params_by_source": params_by_source,
        "metadata_refs": payload.get("metadata_context", {}),
    }


def _next_state(
    payload: dict[str, Any],
    data: dict[str, Any],
    applied_scope: dict[str, Any],
    answer_message: str,
) -> dict[str, Any]:
    state = deepcopy(payload.get("state", {})) if isinstance(payload.get("state"), dict) else {}
    history = list(state.get("chat_history", [])) if isinstance(state.get("chat_history"), list) else []
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    if question:
        history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer_message})
    state["chat_history"] = history[-10:]
    state["context"] = {
        "last_intent_type": applied_scope.get("intent_type"),
        "last_analysis_kind": applied_scope.get("analysis_kind"),
        "last_datasets": applied_scope.get("datasets", []),
        "last_source_aliases": applied_scope.get("source_aliases", []),
    }
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    product_key_columns = _product_key_columns(payload, data, analysis)
    product_key_values = _analysis_product_key_values(analysis, product_key_columns)
    if not product_key_values:
        product_key_values = _product_key_values(data.get("rows", []), product_key_columns)
    state["current_data"] = {
        **data,
        "source_dataset_keys": applied_scope.get("datasets", []),
        "source_aliases": applied_scope.get("source_aliases", []),
        "product_key_columns": product_key_columns,
        "product_key_values": product_key_values,
        "product_key_count": len(product_key_values),
    }
    runtime_source_refs = payload.get("runtime_source_refs") if isinstance(payload.get("runtime_source_refs"), dict) else {}
    if runtime_source_refs:
        state["runtime_source_refs"] = deepcopy(runtime_source_refs)
    state["followup_source_results"] = [
        {
            "source_alias": result.get("source_alias"),
            "dataset_key": result.get("dataset_key"),
            "source_type": result.get("source_type"),
            "columns": deepcopy(result.get("columns", [])),
            "data_ref": result.get("data_ref"),
            "row_count": result.get("row_count"),
            "data_is_reference": result.get("data_is_reference"),
            "data_is_preview": result.get("data_is_preview"),
        }
        for result in payload.get("source_results", [])
        if isinstance(result, dict)
    ]
    return state


def _product_key_columns(payload: dict[str, Any], data: dict[str, Any], analysis: dict[str, Any] | None = None) -> list[str]:
    analysis = analysis if isinstance(analysis, dict) else {}
    analysis_columns = analysis.get("product_key_columns")
    if isinstance(analysis_columns, list) and analysis_columns:
        return [str(column) for column in analysis_columns if str(column or "").strip()]
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    plan_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    columns = data.get("columns") if isinstance(data.get("columns"), list) else []
    if plan_grain:
        return [str(column) for column in plan_grain if str(column) in columns]
    default_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "TSV_DIE_TYP"]
    return [column for column in default_keys if column in columns]


def _analysis_product_key_values(analysis: dict[str, Any], product_key_columns: list[str]) -> list[dict[str, Any]]:
    values = analysis.get("product_key_values") if isinstance(analysis.get("product_key_values"), list) else []
    if not values:
        return []
    result: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        if product_key_columns:
            product = {key: item.get(key) for key in product_key_columns if item.get(key) not in {None, ""}}
        else:
            product = {str(key): value for key, value in item.items() if value not in {None, ""}}
        if product and product not in result:
            result.append(product)
    return result


def _product_key_values(rows: Any, product_key_columns: list[str]) -> list[dict[str, Any]]:
    if not product_key_columns or not isinstance(rows, list):
        return []
    values: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        product = {key: row.get(key) for key in product_key_columns if row.get(key) not in {None, ""}}
        if product and product not in values:
            values.append(product)
    return values


def _answer_text_from_llm(value: Any) -> str:
    text = _text(value).strip()
    if not text:
        return ""
    parsed = _extract_json_object(text)
    if parsed:
        for key in ("answer_message", "answer", "text", "message"):
            candidate = parsed.get(key)
            if candidate:
                return str(candidate).strip()
    return _strip_markdown_fence(text)


def _fallback_answer_text(data: dict[str, Any], applied_scope: dict[str, Any], analysis: dict[str, Any]) -> str:
    if analysis.get("errors"):
        return "분석 단계에서 확인이 필요합니다. " + "; ".join(str(item) for item in analysis["errors"])
    datasets = ", ".join(applied_scope.get("datasets", []))
    if data["row_count"] == 0:
        return f"조건에 맞는 데이터가 없습니다. 사용 dataset: {datasets}"
    preview = "; ".join(str(row) for row in data["rows"][:2])
    return f"{data['row_count']}건을 찾았습니다. 사용 dataset: {datasets}. 결과 예시: {preview}"


def _strip_embedded_result_tables(answer_message: str, data: dict[str, Any]) -> str:
    lines = str(answer_message or "").splitlines()
    if not lines:
        return ""

    result_lines: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _is_table_heading(line) and index + 1 < len(lines) and _is_table_like_line(lines[index + 1]):
            index += 1
            while index < len(lines) and _is_table_like_line(lines[index]):
                index += 1
            continue
        if _is_table_like_line(line):
            start = index
            while index < len(lines) and _is_table_like_line(lines[index]):
                index += 1
            block = lines[start:index]
            if _should_strip_table_block(block, data):
                continue
            result_lines.extend(block)
            continue
        result_lines.append(line)
        index += 1

    return _clean_blank_lines(result_lines).strip()


def _is_table_heading(line: str) -> bool:
    text = str(line or "").strip().strip("#").strip()
    return text in {"결과", "결과 테이블", "상세 결과", "표", "데이터", "조회 결과"}


def _is_table_like_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    if "\t" in text and len([cell for cell in text.split("\t") if cell.strip()]) >= 3:
        return True
    if text.startswith("|") and text.endswith("|") and text.count("|") >= 3:
        return True
    if re.fullmatch(r"[\s|:\-]+", text) and "|" in text:
        return True
    return False


def _should_strip_table_block(block: list[str], data: dict[str, Any]) -> bool:
    table_lines = [line for line in block if _is_table_like_line(line)]
    if len(table_lines) < 2:
        return False
    header_cells = _table_cells(table_lines[0])
    data_columns = [str(column) for column in data.get("columns", []) if str(column or "").strip()]
    if len(header_cells) >= 3 and _has_column_overlap(header_cells, data_columns):
        return True
    return len(table_lines) >= 3


def _table_cells(line: str) -> list[str]:
    text = str(line or "").strip()
    if "\t" in text:
        return [cell.strip() for cell in text.split("\t") if cell.strip()]
    if text.startswith("|") and text.endswith("|"):
        return [cell.strip() for cell in text.strip("|").split("|") if cell.strip()]
    return []


def _has_column_overlap(header_cells: list[str], data_columns: list[str]) -> bool:
    if not header_cells or not data_columns:
        return False
    normalized_columns = {_normalize_table_header(column) for column in data_columns}
    return sum(1 for cell in header_cells if _normalize_table_header(cell) in normalized_columns) >= 2


def _normalize_table_header(value: str) -> str:
    aliases = {
        "생산량": "PRODUCTION",
        "할당장비대수": "EQP_COUNT",
        "장비대수": "EQP_COUNT",
        "재공": "WIP",
        "목표": "OUT_PLAN",
        "목표값": "OUT_PLAN",
    }
    text = re.sub(r"\s+", "", str(value or "").strip()).upper()
    return aliases.get(text, text)


def _clean_blank_lines(lines: list[str]) -> str:
    cleaned: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not str(line or "").strip()
        if blank and previous_blank:
            continue
        cleaned.append(line)
        previous_blank = blank
    return "\n".join(cleaned)


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _strip_markdown_fence(text: str) -> str:
    raw = str(text or "").strip()
    fenced = re.match(r"```(?:\w+)?\s*(.*?)\s*```$", raw, re.DOTALL)
    return fenced.group(1).strip() if fenced else raw


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        for key in ("llm_text", "text", "content", "response"):
            if data.get(key):
                return str(data[key])
    for attr in ("text", "content"):
        if getattr(value, attr, None):
            return str(getattr(value, attr))
    return str(value)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _unique(values: list[Any]) -> list[str]:
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


# 컴포넌트 설명: 20 Answer Response Builder
# Langflow 표시 설명: LLM 답변과 result data, 적용 scope, 다음 턴 state를 하나의 최종 payload로 결합합니다.
class AnswerResponseBuilder(Component):

    display_name = "20 Answer Response Builder"
    description = "LLM 답변과 result data, 적용 scope, 다음 턴 state를 하나의 최종 payload로 결합합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: LLM 답변과 result data, 적용 scope, 다음 턴 state를 하나의 최종 payload로 결합합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = build_answer_response_payload(getattr(self, "payload", None), getattr(self, "llm_response", ""))

        self.status = {
            "status": result.get("status"),
            "rows": (result.get("data") or {}).get("row_count", 0),
            "datasets": (result.get("applied_scope") or {}).get("datasets", []),
        }
        return Data(data=result)
