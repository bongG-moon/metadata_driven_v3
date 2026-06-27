# 파일 설명: 15 Pandas Code Executor Langflow custom component 파일입니다.
# 흐름 역할: LLM이 만든 pandas JSON/code를 파싱하고 안전성 검사 후 runtime source DataFrame 위에서 실행합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import ast
import json
import re
from copy import deepcopy
from typing import Any

import pandas as pd
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


FORBIDDEN_CALL_NAMES = {
    "__import__",
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
FORBIDDEN_ROOT_NAMES = {
    "__builtins__",
    "builtins",
    "importlib",
    "io",
    "np",
    "numpy",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "socket",
    "subprocess",
    "sys",
}
PANDAS_WARNING_PREFIX = "pandas_executor:"
AGGREGATE_STEP_OPERATIONS = {
    "aggregate",
    "aggregate_by_group",
    "aggregate_metric",
    "aggregate_sum",
    "aggregate_sum_by_group",
    "sum_by_group",
}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: LLM이 만든 pandas JSON/code를 파싱하고 안전성 검사 후 runtime source DataFrame 위에서 실행합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def execute_pandas_from_llm(payload_value: Any, llm_response_value: Any, specialized_functions_text: Any = "") -> dict[str, Any]:
    payload = _payload(payload_value)
    manual_helper_text = _text(specialized_functions_text).strip()
    if manual_helper_text:
        payload = dict(payload)
        payload["specialized_functions_text"] = manual_helper_text
    if payload.get("direct_response_ready"):
        return payload
    if _should_pass_through_repair_payload(payload):
        return payload
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}

    llm_text = _text(llm_response_value)
    pandas_json = _extract_json_object(llm_text)
    helper_functions, helper_errors = _function_case_helpers(payload, pandas_json.get("code", ""))
    analysis = _execute_generated_pandas_code(pandas_json, plan, runtime_sources, state, helper_functions, helper_errors)
    analysis["pandas_code_json"] = pandas_json
    analysis["llm_text_preview"] = llm_text[:1200]

    next_payload = dict(payload)
    next_payload["analysis"] = analysis
    if _is_repair_attempt_payload(payload):
        next_payload["pandas_repair"] = _mark_repair_attempt_result(payload.get("pandas_repair"), analysis)
    if analysis.get("errors"):
        next_payload["warnings"] = list(next_payload.get("warnings", [])) + [
            f"{PANDAS_WARNING_PREFIX} {item}" for item in analysis["errors"]
        ]
    return next_payload


def _execute_generated_pandas_code(
    pandas_plan: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, Any],
    state: dict[str, Any],
    helper_functions: dict[str, Any] | None = None,
    helper_errors: list[str] | None = None,
) -> dict[str, Any]:
    code = _strip_harmless_pandas_import(str(pandas_plan.get("code", "")))
    repairable_errors: list[str] = []
    safety_errors = [*(helper_errors or []), *_check_code_safety(code)]
    if safety_errors:
        return {
            "status": "error",
            "analysis_kind": plan.get("analysis_kind"),
            "analysis_code": code,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "intermediate_refs": {},
            "errors": safety_errors,
            "safety_passed": False,
            "executed": False,
        }

    source_column_errors = _runtime_source_column_errors(plan, runtime_sources)
    if source_column_errors:
        return {
            "status": "error",
            "analysis_kind": plan.get("analysis_kind"),
            "analysis_code": code,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "intermediate_refs": {},
            "errors": source_column_errors,
            "safety_passed": True,
            "executed": False,
        }

    required_columns_by_alias = _required_columns_by_alias(plan)
    sources = {}
    for alias, rows in runtime_sources.items():
        alias_text = str(alias)
        frame = _source_dataframe(
            rows if isinstance(rows, list) else [],
            required_columns_by_alias.get(alias_text, []),
            str(plan.get("analysis_kind") or ""),
        )
        sources[alias_text] = _standardize_source_frame_for_alias(frame, alias_text, plan)
    local_vars: dict[str, Any] = {
        "pd": pd,
        "sources": sources,
        "plan": deepcopy(plan),
        "state": deepcopy(state),
        **(helper_functions or {}),
    }
    safe_globals = {"__builtins__": _safe_builtins(), "pd": pd}
    try:
        exec(compile(code, "<llm_pandas_code>", "exec"), safe_globals, local_vars)
        function_case_trace = _function_case_trace_from_locals(local_vars)
        result_df = local_vars.get("result_df")
        if result_df is None or not hasattr(result_df, "to_dict"):
            raise ValueError("Generated code must assign a pandas DataFrame to result_df.")
        result_df = result_df.copy()
        result_df = _normalize_result_columns(result_df, plan)
        fallback_df = _fallback_result_df(plan, runtime_sources)
        if _should_replace_empty_generated_result(result_df, fallback_df):
            result_df = _normalize_result_columns(fallback_df, plan)
            fallback_error = "Generated pandas code returned an empty contract result; executor fallback was used."
            repairable_errors.append(fallback_error)
            code = code + "\n# executor_fallback: generated code returned an empty contract result"
        elif _should_replace_incomplete_generated_result(result_df, fallback_df, plan):
            result_df = _normalize_result_columns(fallback_df, plan)
            fallback_error = "Generated pandas code missed required plan output columns; executor fallback was used."
            repairable_errors.append(fallback_error)
            code = code + "\n# executor_fallback: generated code missed required plan output columns"
        elif _should_replace_filter_mismatched_generated_result(result_df, fallback_df, plan):
            result_df = _normalize_result_columns(fallback_df, plan)
            fallback_error = "Generated pandas code did not match pandas-applied source filters; executor fallback was used."
            repairable_errors.append(fallback_error)
            code = code + "\n# executor_fallback: generated code did not match pandas-applied source filters"
        result_df = _normalize_result_columns(_collapse_over_detailed_aggregate_result(result_df, plan), plan)
    except Exception as exc:
        fallback_df = _fallback_result_df(plan, runtime_sources)
        if fallback_df is None:
            return {
                "status": "error",
                "analysis_kind": plan.get("analysis_kind"),
                "analysis_code": code,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "intermediate_refs": {},
                "errors": [f"Generated pandas code failed: {exc}"],
                "safety_passed": True,
                "executed": False,
            }
        result_df = _normalize_result_columns(fallback_df, plan)
        repairable_errors.append(f"Generated pandas code failed before executor fallback: {exc}")
        code = code + f"\n# executor_fallback: {exc}"
        function_case_trace = {}

    rows = result_df.to_dict(orient="records")
    product_key_columns = _product_key_columns(plan, list(result_df.columns))
    product_key_values = _product_key_values(rows, product_key_columns)
    analysis = {
        "status": "ok",
        "analysis_kind": plan.get("analysis_kind"),
        "analysis_code": code,
        "columns": list(result_df.columns),
        "rows": _json_ready(rows),
        "row_count": len(rows),
        "product_key_columns": product_key_columns,
        "product_key_values": product_key_values,
        "product_key_count": len(product_key_values),
        "intermediate_refs": {},
        "errors": [],
        "repairable_errors": repairable_errors,
        "used_executor_fallback": bool(repairable_errors),
        "safety_passed": True,
        "executed": True,
        "output_columns": pandas_plan.get("output_columns", []),
        "reasoning_steps": pandas_plan.get("reasoning_steps", []),
    }
    if function_case_trace:
        analysis["function_case_trace"] = function_case_trace
    return analysis


def _function_case_helpers(payload: dict[str, Any], generated_code: Any = "") -> tuple[dict[str, Any], list[str]]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    cases = domain.get("pandas_function_cases") if isinstance(domain.get("pandas_function_cases"), dict) else {}
    used_function_names = _called_function_names(str(generated_code or ""))
    required_helpers = _required_function_case_helpers(payload, cases, used_function_names)
    required_function_names = {item["function_name"] for item in required_helpers if item.get("function_name")}
    helpers: dict[str, Any] = {}
    errors: list[str] = []
    helpers.update(_manual_function_case_helpers(payload, required_function_names, errors))
    for case_key, case in cases.items():
        if not isinstance(case, dict):
            continue
        function_name = str(case.get("function_name") or "").strip()
        function_code = _function_case_code_text(case.get("function_code"))
        if not function_name or not function_code:
            continue
        if function_name not in required_function_names:
            continue
        helper_code = _function_definition_code(function_code, function_name) or function_code
        case_errors = _check_code_safety(helper_code)
        if case_errors:
            errors.extend(f"pandas_function_cases.{case_key}.{function_name}: {error}" for error in case_errors)
            continue
        local_vars: dict[str, Any] = {"pd": pd}
        safe_globals = {"__builtins__": _safe_builtins(), "pd": pd}
        try:
            exec(compile(helper_code, f"<pandas_function_case:{case_key}>", "exec"), safe_globals, local_vars)
        except Exception as exc:
            errors.append(f"pandas_function_cases.{case_key}.{function_name} failed to load: {exc}")
            continue
        helper = local_vars.get(function_name)
        if not callable(helper):
            errors.append(f"pandas_function_cases.{case_key} did not define callable {function_name}.")
            continue
        helpers[function_name] = helper
    return helpers, errors


