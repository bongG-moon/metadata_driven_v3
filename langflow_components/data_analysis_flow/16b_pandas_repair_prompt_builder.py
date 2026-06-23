# 파일 설명: 16B Pandas Repair Prompt Builder Langflow custom component 파일입니다.
# 흐름 역할: 실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_pandas_repair_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    repair = payload.get("pandas_repair") if isinstance(payload.get("pandas_repair"), dict) else {}
    if not repair.get("required"):
        route = str(repair.get("route") or "success")
        reason = str(repair.get("reason") or "Pandas repair is not required.")
        prompt = "\n".join(
            [
                "Pandas repair is not required for this payload.",
                f"Repair route: {route}",
                f"Reason: {reason}",
                "Do not generate pandas code for this branch.",
                "The downstream repair executor should pass through the existing payload unchanged.",
            ]
        )
        return {
            "prompt": prompt,
            "payload": payload,
            "prompt_type": "pandas_repair_skip",
            "repair_required": False,
            "repair_decision": repair,
        }

    context = repair.get("context") if isinstance(repair.get("context"), dict) else _pandas_repair_context(payload)
    context = deepcopy(context)
    context.setdefault("column_contract_summary", _column_contract_summary(payload))
    prompt = "\n".join(
        [
            "You repair failed pandas code for a Langflow manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Generate corrected Python pandas code that uses only the provided variables: pd, sources, plan, state.",
            "sources is a dict mapping source_alias to pandas DataFrame.",
            "Use only source aliases that are actual keys in sources/source summaries, normally retrieval_jobs[*].source_alias. Do not invent generic aliases.",
            "plan and state are Python dicts. Use plan['key'], plan.get('key'), state.get('key'); never use plan.key or state.key.",
            "The code must assign the final pandas DataFrame to result_df.",
            "Do not import modules. Do not read/write files. Do not use network, OS, eval, exec, open, subprocess, numpy, np, or np.where.",
            "Do not use pd.inf, float('inf'), or infinity replacement. Avoid division by zero with boolean masks before dividing.",
            "For date/date-format repairs, do not import datetime/date/timedelta. Use pandas only: pd.to_datetime(..., errors='coerce'), Series.dt.strftime(...), string slicing, or direct string comparison with DATE values already present in the plan.",
            "Fix the failed code using the same intent plan and available source DataFrames. Keep result columns aligned to the requested output contract.",
            "Do not use .to_frame() in repaired code. For one total row with multiple metrics, build result_df with pd.DataFrame([{...}]).",
            "Do not use DataFrame.agg(named_metric=(column, func)).to_frame().T; DataFrame.agg can already return a DataFrame and then to_frame will fail.",
            "When combining scalar totals from multiple sources with no group_by, create one DataFrame row directly instead of merging DataFrames with no common key.",
            "Column contract rules:",
            "- Before repaired code runs, each source DataFrame is converted to a standardized pandas analysis view.",
            "- If a physical source column is listed under retrieval_jobs[*].filter_mappings, required_param_mappings, or standard_column_aliases, use the standard mapping key in pandas code, not the physical source column name.",
            "- Do not assume both a mapped physical column and its standard column remain in sources after standardization.",
            "- Physical source column names are allowed only when they have no standard mapping and the source summary shows that column is available.",
            "- Use column_contract_summary below to decide which columns are standardized and which physical-only columns are still allowed.",
            "",
            "Failed execution context:",
            json.dumps(context, ensure_ascii=False, indent=2),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "code": "Corrected Python code. It must set result_df.",
                    "output_columns": ["column names expected in result_df"],
                    "reasoning_steps": ["short explanation of the repair"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {
        "prompt": prompt,
        "payload": payload,
        "prompt_type": "pandas_code_repair",
        "repair_required": True,
        "repair_decision": repair,
    }


def _pandas_repair_context(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = _analysis_from_payload(payload)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}
    return {
        "request": deepcopy(request),
        "intent_plan": deepcopy(payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}),
        "payload_summary": _payload_summary(payload),
        "column_contract_summary": _column_contract_summary(payload),
        "runtime_source_summary": _runtime_source_summary(runtime_sources),
        "state_summary": _state_summary(state),
        "failed_pandas_code_json": deepcopy(
            analysis.get("pandas_code_json") if isinstance(analysis.get("pandas_code_json"), dict) else {}
        ),
        "executed_code": str(analysis.get("analysis_code") or ""),
        "errors": _as_text_list(analysis.get("errors")),
        "analysis_columns": _as_text_list(analysis.get("columns")),
        "analysis_row_count": analysis.get("row_count", 0),
        "llm_text_preview": str(analysis.get("llm_text_preview") or "")[:1200],
    }


def _analysis_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    if analysis:
        return analysis
    analysis_keys = {
        "status",
        "analysis_kind",
        "analysis_code",
        "columns",
        "rows",
        "row_count",
        "errors",
        "pandas_code_json",
        "llm_text_preview",
    }
    if any(key in payload for key in analysis_keys):
        return payload
    return {}


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("status", "warnings", "errors", "info", "direct_response_ready"):
        if key in payload:
            summary[key] = deepcopy(payload.get(key))
    for key in ("retrieval_jobs", "source_results"):
        value = payload.get(key)
        if isinstance(value, list):
            summary[key] = [_compact_dict(item, 12) for item in value[:20] if isinstance(item, dict)]
    return summary


def _column_contract_summary(payload: dict[str, Any]) -> dict[str, Any]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    source_columns_by_alias = _source_columns_by_alias(payload)
    result: dict[str, Any] = {}
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        alias = str(job.get("source_alias") or job.get("dataset_key") or "").strip()
        if not alias:
            continue
        mapped_columns: dict[str, list[str]] = {}
        mapped_physical_columns: set[str] = set()
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mapping = job.get(field) if isinstance(job.get(field), dict) else {}
            for standard, candidates in mapping.items():
                standard_text = str(standard or "").strip()
                if not standard_text:
                    continue
                if not isinstance(candidates, list):
                    candidates = [candidates]
                physical_candidates = [
                    str(candidate)
                    for candidate in candidates
                    if str(candidate or "").strip() and str(candidate) != standard_text
                ]
                if not physical_candidates:
                    continue
                mapped_columns.setdefault(standard_text, [])
                mapped_columns[standard_text].extend(physical_candidates)
                mapped_physical_columns.update(physical_candidates)
        mapped_columns = {
            standard: _unique_columns(candidates)
            for standard, candidates in mapped_columns.items()
            if candidates
        }
        source_columns = source_columns_by_alias.get(alias, [])
        physical_only_columns = [
            column
            for column in source_columns
            if column not in mapped_physical_columns and column not in mapped_columns
        ]
        result[alias] = {
            "use_standard_names_for_mapped_columns": mapped_columns,
            "physical_only_columns_allowed_by_name": physical_only_columns,
        }
    return result


def _source_columns_by_alias(payload: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    source_results = payload.get("source_results") if isinstance(payload.get("source_results"), list) else []
    for source in source_results:
        if not isinstance(source, dict):
            continue
        alias = str(source.get("source_alias") or source.get("dataset_key") or "").strip()
        if not alias:
            continue
        columns = source.get("columns") if isinstance(source.get("columns"), list) else []
        if not columns:
            rows = source.get("rows") if isinstance(source.get("rows"), list) else []
            first_row = rows[0] if rows and isinstance(rows[0], dict) else {}
            columns = list(first_row.keys())
        result[alias] = _unique_columns([str(column) for column in columns if str(column or "").strip()])
    return result


def _runtime_source_summary(runtime_sources: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for alias, rows in runtime_sources.items():
        clean_rows = rows if isinstance(rows, list) else []
        first_row = clean_rows[0] if clean_rows and isinstance(clean_rows[0], dict) else {}
        summary[str(alias)] = {
            "row_count": len(clean_rows),
            "columns": list(first_row.keys()),
            "preview_rows": deepcopy(clean_rows[:5]),
        }
    return summary


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = current_data.get("rows") if isinstance(current_data.get("rows"), list) else []
    return {
        "has_state": bool(state),
        "context": deepcopy(state.get("context", {})),
        "current_data_columns": deepcopy(current_data.get("columns", [])),
        "current_data_row_count": current_data.get("row_count", 0),
        "current_data_preview_rows": deepcopy(rows[:3]),
        "current_data_product_key_columns": deepcopy(current_data.get("product_key_columns", [])),
        "current_data_product_key_values": deepcopy(current_data.get("product_key_values", [])[:20])
        if isinstance(current_data.get("product_key_values"), list)
        else [],
    }


def _compact_dict(value: dict[str, Any], max_keys: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= max_keys:
            result["..."] = f"{len(value) - max_keys} more keys"
            break
        if key in {"data", "rows", "runtime_sources"}:
            if isinstance(item, list):
                result[key] = {"row_count": len(item), "preview_rows": deepcopy(item[:3])}
            elif isinstance(item, dict):
                result[key] = {"keys": list(item.keys())[:20]}
            else:
                result[key] = item
        else:
            result[key] = deepcopy(item)
    return result


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item) for item in value if str(item or "").strip()]


def _unique_columns(columns: list[str]) -> list[str]:
    result: list[str] = []
    for column in columns:
        if column not in result:
            result.append(column)
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 16B Pandas Repair Prompt Builder
# Langflow 표시 설명: 실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다.
class PandasRepairPromptBuilder(Component):

    display_name = "16B Pandas Repair Prompt Builder"
    description = "실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다."
    inputs = [DataInput(name="payload", display_name="Repair Payload", required=True)]
    outputs = [
        Output(name="repair_prompt", display_name="Repair Prompt", method="build_prompt"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt(self) -> Message:
        prompt_payload = build_pandas_repair_prompt_payload(getattr(self, "payload", None))
        self.status = {

            "prompt_type": prompt_payload.get("prompt_type", "pandas_code_repair"),
            "repair_required": prompt_payload.get("repair_required", False),
            "chars": len(prompt_payload["prompt"]),
        }
        return Message(text=prompt_payload["prompt"])