def _manual_function_case_helpers(
    payload: dict[str, Any],
    required_function_names: set[str],
    errors: list[str],
) -> dict[str, Any]:
    helpers: dict[str, Any] = {}
    if not required_function_names:
        return helpers
    for index, block in enumerate(_manual_function_case_code_blocks(payload), start=1):
        for function_name in sorted(required_function_names):
            helper_code = _function_definition_code(block, function_name)
            if not helper_code:
                continue
            case_errors = _check_code_safety(helper_code)
            if case_errors:
                errors.extend(f"specialized_functions_text.{function_name}: {error}" for error in case_errors)
                continue
            local_vars: dict[str, Any] = {"pd": pd}
            safe_globals = {"__builtins__": _safe_builtins(), "pd": pd}
            try:
                exec(compile(helper_code, f"<specialized_functions_text:{index}:{function_name}>", "exec"), safe_globals, local_vars)
            except Exception as exc:
                errors.append(f"specialized_functions_text.{function_name} failed to load: {exc}")
                continue
            helper = local_vars.get(function_name)
            if not callable(helper):
                errors.append(f"specialized_functions_text did not define callable {function_name}.")
                continue
            helpers[function_name] = helper
    return helpers


def _required_function_case_helpers(
    payload: dict[str, Any],
    cases: dict[str, Any],
    used_function_names: set[str],
) -> list[dict[str, str]]:
    required: list[dict[str, str]] = []
    runtime = payload.get("pandas_function_case_runtime") if isinstance(payload.get("pandas_function_case_runtime"), dict) else {}
    selected_cases = runtime.get("selected_cases") if isinstance(runtime.get("selected_cases"), list) else []
    for item in selected_cases:
        if isinstance(item, dict):
            _append_function_case_requirement(required, item.get("key"), item.get("function_name"))

    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    for item in _plan_function_case_candidates(plan):
        if isinstance(item, str):
            case_key, function_name = _case_key_and_function_name_from_text(item, cases)
            _append_function_case_requirement(required, case_key, function_name)
            continue
        if not isinstance(item, dict):
            continue
        explicit_key = str(item.get("key") or item.get("case_key") or item.get("function_case_key") or "").strip()
        explicit_function = str(item.get("function_name") or "").strip()
        if explicit_key or explicit_function:
            case_key, function_name = _case_key_and_function_name(explicit_key, explicit_function, cases)
            _append_function_case_requirement(required, case_key, function_name)

    for case_key, case in cases.items():
        if not isinstance(case, dict):
            continue
        function_name = str(case.get("function_name") or "").strip()
        if function_name and function_name in used_function_names:
            _append_function_case_requirement(required, str(case_key), function_name)
    return required


def _plan_function_case_candidates(plan: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = []
    for key in ("pandas_function_case", "function_case"):
        value = plan.get(key)
        if value not in (None, "", [], {}):
            candidates.append(value)
    for key in ("pandas_function_cases", "function_cases"):
        value = plan.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif value not in (None, "", [], {}):
            candidates.append(value)
    steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("operation") == "apply_pandas_function_case" or step.get("function_case_key") or step.get("function_name"):
            candidates.append(step)
    return candidates


def _case_key_and_function_name_from_text(value: str, cases: dict[str, Any]) -> tuple[str, str]:
    text = str(value or "").strip()
    for case_key, case in cases.items():
        if not isinstance(case, dict):
            continue
        function_name = str(case.get("function_name") or "").strip()
        if text == str(case_key) or (function_name and text == function_name):
            return str(case_key), function_name
    return text, ""


def _case_key_and_function_name(explicit_key: str, explicit_function: str, cases: dict[str, Any]) -> tuple[str, str]:
    if explicit_key and explicit_function:
        return explicit_key, explicit_function
    if explicit_key:
        case = cases.get(explicit_key)
        if isinstance(case, dict):
            return explicit_key, str(case.get("function_name") or "").strip()
    if explicit_function:
        for case_key, case in cases.items():
            if isinstance(case, dict) and str(case.get("function_name") or "").strip() == explicit_function:
                return str(case_key), explicit_function
    return explicit_key, explicit_function


def _append_function_case_requirement(required: list[dict[str, str]], case_key: Any, function_name: Any) -> None:
    key_text = str(case_key or "").strip()
    function_text = str(function_name or "").strip()
    if not function_text:
        return
    item = {"key": key_text, "function_name": function_text}
    if item not in required:
        required.append(item)


def _manual_function_case_code_blocks(payload: dict[str, Any]) -> list[str]:
    runtime = payload.get("pandas_function_case_runtime") if isinstance(payload.get("pandas_function_case_runtime"), dict) else {}
    blocks = runtime.get("manual_code_blocks") if isinstance(runtime.get("manual_code_blocks"), list) else []
    clean_blocks = [str(block).strip() for block in blocks if str(block or "").strip()]
    if clean_blocks:
        return clean_blocks
    manual = str(runtime.get("manual_text") or payload.get("specialized_functions_text") or "").strip()
    if not manual:
        return []
    fenced_blocks = re.findall(r"```(?:python|py)?\s*(.*?)```", manual, flags=re.IGNORECASE | re.DOTALL)
    clean_blocks = [str(block).strip() for block in fenced_blocks if str(block or "").strip()]
    if clean_blocks:
        return clean_blocks
    return [manual] if "def " in manual else []


def _function_definition_code(code: str, function_name: str) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ""
    lines = code.splitlines()
    parts: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            start = max((node.lineno or 1) - 1, 0)
            end = getattr(node, "end_lineno", None) or node.lineno
            parts.append("\n".join(lines[start:end]))
    return "\n\n".join(part for part in parts if part.strip())


def _called_function_names(code: str) -> set[str]:
    try:
        tree = ast.parse(_strip_harmless_pandas_import(code))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def _function_case_code_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(line) for line in value)
    return str(value or "").strip()


def _function_case_trace_from_locals(local_vars: dict[str, Any]) -> dict[str, Any]:
    trace: dict[str, Any] = {}
    for name in ("matched_conditions", "matched_conditions_df", "condition_trace", "function_case_trace"):
        if name in local_vars:
            trace[name] = _trace_value(local_vars[name])

    dataframes: dict[str, Any] = {}
    for name, value in local_vars.items():
        if name.startswith("__") or not hasattr(value, "attrs"):
            continue
        attrs = getattr(value, "attrs", {})
        if not isinstance(attrs, dict):
            continue
        matched_conditions = attrs.get("matched_conditions")
        if matched_conditions not in (None, "", [], {}):
            dataframes[name] = {"matched_conditions": _trace_value(matched_conditions)}
    if dataframes:
        trace["dataframe_attrs"] = dataframes

    step_outputs = local_vars.get("step_outputs")
    if isinstance(step_outputs, dict):
        step_trace = {}
        for key, value in step_outputs.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(marker in lowered for marker in ("condition", "trace", "mapping")):
                step_trace[key_text] = _trace_value(value)
        if step_trace:
            trace["step_outputs"] = step_trace
    return {key: value for key, value in trace.items() if value not in (None, "", [], {})}


def _trace_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        try:
            return _json_ready(value.head(100).to_dict(orient="records"))
        except TypeError:
            pass
    if isinstance(value, dict):
        return {str(key): _trace_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_trace_value(item) for item in list(value)[:100]]
    return _json_ready(value)


def _normalize_result_columns(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    result = frame.copy()
    rename_map: dict[str, str] = {}
    analysis_kind = plan.get("analysis_kind")
    rename_map.update(_dotted_result_column_renames(result, plan))

    for base_name in ["PRODUCTION", "WIP", "OUT_PLAN", "TARGET_QTY", "LOT_COUNT", "WF_QTY", "DIE_QTY", "PRESS_CNT"]:
        for suffix in ("_sum", "_total", "_quantity", "_qty"):
            alias = f"{base_name}{suffix}"
            if base_name not in result.columns and alias in result.columns:
                rename_map[alias] = base_name

    structural_alias_map = {
        "WIP": ["TOTAL_WIP", "WIP_TOTAL", "WIP_SUM", "SUM_WIP", "WIP_QUANTITY", "WIP_QTY"],
        "PRODUCTION": ["PRODUCTION_QUANTITY", "PRODUCTION_QTY"],
        "PRESS_CNT": ["TOTAL_PRESS_CNT", "PRESS_COUNT"],
        "WF_QTY": ["WAFER_QTY", "WAFER_COUNT", "WF_COUNT"],
        "DIE_QTY": ["DIE_COUNT"],
        "EQP_COUNT": ["EQUIPMENT_COUNT", "EQP_CNT"],
        "HOLD_LOT_COUNT": ["HOLD_COUNT", "HOLD_LOT_CNT", "LOT_HOLD_COUNT"],
        "AVG_IN_TAT": ["IN_TAT_AVG", "AVERAGE_IN_TAT", "MEAN_IN_TAT"],
    }
    for standard_name, aliases in structural_alias_map.items():
        if standard_name in result.columns:
            continue
        for alias in aliases:
            if alias in result.columns:
                rename_map[alias] = standard_name
                break
    if analysis_kind == "lot_quantity_summary" and "DIE_QTY" not in result.columns and "SUB_PROD_QTY" in result.columns:
        rename_map["SUB_PROD_QTY"] = "DIE_QTY"
    if analysis_kind == "top_wip_process_hold_lot_in_tat" and "HOLD_LOT_COUNT" not in result.columns and "LOT_COUNT" in result.columns:
        rename_map["LOT_COUNT"] = "HOLD_LOT_COUNT"
    if analysis_kind in {"lot_count_by_process", "top_wip_process_hold_lot_in_tat"} and "OPER_SHORT_DESC" not in result.columns and "OPER_NAME" in result.columns:
        rename_map["OPER_NAME"] = "OPER_SHORT_DESC"

    if analysis_kind == "rank_wip_then_join_production":
        if "WIP_RANK" not in result.columns and "rank" in result.columns:
            rename_map["rank"] = "WIP_RANK"
        if "PRODUCTION" not in result.columns and "PRODUCTION_total" in result.columns:
            rename_map["PRODUCTION_total"] = "PRODUCTION"

    alias_map = {
        "PRODUCTION": ["생산량", "생산 수량", "실적", "생산실적"],
        "WIP": ["재공", "재공 수량", "재공수량"],
        "OUT_PLAN": ["목표값", "목표", "생산계획", "계획", "OUT계획"],
        "TARGET_QTY": ["목표수량", "목표 수량", "계획수량", "계획 수량"],
        "ACHIEVEMENT_RATE": ["생산달성율", "생산달성률", "달성율", "달성률"],
        "BALANCE": ["차이수량", "부족수량", "미달수량"],
        "LOT_COUNT": ["Lot 수량", "LOT 수량", "lot 수량", "lot수량"],
    }
    for standard_name, aliases in alias_map.items():
        if standard_name in result.columns:
            continue
        for alias in aliases:
            if alias in result.columns:
                rename_map[alias] = standard_name
                break

    if rename_map:
        result = result.rename(columns=rename_map)
    if analysis_kind == "aggregate_wip_total" and "SCOPE" not in result.columns and "WIP" in result.columns:
        result.insert(0, "SCOPE", plan.get("scope_label") or "ALL")
    result = _add_result_scope_columns(result, plan)
    return _order_result_columns(result, plan)


def _dotted_result_column_renames(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, str]:
    aliases = {
        str(job.get("source_alias") or job.get("dataset_key") or "").strip().lower()
        for job in plan.get("retrieval_jobs", [])
        if isinstance(job, dict)
    }
    aliases = {alias for alias in aliases if alias}
    renames: dict[str, str] = {}
    existing = {str(column) for column in frame.columns}
    for column in frame.columns:
        column_text = str(column or "").strip()
        if "." not in column_text:
            continue
        prefix, metric = column_text.split(".", 1)
        prefix_key = prefix.strip().lower()
        metric_text = metric.strip()
        if not prefix_key or not metric_text or (aliases and prefix_key not in aliases):
            continue
        clean_prefix = re.sub(r"[^0-9A-Za-z]+", "_", prefix.strip()).strip("_").upper()
        clean_metric = re.sub(r"[^0-9A-Za-z]+", "_", metric_text).strip("_").upper()
        if not clean_metric:
            continue
        candidate = clean_prefix if clean_prefix.endswith(f"_{clean_metric}") or clean_prefix == clean_metric else f"{clean_prefix}_{clean_metric}"
        if candidate and candidate not in existing and candidate not in renames.values():
            renames[column_text] = candidate
    return renames


def _fallback_result_df(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> pd.DataFrame | None:
    if str(plan.get("analysis_kind") or "") == "rank_wip_then_join_production":
        ranked_join = _fallback_rank_wip_then_join_production(plan, runtime_sources)
        if ranked_join is not None:
            return ranked_join
    step_plan_result = _fallback_from_step_plan(plan, runtime_sources)
    if step_plan_result is not None:
        return step_plan_result
    if _is_top_wip_process_hold_lot_in_tat_plan(plan):
        return _fallback_top_wip_process_hold_lot_in_tat(plan, runtime_sources)
    if _is_top_wip_product_oldest_lot_plan(plan):
        return _fallback_top_wip_product_oldest_lot(plan, runtime_sources)
    if str(plan.get("analysis_kind") or "") == "aggregate_previous_source":
        alias = _primary_source_alias(plan, runtime_sources)
        rows = runtime_sources.get(alias) if alias else None
        if not isinstance(rows, list):
            return None
        frame = _source_dataframe(rows, [], str(plan.get("analysis_kind") or ""))
        frame = _standardize_source_frame_for_alias(frame, alias, plan)
        frame = _apply_source_filters_for_alias(frame, alias, plan)
        if frame.empty:
            return pd.DataFrame()
        step_plan = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
        first_step = step_plan[0] if step_plan and isinstance(step_plan[0], dict) else {}
        group_by_value = first_step.get("group_by") if isinstance(first_step.get("group_by"), list) else plan.get("product_grain", [])
        group_by = [str(column) for column in group_by_value if str(column) in frame.columns]
        metric = str(first_step.get("metric") or plan.get("metric") or "").strip()
        if not metric or metric not in frame.columns:
            return None
        clean = frame.copy()
        clean[metric] = pd.to_numeric(clean[metric], errors="coerce").fillna(0)
        if group_by:
            return clean.groupby(group_by, dropna=False, as_index=False)[metric].sum()
        return pd.DataFrame([{metric: clean[metric].sum()}])
    if str(plan.get("analysis_kind") or "") != "lot_quantity_summary":
        return None
    alias = _primary_source_alias(plan, runtime_sources)
    rows = runtime_sources.get(alias) if alias else None
    if not isinstance(rows, list):
        return None
    frame = _source_dataframe(rows, [], str(plan.get("analysis_kind") or ""))
    frame = _standardize_source_frame_for_alias(frame, alias, plan)
    frame = _apply_source_filters_for_alias(frame, alias, plan)
    lot_count = frame["LOT_ID"].nunique() if "LOT_ID" in frame.columns else 0
    wf_qty = frame["WF_QTY"].sum() if "WF_QTY" in frame.columns else 0
    die_source = "SUB_PROD_QTY" if "SUB_PROD_QTY" in frame.columns else "DIE_QTY"
    die_qty = frame[die_source].sum() if die_source in frame.columns else 0
    return pd.DataFrame([{"LOT_COUNT": lot_count, "WF_QTY": wf_qty, "DIE_QTY": die_qty}])


def _fallback_from_step_plan(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> pd.DataFrame | None:
    steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    if not steps:
        return None
    frames_by_step: dict[str, pd.DataFrame] = {}
    last_frame: pd.DataFrame | None = None
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return None
        operation = str(step.get("operation") or "").strip()
        if operation == "rank_top_n":
            frame = _fallback_step_rank_top_n(step, plan, runtime_sources, frames_by_step)
        elif operation in AGGREGATE_STEP_OPERATIONS:
            frame = _fallback_step_aggregate(step, plan, runtime_sources, frames_by_step)
        elif operation in {"equipment_count_by_product", "unique_count_by_group", "nunique_by_group"}:
            frame = _fallback_step_unique_count(step, plan, runtime_sources, frames_by_step)
        elif operation == "hold_lot_in_tat_by_process":
            frame = _fallback_step_hold_lot_in_tat(step, plan, runtime_sources, frames_by_step)
        elif operation == "left_join":
            frame = _fallback_step_left_join(step, frames_by_step)
        else:
            return None
        if frame is None:
            return None
        step_id = str(step.get("step_id") or f"step_{index + 1}")
        frames_by_step[step_id] = frame
        last_frame = frame
    if last_frame is None:
        return None
    output_columns = _step_output_columns(steps[-1]) or _step_output_columns({"output_columns": plan.get("analysis_output_columns")})
    return _select_step_columns(last_frame, output_columns)


def _fallback_step_rank_top_n(
    step: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, Any],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources, plan)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    metric = str(step.get("metric") or plan.get("metric") or "").strip()
    if not metric or metric not in frame.columns:
        return None
    work = frame.copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce").fillna(0)
    group_by = _available_columns(work, step.get("group_by"))
    if group_by:
        result = work.groupby(group_by, dropna=False, as_index=False)[metric].sum()
    else:
        result = work
    ascending = str(step.get("rank_order") or plan.get("rank_order") or "desc").lower() in {"asc", "ascending"}
    top_n = _top_n_for_step(step, plan)
    result = result.sort_values(metric, ascending=ascending).head(top_n)
    result = _apply_step_renames(result, step)
    return _select_step_columns(result, _step_output_columns(step))


def _fallback_step_aggregate(
    step: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, Any],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources, plan)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    metrics = _step_metric_columns(step, plan, frame)
    if not metrics:
        return None
    aggregation = _step_aggregation(step)
    if not aggregation:
        return None
    group_by = _available_columns(frame, step.get("group_by"))
    work = frame.copy()
    if aggregation in {"sum", "mean", "max", "min"}:
        for metric in metrics:
            work[metric] = pd.to_numeric(work[metric], errors="coerce")
        if aggregation == "sum":
            work[metrics] = work[metrics].fillna(0)
    if group_by:
        result = work.groupby(group_by, dropna=False, as_index=False)[metrics].agg(aggregation)
    else:
        result = pd.DataFrame([{metric: _aggregate_series(work[metric], aggregation) for metric in metrics}])
    result = _apply_metric_output_aliases(result, step, metrics, group_by)
    result = _apply_step_renames(result, step)
    return _select_step_columns(result, _step_output_columns(step))


def _collapse_over_detailed_aggregate_result(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    step = _final_aggregate_step(plan)
    if not step or frame.empty:
        return frame
    group_by = _available_columns(frame, step.get("group_by"))
    metrics = _aggregate_output_metrics_for_frame(frame, step, plan, group_by)
    if not metrics:
        return frame
    if group_by:
        if not frame.duplicated(subset=group_by, keep=False).any():
            return frame
        work = frame.copy()
        for metric in metrics:
            work[metric] = pd.to_numeric(work[metric], errors="coerce").fillna(0)
        collapsed = work.groupby(group_by, dropna=False, as_index=False)[metrics].sum()
    else:
        if len(frame) <= 1:
            return frame
        collapsed = pd.DataFrame(
            [
                {
                    metric: pd.to_numeric(frame[metric], errors="coerce").fillna(0).sum()
                    for metric in metrics
                }
            ]
        )
    output_columns = _step_output_columns(step) or _preferred_columns(plan) or list(collapsed.columns)
    return _select_step_columns(collapsed, [column for column in output_columns if column in collapsed.columns])


def _final_aggregate_step(plan: dict[str, Any]) -> dict[str, Any]:
    steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    if not steps:
        return {}
    final_step = steps[-1] if isinstance(steps[-1], dict) else {}
    if str(final_step.get("operation") or "").strip() in AGGREGATE_STEP_OPERATIONS:
        return final_step
    return {}


def _aggregate_output_metrics_for_frame(
    frame: pd.DataFrame,
    step: dict[str, Any],
    plan: dict[str, Any],
    group_by: list[str],
) -> list[str]:
    candidates: list[str] = []
    if isinstance(step.get("metrics"), list):
        candidates.extend(str(item) for item in step["metrics"] if str(item or "").strip())
    for key in ("metric", "value_column", "measure_column", "quantity_column"):
        value = str(step.get(key) or "").strip()
        if value:
            candidates.append(value)
    for column in _step_output_columns(step):
        if column not in group_by:
            candidates.append(column)
    if isinstance(plan.get("analysis_output_columns"), list):
        candidates.extend(
            column
            for column in _column_names_from_output_specs(plan["analysis_output_columns"])
            if column not in group_by
        )
    scope_columns = set(_result_scope_column_names(plan))
    return _unique_columns(
        [
            column
            for column in candidates
            if column in frame.columns
            and column not in group_by
            and column not in scope_columns
            and pd.api.types.is_numeric_dtype(pd.to_numeric(frame[column], errors="coerce"))
        ]
    )


def _fallback_step_unique_count(
    step: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, Any],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources, plan)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    count_column = str(step.get("count_column") or "").strip()
    if not count_column or count_column not in frame.columns:
        return None
    group_by = _available_columns(frame, step.get("group_by"))
    output_column = _count_output_column(step, group_by)
    if group_by:
        result = frame.groupby(group_by, dropna=False)[count_column].nunique().reset_index(name=output_column)
    else:
        result = pd.DataFrame([{output_column: frame[count_column].nunique()}])
    return _select_step_columns(result, _step_output_columns(step))


def _fallback_step_hold_lot_in_tat(
    step: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, Any],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources, plan)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    group_by = _available_columns(frame, step.get("group_by"))
    if not group_by:
        return None
    count_column = str(step.get("count_column") or "LOT_ID").strip()
    tat_column = str(step.get("tat_column") or "IN_TAT").strip()
    status_column = str(step.get("hold_status_column") or "LOT_HOLD_STAT_CD").strip()
    if count_column not in frame.columns or tat_column not in frame.columns:
        return None
    work = frame.copy()
    work[tat_column] = pd.to_numeric(work[tat_column], errors="coerce")
    base = work[group_by].drop_duplicates()
    if status_column in work.columns:
        status = work[status_column].astype(str).str.upper().str.replace(" ", "", regex=False)
        hold_mask = status.isin({"HOLD", "ONHOLD", "Y", "YES", "TRUE"})
    else:
        hold_mask = pd.Series(False, index=work.index)
    hold_counts = work[hold_mask].groupby(group_by, dropna=False)[count_column].nunique().reset_index(name="HOLD_LOT_COUNT")
    avg_in_tat = work.groupby(group_by, dropna=False)[tat_column].mean().reset_index(name="AVG_IN_TAT")
    result = base.merge(hold_counts, on=group_by, how="left").merge(avg_in_tat, on=group_by, how="left")
    result["HOLD_LOT_COUNT"] = result["HOLD_LOT_COUNT"].fillna(0).astype(int)
    return _select_step_columns(result, _step_output_columns(step))


def _fallback_step_left_join(step: dict[str, Any], frames_by_step: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    left_step = str(step.get("left_step") or "").strip()
    right_step = str(step.get("right_step") or "").strip()
    if not left_step or not right_step or left_step not in frames_by_step or right_step not in frames_by_step:
        return None
    left = frames_by_step[left_step]
    right = frames_by_step[right_step]
    join_keys = _step_join_keys(step, left, right)
    if not join_keys:
        return None
    result = left.merge(right, on=join_keys, how="left")
    for column in _step_output_columns(step):
        if column not in result.columns:
            result[column] = 0 if column.endswith("_COUNT") else None
    return _select_step_columns(result, _step_output_columns(step))


def _frame_for_step_source(step: dict[str, Any], runtime_sources: dict[str, Any], plan: dict[str, Any]) -> pd.DataFrame | None:
    alias = str(step.get("source_alias") or "").strip()
    if alias and alias in runtime_sources:
        rows = runtime_sources.get(alias)
        frame = _source_dataframe(rows if isinstance(rows, list) else [], [], str(plan.get("analysis_kind") or ""))
        frame = _standardize_source_frame_for_alias(frame, alias, plan)
        return _apply_source_filters_for_alias(frame, alias, plan)
    return None


def _filter_frame_from_previous_step(
    frame: pd.DataFrame,
    step: dict[str, Any],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    previous_step_id = str(step.get("filter_from_step") or "").strip()
    if not previous_step_id or previous_step_id not in frames_by_step:
        if not frames_by_step:
            return frame
        previous = next(reversed(frames_by_step.values()))
    else:
        previous = frames_by_step[previous_step_id]
    join_keys = _step_join_keys(step, frame, previous)
    if not join_keys:
        default_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "TSV_DIE_TYP"]
        join_keys = [column for column in default_keys if column in frame.columns and column in previous.columns]
    if not join_keys:
        return frame
    right_columns = join_keys + [column for column in previous.columns if column not in frame.columns]
    selected = previous[right_columns].drop_duplicates()
    return frame.merge(selected, on=join_keys, how="inner")


def _apply_source_filters_for_alias(frame: pd.DataFrame, alias: str, plan: dict[str, Any]) -> pd.DataFrame:
    filters = _filters_for_source_alias(plan, alias)
    if frame.empty or not filters:
        return frame
    result = frame.copy()
    for condition in filters:
        if not isinstance(condition, dict):
            continue
        field = str(condition.get("field") or "").strip()
        op = str(condition.get("op") or "eq").strip().lower()
        if not field or field == "PRODUCT_GRAIN" or op == "from_state":
            continue
        column = _filter_column_for_frame(result, field, alias, plan)
        if not column:
            continue
        values = condition.get("values")
        if values is None and "value" in condition:
            values = [condition.get("value")]
        values = values if isinstance(values, list) else [values]
        normalized_values = {_normalize_compare_value(value) for value in values}
        series = result[column]
        normalized_series = series.map(_normalize_compare_value)
        if op in {"eq", "="}:
            result = result[normalized_series.isin(normalized_values)]
        elif op == "in":
            result = result[normalized_series.isin(normalized_values)]
        elif op in {"ne", "!="}:
            result = result[~normalized_series.isin(normalized_values)]
        elif op == "not_in":
            result = result[~normalized_series.isin(normalized_values)]
        elif op in {"not_empty", "exists"}:
            result = result[series.notna() & (series.astype(str) != "")]
        elif op == "empty":
            result = result[series.isna() | (series.astype(str).str.strip() == "")]
        elif op in {"contains", "like"}:
            result = result[normalized_series.map(lambda value: any(target in value for target in normalized_values))]
        elif op == "starts_with":
            result = result[normalized_series.map(lambda value: any(value.startswith(target) for target in normalized_values))]
        elif op == "last_char_in":
            result = result[normalized_series.map(lambda value: bool(value) and value[-1:] in normalized_values)]
        elif op in {"gte", ">=", "gt", ">", "lte", "<=", "lt", "<"}:
            numeric_series = pd.to_numeric(series, errors="coerce")
            numeric_targets = [pd.to_numeric(value, errors="coerce") for value in values]
            numeric_targets = [value for value in numeric_targets if not pd.isna(value)]
            if not numeric_targets:
                continue
            target = numeric_targets[0]
            if op in {"gte", ">="}:
                result = result[numeric_series >= target]
            elif op in {"gt", ">"}:
                result = result[numeric_series > target]
            elif op in {"lte", "<="}:
                result = result[numeric_series <= target]
            elif op in {"lt", "<"}:
                result = result[numeric_series < target]
    return result


def _filters_for_source_alias(plan: dict[str, Any], alias: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_alias = str(job.get("source_alias") or job.get("dataset_key") or "").strip()
        if job_alias != alias:
            continue
        filters = job.get("filters") if isinstance(job.get("filters"), list) else []
        result.extend(deepcopy(item) for item in filters if isinstance(item, dict))
    return result


def _plan_has_pandas_source_filters(plan: dict[str, Any]) -> bool:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        for condition in job.get("filters", []) if isinstance(job.get("filters"), list) else []:
            if not isinstance(condition, dict):
                continue
            field = str(condition.get("field") or "").strip()
            op = str(condition.get("op") or "eq").strip().lower()
            if field and field != "PRODUCT_GRAIN" and op != "from_state":
                return True
    return False


def _filter_column_for_frame(frame: pd.DataFrame, field: str, alias: str, plan: dict[str, Any]) -> str:
    for candidate in _metadata_column_candidates_for_source(alias, plan, field):
        if candidate in frame.columns:
            return candidate
    return ""


def _metadata_column_candidates_for_source(alias: str, plan: dict[str, Any], column: str) -> list[str]:
    column_text = str(column or "").strip()
    if not column_text:
        return []
    candidates = [column_text]
    job = _job_for_source_alias(alias, plan)
    if isinstance(job, dict):
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mapping = job.get(field) if isinstance(job.get(field), dict) else {}
            mapped = mapping.get(column_text)
            if mapped is not None:
                if not isinstance(mapped, list):
                    mapped = [mapped]
                candidates.extend(str(item) for item in mapped if str(item or "").strip())
            for standard, mapped_candidates in mapping.items():
                mapped_list = mapped_candidates if isinstance(mapped_candidates, list) else [mapped_candidates]
                if column_text in [str(item) for item in mapped_list if str(item or "").strip()]:
                    candidates.append(str(standard))
    return _unique_columns(candidates)


def _normalize_compare_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _step_join_keys(step: dict[str, Any], left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    raw_keys = step.get("join_keys") if isinstance(step.get("join_keys"), list) else []
    if not raw_keys and step.get("join_key"):
        raw_keys = [step.get("join_key")]
    return [str(key) for key in raw_keys if str(key) in left.columns and str(key) in right.columns]


def _available_columns(frame: pd.DataFrame, columns: Any) -> list[str]:
    return [str(column) for column in columns if str(column) in frame.columns] if isinstance(columns, list) else []


def _step_metric_columns(step: dict[str, Any], plan: dict[str, Any], frame: pd.DataFrame) -> list[str]:
    raw_metrics = step.get("metrics") if isinstance(step.get("metrics"), list) else []
    candidates: list[Any] = list(raw_metrics)
    for key in ("metric", "value_column", "measure_column", "quantity_column"):
        if step.get(key):
            candidates.append(step.get(key))
    if isinstance(plan.get("metrics"), list):
        candidates.extend(plan.get("metrics", []))
    if plan.get("metric"):
        candidates.append(plan.get("metric"))
    if not candidates:
        group_by = set(_available_columns(frame, step.get("group_by")))
        output_columns = _step_output_columns(step) or _step_output_columns({"output_columns": plan.get("analysis_output_columns")})
        candidates.extend(column for column in output_columns if str(column) not in group_by)
    return _unique_columns([str(column) for column in candidates if str(column) in frame.columns])


def _step_aggregation(step: dict[str, Any]) -> str:
    raw_value = str(step.get("aggregation") or step.get("agg") or step.get("agg_func") or "sum").strip().lower()
    aliases = {
        "avg": "mean",
        "average": "mean",
        "count_distinct": "nunique",
        "distinct_count": "nunique",
        "total": "sum",
        "unique_count": "nunique",
    }
    value = aliases.get(raw_value, raw_value)
    return value if value in {"count", "max", "mean", "min", "nunique", "sum"} else ""


def _aggregate_series(series: pd.Series, aggregation: str) -> Any:
    if aggregation == "sum":
        return pd.to_numeric(series, errors="coerce").fillna(0).sum()
    if aggregation == "mean":
        return pd.to_numeric(series, errors="coerce").mean()
    if aggregation == "max":
        return pd.to_numeric(series, errors="coerce").max()
    if aggregation == "min":
        return pd.to_numeric(series, errors="coerce").min()
    if aggregation == "count":
        return series.count()
    if aggregation == "nunique":
        return series.nunique()
    return None


def _apply_metric_output_aliases(
    frame: pd.DataFrame,
    step: dict[str, Any],
    metrics: list[str],
    group_by: list[str],
) -> pd.DataFrame:
    if len(metrics) != 1:
        return frame
    metric = metrics[0]
    output_column = str(step.get("output_column") or "").strip()
    if output_column and output_column not in frame.columns:
        return frame.rename(columns={metric: output_column})
    output_columns = _step_output_columns(step)
    metric_outputs = [column for column in output_columns if column not in group_by]
    if len(metric_outputs) == 1 and metric_outputs[0] != metric and metric_outputs[0] not in frame.columns:
        return frame.rename(columns={metric: metric_outputs[0]})
    return frame
def _top_n_for_step(step: dict[str, Any], plan: dict[str, Any]) -> int:
    value = step.get("top_n", plan.get("top_n", 1))
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return 1


def _apply_step_renames(frame: pd.DataFrame, step: dict[str, Any]) -> pd.DataFrame:
    renames = step.get("rename_columns") if isinstance(step.get("rename_columns"), dict) else {}
    if not renames:
        return frame
    return frame.rename(columns={str(source): str(target) for source, target in renames.items()})


def _step_output_columns(step: dict[str, Any]) -> list[str]:
    columns = step.get("output_columns") if isinstance(step.get("output_columns"), list) else []
    return _column_names_from_output_specs(columns)


def _column_names_from_output_specs(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        column = _column_name_from_output_spec(value)
        if column and column not in result:
            result.append(column)
    return result


def _column_name_from_output_spec(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("output_column", "column", "name"):
            column = str(value.get(key) or "").strip()
            if column:
                return column
        return ""
    return str(value or "").strip()


def _select_step_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if not columns:
        return frame
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = 0 if column.endswith("_COUNT") else None
    return result[columns]


def _count_output_column(step: dict[str, Any], group_by: list[str]) -> str:
    explicit = str(step.get("output_column") or "").strip()
    if explicit:
        return explicit
    for column in _step_output_columns(step):
        if column not in group_by:
            return column
    return "COUNT"


def _should_replace_empty_generated_result(result_df: pd.DataFrame, fallback_df: pd.DataFrame | None) -> bool:
    return bool(result_df.empty and fallback_df is not None and not fallback_df.empty)


def _should_replace_incomplete_generated_result(
    result_df: pd.DataFrame,
    fallback_df: pd.DataFrame | None,
    plan: dict[str, Any],
) -> bool:
    if fallback_df is None or fallback_df.empty:
        return False
    required = _preferred_columns(plan)
    if not required and isinstance(plan.get("analysis_output_columns"), list):
        required = _column_names_from_output_specs(plan["analysis_output_columns"])
    if not required:
        return False
    return any(column not in result_df.columns for column in required)


def _should_replace_filter_mismatched_generated_result(
    result_df: pd.DataFrame,
    fallback_df: pd.DataFrame | None,
    plan: dict[str, Any],
) -> bool:
    if not _plan_has_pandas_source_filters(plan) or fallback_df is None or fallback_df.empty:
        return False
    return not _frames_equal_on_fallback_columns(result_df, fallback_df)


def _frames_equal_on_fallback_columns(result_df: pd.DataFrame, fallback_df: pd.DataFrame) -> bool:
    fallback_columns = [str(column) for column in fallback_df.columns]
    if any(column not in result_df.columns for column in fallback_columns):
        return False
    left = result_df[fallback_columns].reset_index(drop=True)
    right = fallback_df[fallback_columns].reset_index(drop=True)
    if len(left) != len(right):
        return False
    return _json_ready(left.to_dict(orient="records")) == _json_ready(right.to_dict(orient="records"))


def _fallback_rank_wip_then_join_production(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> pd.DataFrame | None:
    rank_groups = _rank_groups_for_plan(plan)
    if not rank_groups:
        return None
    wip_alias = _source_alias_for_dataset(plan, runtime_sources, "wip")
    production_alias = _source_alias_for_dataset(plan, runtime_sources, "production")
    if not wip_alias or not production_alias:
        return None
    wip_rows = runtime_sources.get(wip_alias)
    production_rows = runtime_sources.get(production_alias)
    if not isinstance(wip_rows, list) or not isinstance(production_rows, list):
        return None

    wip_df = _source_dataframe(wip_rows, [], str(plan.get("analysis_kind") or ""))
    production_df = _source_dataframe(production_rows, [], str(plan.get("analysis_kind") or ""))
    wip_df = _standardize_source_frame_for_alias(wip_df, wip_alias, plan)
    production_df = _standardize_source_frame_for_alias(production_df, production_alias, plan)
    wip_df = _apply_source_filters_for_alias(wip_df, wip_alias, plan)
    production_df = _apply_source_filters_for_alias(production_df, production_alias, plan)
    if wip_df.empty or "WIP" not in wip_df.columns:
        return pd.DataFrame(columns=_preferred_columns(plan))

    wip_df = _assign_rank_group(wip_df, rank_groups)
    if "RANK_GROUP" not in wip_df.columns:
        return None
    wip_df = wip_df[wip_df["RANK_GROUP"].notna() & (wip_df["RANK_GROUP"].astype(str) != "")]
    if wip_df.empty:
        return pd.DataFrame(columns=_preferred_columns(plan))

    product_keys = _rank_join_product_keys(plan, wip_df, production_df)
    if not product_keys:
        return None
    rank_step = _rank_step_for_plan(plan)
    top_n = _top_n_for_step(rank_step, plan)
    ascending = str(rank_step.get("rank_order") or plan.get("rank_order") or "desc").lower() in {"asc", "ascending"}

    wip_work = wip_df.copy()
    wip_work["WIP"] = pd.to_numeric(wip_work["WIP"], errors="coerce").fillna(0)
    ranked = (
        wip_work.groupby(["RANK_GROUP", *product_keys], dropna=False, as_index=False)["WIP"]
        .sum()
        .sort_values(["RANK_GROUP", "WIP"], ascending=[True, ascending])
    )
    ranked["WIP_RANK"] = ranked.groupby("RANK_GROUP")["WIP"].rank(method="first", ascending=ascending).astype(int)
    ranked = ranked[ranked["WIP_RANK"] <= top_n]
    if ranked.empty:
        return pd.DataFrame(columns=["RANK_GROUP", "WIP_RANK", *product_keys, "WIP", "PRODUCTION"])

    if production_df.empty or "PRODUCTION" not in production_df.columns:
        ranked["PRODUCTION"] = 0
    else:
        production_work = _assign_rank_group(production_df.copy(), rank_groups)
        if "RANK_GROUP" in production_work.columns:
            production_work = production_work[
                production_work["RANK_GROUP"].notna() & (production_work["RANK_GROUP"].astype(str) != "")
            ]
            production_keys = ["RANK_GROUP", *product_keys]
        else:
            production_keys = product_keys
        production_work["PRODUCTION"] = pd.to_numeric(production_work["PRODUCTION"], errors="coerce").fillna(0)
        product_scope = ranked[["RANK_GROUP", *product_keys]].drop_duplicates()
        merge_keys = [key for key in production_keys if key in production_work.columns and key in product_scope.columns]
        if merge_keys:
            production_work = production_work.merge(product_scope[merge_keys].drop_duplicates(), on=merge_keys, how="inner")
        production_sum = (
            production_work.groupby(production_keys, dropna=False, as_index=False)["PRODUCTION"].sum()
            if production_keys
            else pd.DataFrame([{"PRODUCTION": production_work["PRODUCTION"].sum()}])
        )
        join_keys = [key for key in ["RANK_GROUP", *product_keys] if key in ranked.columns and key in production_sum.columns]
        ranked = ranked.merge(production_sum, on=join_keys, how="left") if join_keys else ranked
        if "PRODUCTION" not in ranked.columns:
            ranked["PRODUCTION"] = 0
        ranked["PRODUCTION"] = pd.to_numeric(ranked["PRODUCTION"], errors="coerce").fillna(0)

    ranked["WIP_RANK"] = ranked["WIP_RANK"].astype(int)
    ranked = ranked.sort_values(["RANK_GROUP", "WIP_RANK"], ascending=[True, True])
    columns = ["RANK_GROUP", "WIP_RANK", *product_keys, "WIP", "PRODUCTION"]
    return ranked[columns]


def _rank_groups_for_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    if isinstance(plan.get("rank_groups"), list):
        candidates.extend(plan["rank_groups"])
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if isinstance(step, dict) and isinstance(step.get("rank_groups"), list):
            candidates.extend(step["rank_groups"])
    result: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        field = str(item.get("field") or "OPER_NAME").strip()
        values = [str(value or "").strip() for value in item.get("values", []) if str(value or "").strip()]
        if label and field and values:
            result.append({"label": label, "field": field, "values": values})
    return result


def _assign_rank_group(frame: pd.DataFrame, rank_groups: list[dict[str, Any]]) -> pd.DataFrame:
    result = frame.copy()
    if result.empty or not rank_groups:
        return result
    result["RANK_GROUP"] = None
    for group in rank_groups:
        field = str(group.get("field") or "").strip()
        if field not in result.columns:
            continue
        values = {str(value or "").strip().upper() for value in group.get("values", []) if str(value or "").strip()}
        if not values:
            continue
        mask = result[field].astype(str).str.strip().str.upper().isin(values)
        result.loc[mask, "RANK_GROUP"] = str(group.get("label") or "").strip()
    return result


def _rank_join_product_keys(plan: dict[str, Any], wip_df: pd.DataFrame, production_df: pd.DataFrame) -> list[str]:
    plan_keys = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    process_columns = {"OPER_NAME", "OPER_SHORT_DESC", "OPER_ID", "OPER_DESC", "OPER_NUM"}
    candidates = [
        str(column)
        for column in plan_keys
        if str(column or "").strip() and str(column) not in process_columns and str(column) in wip_df.columns
    ]
    shared = [column for column in candidates if production_df.empty or column in production_df.columns]
    if shared:
        return shared
    default_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "TSV_DIE_TYP"]
    return [column for column in default_keys if column in wip_df.columns and (production_df.empty or column in production_df.columns)]


def _rank_step_for_plan(plan: dict[str, Any]) -> dict[str, Any]:
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if not isinstance(step, dict):
            continue
        operation = str(step.get("operation") or "")
        metric = str(step.get("metric") or "").upper()
        if operation in {"rank_top_n", "rank_bottom_n", "rank_top_n_per_filter_group"} or metric == "WIP":
            return step
    return {}


def _fallback_top_wip_process_hold_lot_in_tat(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> pd.DataFrame:
    wip_alias = _source_alias_for_dataset(plan, runtime_sources, "wip")
    lot_alias = _source_alias_for_dataset(plan, runtime_sources, "lot")
    wip_rows = runtime_sources.get(wip_alias) if wip_alias else None
    lot_rows = runtime_sources.get(lot_alias) if lot_alias else None
    if not isinstance(wip_rows, list) or not isinstance(lot_rows, list):
        return pd.DataFrame()

    wip_df = _source_dataframe(wip_rows, [], str(plan.get("analysis_kind") or ""))
    lot_df = _source_dataframe(lot_rows, [], str(plan.get("analysis_kind") or ""))
    wip_df = _standardize_source_frame_for_alias(wip_df, wip_alias, plan)
    lot_df = _standardize_source_frame_for_alias(lot_df, lot_alias, plan)
    wip_df = _apply_source_filters_for_alias(wip_df, wip_alias, plan)
    lot_df = _apply_source_filters_for_alias(lot_df, lot_alias, plan)
    if wip_df.empty or "WIP" not in wip_df.columns:
        return pd.DataFrame()

    wip_process_column = _process_column(wip_df)
    if not wip_process_column:
        return pd.DataFrame()

    top_n = _top_n_for_process_plan(plan)
    wip_work = wip_df.copy()
    wip_work["OPER_SHORT_DESC"] = wip_work[wip_process_column].astype(str)
    wip_work["WIP"] = pd.to_numeric(wip_work["WIP"], errors="coerce").fillna(0)
    ranked = (
        wip_work.groupby("OPER_SHORT_DESC", dropna=False, as_index=False)["WIP"]
        .sum()
        .sort_values("WIP", ascending=False)
        .head(top_n)
    )
    if ranked.empty:
        return pd.DataFrame(columns=["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"])

    if lot_df.empty:
        ranked["HOLD_LOT_COUNT"] = 0
        ranked["AVG_IN_TAT"] = None
        return ranked[["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]]

    lot_process_column = _process_column(lot_df)
    if not lot_process_column:
        ranked["HOLD_LOT_COUNT"] = 0
        ranked["AVG_IN_TAT"] = None
        return ranked[["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]]

    selected_processes = set(ranked["OPER_SHORT_DESC"].astype(str))
    lot_work = lot_df.copy()
    lot_work["OPER_SHORT_DESC"] = lot_work[lot_process_column].astype(str)
    lot_work = lot_work[lot_work["OPER_SHORT_DESC"].isin(selected_processes)].copy()
    if lot_work.empty:
        ranked["HOLD_LOT_COUNT"] = 0
        ranked["AVG_IN_TAT"] = None
        return ranked[["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]]

    lot_work["IN_TAT"] = pd.to_numeric(lot_work["IN_TAT"], errors="coerce") if "IN_TAT" in lot_work.columns else None
    status = lot_work["LOT_HOLD_STAT_CD"].astype(str).str.upper().str.replace(" ", "", regex=False) if "LOT_HOLD_STAT_CD" in lot_work.columns else pd.Series("", index=lot_work.index)
    hold_mask = status.isin({"HOLD", "ONHOLD", "Y", "YES", "TRUE"})
    lot_id_column = "LOT_ID" if "LOT_ID" in lot_work.columns else ""
    if lot_id_column:
        hold_counts = lot_work[hold_mask].groupby("OPER_SHORT_DESC")[lot_id_column].nunique()
    else:
        hold_counts = lot_work[hold_mask].groupby("OPER_SHORT_DESC").size()
    avg_in_tat = lot_work.groupby("OPER_SHORT_DESC")["IN_TAT"].mean() if "IN_TAT" in lot_work.columns else pd.Series(dtype="float64")
    metrics = pd.DataFrame({"OPER_SHORT_DESC": list(selected_processes)})
    metrics["HOLD_LOT_COUNT"] = metrics["OPER_SHORT_DESC"].map(hold_counts).fillna(0).astype(int)
    metrics["AVG_IN_TAT"] = metrics["OPER_SHORT_DESC"].map(avg_in_tat)

    result = ranked.merge(metrics, on="OPER_SHORT_DESC", how="left")
    result["HOLD_LOT_COUNT"] = result["HOLD_LOT_COUNT"].fillna(0).astype(int)
    return result[["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]]


def _process_column(frame: pd.DataFrame) -> str:
    for column in ["OPER_SHORT_DESC", "OPER_NAME", "OPER_ID"]:
        if column in frame.columns:
            return column
    return ""


def _top_n_for_process_plan(plan: dict[str, Any]) -> int:
    if isinstance(plan.get("top_n"), int) and plan["top_n"] > 0:
        return int(plan["top_n"])
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if not isinstance(step, dict):
            continue
        value = step.get("top_n")
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    return 3


def _fallback_top_wip_product_oldest_lot(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> pd.DataFrame:
    wip_alias = _source_alias_for_dataset(plan, runtime_sources, "wip")
    lot_alias = _source_alias_for_dataset(plan, runtime_sources, "lot")
    wip_rows = runtime_sources.get(wip_alias) if wip_alias else None
    lot_rows = runtime_sources.get(lot_alias) if lot_alias else None
    if not isinstance(wip_rows, list) or not isinstance(lot_rows, list):
        return pd.DataFrame()
    wip_df = _source_dataframe(wip_rows, [], str(plan.get("analysis_kind") or ""))
    lot_df = _source_dataframe(lot_rows, [], str(plan.get("analysis_kind") or ""))
    wip_df = _standardize_source_frame_for_alias(wip_df, wip_alias, plan)
    lot_df = _standardize_source_frame_for_alias(lot_df, lot_alias, plan)
    wip_df = _apply_source_filters_for_alias(wip_df, wip_alias, plan)
    lot_df = _apply_source_filters_for_alias(lot_df, lot_alias, plan)
    if wip_df.empty or lot_df.empty or "WIP" not in wip_df.columns or "IN_TAT" not in lot_df.columns or "LOT_ID" not in lot_df.columns:
        return pd.DataFrame()

    product_keys = _shared_product_keys(plan, wip_df, lot_df)
    if not product_keys:
        return pd.DataFrame()

    wip_work = wip_df.copy()
    wip_work["WIP"] = pd.to_numeric(wip_work["WIP"], errors="coerce").fillna(0)
    top_product = (
        wip_work.groupby(product_keys, dropna=False, as_index=False)["WIP"]
        .sum()
        .sort_values("WIP", ascending=False)
        .head(1)
    )
    if top_product.empty:
        return pd.DataFrame()

    lot_work = lot_df.copy()
    mask = pd.Series(True, index=lot_work.index)
    top_row = top_product.iloc[0]
    for column in product_keys:
        mask = mask & (lot_work[column].astype(str) == str(top_row[column]))
    lot_work = lot_work[mask].copy()
    if lot_work.empty:
        return pd.DataFrame(columns=[*product_keys, "WIP", "LOT_ID", "IN_TAT"])
    lot_work["IN_TAT"] = pd.to_numeric(lot_work["IN_TAT"], errors="coerce")
    lot_work = lot_work.sort_values("IN_TAT", ascending=False).head(1)
    lot_work["WIP"] = top_row["WIP"]
    for column in product_keys:
        lot_work[column] = top_row[column]
    return lot_work[[*product_keys, "WIP", "LOT_ID", "IN_TAT"]]


def _source_alias_for_dataset(plan: dict[str, Any], runtime_sources: dict[str, Any], token: str) -> str:
    for job in plan.get("retrieval_jobs", []) if isinstance(plan.get("retrieval_jobs"), list) else []:
        if not isinstance(job, dict):
            continue
        text = " ".join(str(job.get(key) or "") for key in ("dataset_key", "source_alias", "purpose")).lower()
        if token in text:
            alias = str(job.get("source_alias") or job.get("dataset_key") or "")
            if alias in runtime_sources:
                return alias
    for alias in runtime_sources:
        if token in str(alias).lower():
            return str(alias)
    return ""


def _shared_product_keys(plan: dict[str, Any], wip_df: pd.DataFrame, lot_df: pd.DataFrame) -> list[str]:
    plan_keys = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    candidates = [str(column) for column in plan_keys if str(column) in wip_df.columns and str(column) in lot_df.columns]
    if candidates:
        return candidates
    default_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "TSV_DIE_TYP"]
    return [column for column in default_keys if column in wip_df.columns and column in lot_df.columns]


def _is_top_wip_product_oldest_lot_plan(plan: dict[str, Any]) -> bool:
    kind = str(plan.get("analysis_kind") or "").lower()
    if kind == "top_wip_process_hold_lot_in_tat":
        return False
    if kind in {
        "top_wip_product_oldest_lot",
        "wip_top_product_oldest_lot",
        "top_wip_product_lot_in_tat",
        "oldest_lot_for_top_wip_product",
    }:
        return True
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    has_wip = any(_job_text_contains(job, "wip") for job in jobs if isinstance(job, dict))
    has_lot = any(_job_text_contains(job, "lot") for job in jobs if isinstance(job, dict))
    step_text = json.dumps(plan.get("step_plan") or [], ensure_ascii=False).lower()
    return has_wip and has_lot and "in_tat" in step_text and "wip" in step_text


def _is_top_wip_process_hold_lot_in_tat_plan(plan: dict[str, Any]) -> bool:
    kind = str(plan.get("analysis_kind") or "").lower()
    if kind == "top_wip_process_hold_lot_in_tat":
        return True
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    has_wip = any(_job_text_contains(job, "wip") for job in jobs if isinstance(job, dict))
    has_lot = any(_job_text_contains(job, "lot") for job in jobs if isinstance(job, dict))
    columns = plan.get("analysis_output_columns") if isinstance(plan.get("analysis_output_columns"), list) else []
    column_text = " ".join(str(column).upper() for column in columns)
    return has_wip and has_lot and "HOLD_LOT_COUNT" in column_text and "AVG_IN_TAT" in column_text


def _job_text_contains(job: dict[str, Any], token: str) -> bool:
    text = " ".join(str(job.get(key) or "") for key in ("dataset_key", "source_alias", "purpose")).lower()
    return token in text


def _primary_source_alias(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> str:
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if isinstance(step, dict) and step.get("source_alias") in runtime_sources:
            return str(step["source_alias"])
    for alias in runtime_sources:
        return str(alias)
    return ""


def _order_result_columns(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    preferred = _final_step_output_columns(plan) or _preferred_columns(plan)
    if not preferred and isinstance(plan.get("analysis_output_columns"), list):
        preferred = _column_names_from_output_specs(plan["analysis_output_columns"])
    scope_columns = [column for column in _result_scope_column_names(plan) if column in frame.columns]
    if scope_columns:
        preferred = _unique_columns([*scope_columns, *preferred])
    if not preferred:
        return frame
    ordered = [column for column in preferred if column in frame.columns]
    remaining = [column for column in frame.columns if column not in ordered]
    return frame[ordered + remaining]


def _add_result_scope_columns(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    scope_columns = plan.get("result_scope_columns") if isinstance(plan.get("result_scope_columns"), list) else []
    if not scope_columns:
        return frame
    result = frame.copy()
    for item in reversed(scope_columns):
        if not isinstance(item, dict):
            continue
        column = str(item.get("column") or "").strip()
        value = item.get("value")
        if not column or column in result.columns or value in (None, ""):
            continue
        result.insert(0, column, value)
    return result


def _result_scope_column_names(plan: dict[str, Any]) -> list[str]:
    scope_columns = plan.get("result_scope_columns") if isinstance(plan.get("result_scope_columns"), list) else []
    result: list[str] = []
    for item in scope_columns:
        if not isinstance(item, dict):
            continue
        column = str(item.get("column") or "").strip()
        if column and column not in result:
            result.append(column)
    return result


def _final_step_output_columns(plan: dict[str, Any]) -> list[str]:
    steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    if not steps:
        return []
    final_step = steps[-1] if isinstance(steps[-1], dict) else {}
    return _step_output_columns(final_step)


def _product_key_columns(plan: dict[str, Any], columns: list[Any]) -> list[str]:
    available = [str(column) for column in columns]
    plan_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    if plan_grain:
        return [str(column) for column in plan_grain if str(column) in available]
    default_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "TSV_DIE_TYP"]
    return [column for column in default_keys if column in available]


def _product_key_values(rows: list[dict[str, Any]], product_key_columns: list[str]) -> list[dict[str, Any]]:
    if not product_key_columns:
        return []
    values: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        product = {key: row.get(key) for key in product_key_columns if row.get(key) not in {None, ""}}
        if product and product not in values:
            values.append(product)
    return values


def _preferred_columns(plan: dict[str, Any]) -> list[str]:
    product_keys = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    kind = plan.get("analysis_kind")
    if kind == "rank_wip_then_join_production":
        return ["RANK_GROUP", "WIP_RANK", *product_keys, "WIP", "PRODUCTION"]
    if kind == "aggregate_join":
        return [*product_keys, "PRODUCTION", "WIP"]
    if kind == "production_wip_target_rate":
        return [*product_keys, "WIP", "PRODUCTION", "OUT_PLAN", "ACHIEVEMENT_RATE"]
    if kind == "low_output_vs_target":
        return [*product_keys, "PRODUCTION", "TARGET_QTY", "ACHIEVEMENT_RATE", "BALANCE", "LOW_OUTPUT_FLAG"]
    if kind == "lot_count_by_process":
        return ["OPER_SHORT_DESC", "LOT_COUNT"]
    if kind == "top_wip_process_hold_lot_in_tat":
        return ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]
    if kind == "lot_quantity_summary":
        return ["LOT_COUNT", "WF_QTY", "DIE_QTY"]
    if kind == "aggregate_wip_total":
        return ["SCOPE", "WIP"]
    if kind == "overall_production_wip_target":
        return ["SCOPE", "PRODUCTION", "WIP", "OUT_PLAN"]
    if kind == "date_split_production_plan_gap":
        return [*product_keys, "PRODUCTION", "OUT_PLAN", "BALANCE"]
    if kind == "equipment_by_model":
        return ["EQP_MODEL", "EQP_COUNT", "PRESS_CNT"]
    if kind == "equipment_count_for_previous_products":
        return [*product_keys, "EQP_COUNT"]
    if _is_top_wip_product_oldest_lot_plan(plan):
        return [*product_keys, "WIP", "LOT_ID", "IN_TAT"]
    return []


def _source_dataframe(
    rows: list[dict[str, Any]],
    required_columns: list[str] | None = None,
    analysis_kind: str = "",
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=[str(column) for column in (required_columns or [])])
    return frame


def _required_columns_by_alias(plan: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for job in plan.get("retrieval_jobs", []) if isinstance(plan.get("retrieval_jobs"), list) else []:
        if not isinstance(job, dict):
            continue
        alias = str(job.get("source_alias") or job.get("dataset_key") or "")
        columns = job.get("required_columns") if isinstance(job.get("required_columns"), list) else []
        if alias:
            result[alias] = _unique_columns([str(column) for column in columns if str(column or "").strip()])
    return result


def _standardize_source_frame_for_alias(frame: pd.DataFrame, alias: str, plan: dict[str, Any]) -> pd.DataFrame:
    aliases = _standard_aliases_for_source(alias, plan)
    if not aliases:
        return frame
    result = frame.copy()
    for standard, candidates in aliases.items():
        standard_text = str(standard or "").strip()
        if not standard_text:
            continue
        candidate_columns = [
            str(candidate)
            for candidate in candidates
            if str(candidate or "").strip()
            and str(candidate) != standard_text
            and str(candidate) in result.columns
        ]
        if not candidate_columns:
            continue
        if standard_text in result.columns:
            for candidate in candidate_columns:
                if candidate in result.columns:
                    result[standard_text] = _fill_blank_series(result[standard_text], result[candidate])
            result = result.drop(columns=[column for column in candidate_columns if column in result.columns], errors="ignore")
            continue
        rename_source = candidate_columns[0]
        result = result.rename(columns={rename_source: standard_text})
        drop_columns = [column for column in candidate_columns[1:] if column in result.columns]
        if drop_columns:
            result = result.drop(columns=drop_columns, errors="ignore")
    return result


def _fill_blank_series(base: pd.Series, fallback: pd.Series) -> pd.Series:
    blank_mask = base.isna() | (base.astype(str).str.strip() == "")
    return base.where(~blank_mask, fallback)


def _standard_aliases_for_source(alias: str, plan: dict[str, Any]) -> dict[str, list[str]]:
    job = _job_for_source_alias(alias, plan)
    aliases: dict[str, list[str]] = {}
    standard_candidates = _standard_columns_from_plan(plan)
    if isinstance(job, dict):
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mapping = job.get(field) if isinstance(job.get(field), dict) else {}
            for standard, candidates in mapping.items():
                standard_text = str(standard or "").strip()
                if not standard_text or standard_text not in standard_candidates:
                    continue
                if not isinstance(candidates, list):
                    candidates = [candidates]
                aliases.setdefault(standard_text, [])
                aliases[standard_text].extend(str(item) for item in candidates if str(item or "").strip())
    return {key: _unique_columns([item for item in values if item != key]) for key, values in aliases.items()}


def _job_for_source_alias(alias: str, plan: dict[str, Any]) -> dict[str, Any]:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_alias = str(job.get("source_alias") or job.get("dataset_key") or "")
        if job_alias == alias:
            return job
    return {}


def _standard_columns_from_plan(plan: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    for key in ("product_grain", "analysis_output_columns"):
        value = plan.get(key)
        if isinstance(value, list):
            columns.extend(_column_names_from_output_specs(value))
    steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        for key in ("group_by", "join_keys", "output_columns"):
            value = step.get(key)
            if isinstance(value, list):
                columns.extend(_column_names_from_output_specs(value))
        for key in ("metric", "target_column", "count_column"):
            value = str(step.get(key) or "").strip()
            if value:
                columns.append(value)
    for key in ("metric", "target_column", "production_column"):
        value = str(plan.get(key) or "").strip()
        if value:
            columns.append(value)
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        required_columns = job.get("required_columns") if isinstance(job.get("required_columns"), list) else []
        columns.extend(str(item) for item in required_columns if str(item or "").strip())
        params = job.get("params") if isinstance(job.get("params"), dict) else {}
        columns.extend(str(key) for key in params.keys() if str(key or "").strip())
        filters = job.get("filters") if isinstance(job.get("filters"), list) else []
        for condition in filters:
            if not isinstance(condition, dict):
                continue
            field = str(condition.get("field") or "").strip()
            if field and field != "PRODUCT_GRAIN":
                columns.append(field)
    return _unique_columns(columns)


def _runtime_source_column_errors(plan: dict[str, Any], runtime_sources: dict[str, Any]) -> list[str]:
    required_columns_by_alias = _required_columns_by_alias(plan)
    errors: list[str] = []
    for alias, required_columns in required_columns_by_alias.items():
        rows = runtime_sources.get(alias)
        if not isinstance(rows, list) or not rows:
            continue
        present_columns: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                present_columns.update(str(column) for column in row.keys())
        missing = [
            column
            for column in required_columns
            if not any(candidate in present_columns for candidate in _metadata_column_candidates_for_source(alias, plan, column))
        ]
        if missing:
            errors.append(f"Runtime source '{alias}' is missing required columns: {', '.join(missing)}")
    return errors


def _unique_columns(columns: list[str]) -> list[str]:
    result = []
    for column in columns:
        if column not in result:
            result.append(column)
    return result


def _strip_harmless_pandas_import(code: str) -> str:
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped in {"import pandas as pd", "import pandas"}:
            continue
        lines.append(line)
    return _rewrite_pandas_compatibility("\n".join(lines).strip())


def _rewrite_pandas_compatibility(code: str) -> str:
    # Some LLMs emit NumPy-style infinity through pandas. pandas 2.x has no pd.inf.
    return re.sub(r"(?<![\w.])pd\.inf\b", 'float("inf")', code, flags=re.IGNORECASE)


def _check_code_safety(code: str) -> list[str]:
    if not code:
        return ["Generated pandas code is empty."]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"Generated pandas code has syntax error: {exc}"]

    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            errors.append("Imports are not allowed in generated pandas code.")
            if any(alias.name.split(".", 1)[0] == "datetime" for alias in node.names):
                errors.append("Use pd.to_datetime and pandas string/date operations instead of importing datetime.")
        if isinstance(node, ast.ImportFrom):
            errors.append("Imports are not allowed in generated pandas code.")
            if str(node.module or "").split(".", 1)[0] == "datetime":
                errors.append("Use pd.to_datetime and pandas string/date operations instead of importing datetime.")
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in FORBIDDEN_CALL_NAMES:
                errors.append(f"Forbidden call: {name}")
            root = name.split(".", 1)[0] if name else ""
            if root in FORBIDDEN_ROOT_NAMES:
                errors.append(f"Forbidden call root: {root}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_ROOT_NAMES:
            errors.append(f"Forbidden name: {node.id}")
        if isinstance(node, ast.Attribute):
            value_name = _root_name(node.value)
            if value_name in FORBIDDEN_ROOT_NAMES:
                errors.append(f"Forbidden attribute root: {value_name}")
    return sorted(set(errors))


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    return ""


def _safe_builtins() -> dict[str, Any]:
    return {
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }


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


def _json_ready(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return str(value)


def _mark_repair_attempt_result(repair_value: Any, analysis: dict[str, Any]) -> dict[str, Any]:
    repair = deepcopy(repair_value) if isinstance(repair_value, dict) else {}
    final_errors = _unique_text([*_as_text_list(analysis.get("errors")), *_as_text_list(analysis.get("repairable_errors"))])
    repair["executed"] = True
    repair["completed"] = not bool(final_errors)
    repair["status"] = "repaired" if not final_errors else "repair_failed"
    repair["final_errors"] = final_errors
    return repair


def _should_pass_through_repair_payload(payload: dict[str, Any]) -> bool:
    repair = payload.get("pandas_repair") if isinstance(payload.get("pandas_repair"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return repair.get("required") is False and bool(analysis)


def _is_repair_attempt_payload(payload: dict[str, Any]) -> bool:
    repair = payload.get("pandas_repair") if isinstance(payload.get("pandas_repair"), dict) else {}
    return repair.get("required") is True


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item) for item in value if str(item or "").strip()]


def _unique_text(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result

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
        data = value
        if isinstance(data.get("payload"), dict) and (
            "prompt" in data
            or "prompt_type" in data
            or "pandas_function_cases" in data
            or "pandas_function_case_runtime" in data
        ):
            payload = deepcopy(data["payload"])
            if "pandas_function_case_runtime" in data and "pandas_function_case_runtime" not in payload:
                payload["pandas_function_case_runtime"] = deepcopy(data["pandas_function_case_runtime"])
            return payload
        return deepcopy(data)
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return _payload(data)
    return {}


# 컴포넌트 설명: 15 Pandas Code Executor
# Langflow 표시 설명: LLM이 만든 pandas JSON/code를 파싱하고 안전성 검사 후 runtime source DataFrame 위에서 실행합니다.
class PandasCodeExecutor(Component):

    display_name = "15 Pandas Code Executor"
    description = "LLM이 만든 pandas JSON/code를 파싱하고 안전성 검사 후 runtime source DataFrame 위에서 실행합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
        MessageTextInput(
            name="specialized_functions_text",
            display_name="Specialized Functions",
            value="",
            required=False,
        ),
    ]
    outputs = [
        Output(name="payload_out", display_name="Payload", method="build_payload"),
    ]


    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: LLM이 만든 pandas JSON/code를 파싱하고 안전성 검사 후 runtime source DataFrame 위에서 실행합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        return Data(data=self._result())

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: LLM이 만든 pandas JSON/code를 파싱하고 안전성 검사 후 runtime source DataFrame 위에서 실행합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def _result(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_result", None)
        if isinstance(cached, dict):
            return cached
        result = execute_pandas_from_llm(
            getattr(self, "payload", None),
            getattr(self, "llm_response", ""),
            getattr(self, "specialized_functions_text", ""),
        )
        self._cached_result = result
        self._set_status(result)
        return result

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: LLM이 만든 pandas JSON/code를 파싱하고 안전성 검사 후 runtime source DataFrame 위에서 실행합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def _set_status(self, result: dict[str, Any]) -> None:
        analysis = result.get("analysis", {})
        repair = result.get("pandas_repair") if isinstance(result.get("pandas_repair"), dict) else {}
        self.status = {
            "status": analysis.get("status"),
            "rows": analysis.get("row_count", 0),
            "safety_passed": analysis.get("safety_passed", False),
            "executed": analysis.get("executed", False),
            "errors": len(analysis.get("errors", [])),
            "repair_required": repair.get("required", False),
            "repair_status": repair.get("status", ""),
        }
