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
def execute_initial_pandas_from_llm(
    payload_value: Any,
    llm_response_value: Any,
    specialized_functions_text: Any = "",
) -> dict[str, Any]:
    return _execute_pandas_from_llm(
        payload_value,
        llm_response_value,
        specialized_functions_text,
        allow_repair_attempt=False,
    )


def execute_repair_pandas_from_llm(
    payload_value: Any,
    llm_response_value: Any,
    specialized_functions_text: Any = "",
) -> dict[str, Any]:
    return _execute_pandas_from_llm(
        payload_value,
        llm_response_value,
        specialized_functions_text,
        allow_repair_attempt=True,
    )


def execute_pandas_from_llm(payload_value: Any, llm_response_value: Any, specialized_functions_text: Any = "") -> dict[str, Any]:
    return _execute_pandas_from_llm(
        payload_value,
        llm_response_value,
        specialized_functions_text,
        allow_repair_attempt=True,
    )


def _execute_pandas_from_llm(
    payload_value: Any,
    llm_response_value: Any,
    specialized_functions_text: Any = "",
    *,
    allow_repair_attempt: bool,
) -> dict[str, Any]:
    payload = _payload(payload_value)
    manual_helper_text = _text(specialized_functions_text).strip()
    if manual_helper_text:
        payload = dict(payload)
        payload["specialized_functions_text"] = manual_helper_text
    if payload.get("direct_response_ready"):
        return payload
    if _should_pass_through_repair_payload(payload):
        return payload
    if _is_repair_attempt_payload(payload) and not allow_repair_attempt:
        next_payload = dict(payload)
        next_payload["warnings"] = list(next_payload.get("warnings", [])) + [
            f"{PANDAS_WARNING_PREFIX} Repair payload received by 15 Pandas Code Executor. "
            "Use 17 Pandas Repair Code Executor for repair execution."
        ]
        return next_payload
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
    if allow_repair_attempt and _is_repair_attempt_payload(payload):
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
    local_vars["__builtins__"] = _safe_builtins()
    try:
        exec(compile(code, "<llm_pandas_code>", "exec"), local_vars, local_vars)
        function_case_trace = _function_case_trace_from_locals(local_vars)
        result_df = local_vars.get("result_df")
        if result_df is None or not hasattr(result_df, "to_dict"):
            raise ValueError("Generated code must assign a pandas DataFrame to result_df.")
        result_df = result_df.copy()
        result_df = _normalize_result_columns(result_df, plan)
        result_df = _normalize_result_columns(_collapse_over_detailed_aggregate_result(result_df, plan), plan)
    except Exception as exc:
        return {
            "status": "error",
            "analysis_kind": plan.get("analysis_kind"),
            "analysis_code": code,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "intermediate_refs": {},
            "errors": [f"Generated pandas code failed: {exc}"],
            "repairable_errors": [f"Generated pandas code failed: {exc}"],
            "used_executor_fallback": False,
            "safety_passed": True,
            "executed": False,
        }

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
        local_vars: dict[str, Any] = {"pd": pd, "__builtins__": _safe_builtins()}
        try:
            exec(compile(helper_code, f"<pandas_function_case:{case_key}>", "exec"), local_vars, local_vars)
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
            local_vars: dict[str, Any] = {"pd": pd, "__builtins__": _safe_builtins()}
            try:
                exec(compile(helper_code, f"<specialized_functions_text:{index}:{function_name}>", "exec"), local_vars, local_vars)
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

    for base_name in ["PRODUCTION", "WIP", "INPUT_PLAN", "OUT_PLAN", "TARGET_QTY", "LOT_COUNT", "WF_QTY", "DIE_QTY", "PRESS_CNT"]:
        for suffix in ("_sum", "_total", "_quantity", "_qty"):
            alias = f"{base_name}{suffix}"
            if base_name not in result.columns and alias in result.columns:
                rename_map[alias] = base_name
    plan_metric = str(plan.get("metric") or "").strip().upper()
    if plan_metric == "PRODUCTION" and "PRODUCTION" not in result.columns:
        for column in result.columns:
            column_text = str(column or "").strip()
            column_key = column_text.upper()
            if (
                column_key.endswith("_PRODUCTION_QTY")
                or column_key.endswith("_PRODUCTION_QUANTITY")
                or (
                    "PRODUCTION" in column_key
                    and "RATE" not in column_key
                    and "ACHIEVEMENT" not in column_key
                    and "BALANCE" not in column_key
                )
            ):
                rename_map[column_text] = "PRODUCTION"
                break

    structural_alias_map = {
        "WIP": ["TOTAL_WIP", "WIP_TOTAL", "WIP_SUM", "SUM_WIP", "WIP_QUANTITY", "WIP_QTY"],
        "PRODUCTION": ["TOTAL_PRODUCTION", "PRODUCTION_TOTAL", "SUM_PRODUCTION", "PRODUCTION_SUM", "PRODUCTION_QUANTITY", "PRODUCTION_QTY"],
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
    alias_map = {
        "PRODUCTION": ["생산량", "생산 수량", "실적", "생산실적"],
        "WIP": ["재공", "재공 수량", "재공수량"],
        "INPUT_PLAN": ["INPUT계획", "INPUT 계획", "투입계획", "투입 계획"],
        "OUT_PLAN": ["목표값", "목표", "생산계획", "계획", "OUT계획", "OUT 계획"],
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
    result = _drop_duplicate_standard_alias_columns(result)
    if analysis_kind == "aggregate_wip_total" and "SCOPE" not in result.columns and "WIP" in result.columns:
        result.insert(0, "SCOPE", plan.get("scope_label") or "ALL")
    result = _add_result_scope_columns(result, plan)
    return _order_result_columns(result, plan)


def _drop_duplicate_standard_alias_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    alias_groups = {
        "DEN": ["DENSITY", "DEN_TYP"],
        "PKG_TYPE1": ["PKG1", "PKG_TYP1", "PKG_TYP"],
        "PKG_TYPE2": ["PKG2", "PKG_TYP2", "PKG_TYP_2"],
        "MCP_NO": ["MCP NO", "MCP_SALE_CD", "MCP_SALES_NO", "MCPSALENO", "PROD_GRP_ID"],
        "MODE": ["PROD_TYP"],
        "TECH": ["TECH_NM"],
        "LEAD": ["LEAD_CNT"],
        "PRODUCTION": ["TOTAL_PRODUCTION", "PRODUCTION_TOTAL", "SUM_PRODUCTION", "PRODUCTION_SUM", "PRODUCTION_QUANTITY", "PRODUCTION_QTY"],
        "WIP": ["TOTAL_WIP", "WIP_TOTAL", "WIP_SUM", "SUM_WIP", "WIP_QUANTITY", "WIP_QTY"],
    }
    for standard, aliases in alias_groups.items():
        if standard not in result.columns:
            if standard not in {"PRODUCTION", "WIP"}:
                continue
            for alias in aliases:
                if alias in result.columns:
                    result = result.rename(columns={alias: standard})
                    break
            continue
        duplicate_aliases = [
            alias
            for alias in aliases
            if alias in result.columns and _series_values_equivalent(result[standard], result[alias])
        ]
        if duplicate_aliases:
            result = result.drop(columns=duplicate_aliases)
    return result


def _series_values_equivalent(left: pd.Series, right: pd.Series) -> bool:
    if len(left) != len(right):
        return False
    left_numeric = pd.to_numeric(left, errors="coerce")
    right_numeric = pd.to_numeric(right, errors="coerce")
    if left_numeric.notna().any() or right_numeric.notna().any():
        return left_numeric.fillna(0).equals(right_numeric.fillna(0))
    left_text = left.fillna("").astype(str).str.strip().str.upper()
    right_text = right.fillna("").astype(str).str.strip().str.upper()
    return left_text.equals(right_text)


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
    step_plan_result = _fallback_from_step_plan(plan, runtime_sources)
    if step_plan_result is not None:
        return step_plan_result
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
    return None


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
        elif operation in {
            "equipment_count_by_product",
            "unique_count_by_group",
            "nunique_by_group",
        }:
            frame = _fallback_step_unique_count(step, plan, runtime_sources, frames_by_step)
        elif operation == "detail_rows":
            frame = _fallback_step_detail_rows(step, plan, runtime_sources, frames_by_step)
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
    frame = _frame_for_step_source(step, runtime_sources, plan, frames_by_step)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    frame = _apply_step_filters(frame, step)
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
    frame = _frame_for_step_source(step, runtime_sources, plan, frames_by_step)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    frame = _apply_step_filters(frame, step)
    metric_specs = _step_metric_specs(step, plan, frame)
    if not metric_specs:
        return None
    group_by = _available_columns(frame, step.get("group_by"))
    work = frame.copy()
    for spec in metric_specs:
        if spec["aggregation"] in {"sum", "mean", "max", "min"}:
            work[spec["source_column"]] = pd.to_numeric(work[spec["source_column"]], errors="coerce")
            if spec["aggregation"] == "sum":
                work[spec["source_column"]] = work[spec["source_column"]].fillna(0)
    if group_by:
        result: pd.DataFrame | None = None
        for spec in metric_specs:
            piece = (
                work.groupby(group_by, dropna=False)[spec["source_column"]]
                .agg(spec["aggregation"])
                .reset_index(name=spec["output_column"])
            )
            result = piece if result is None else result.merge(piece, on=group_by, how="outer")
        if result is None:
            return None
    else:
        result = pd.DataFrame(
            [
                {
                    spec["output_column"]: _aggregate_series(work[spec["source_column"]], spec["aggregation"])
                    for spec in metric_specs
                }
            ]
        )
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
    frame = _frame_for_step_source(step, runtime_sources, plan, frames_by_step)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    frame = _apply_step_filters(frame, step)
    count_column = str(step.get("count_column") or "").strip()
    if not count_column:
        count_column = next((column for column in ["EQPID", "EQP_ID", "LOT_ID"] if column in frame.columns), "")
    if not count_column or count_column not in frame.columns:
        return None
    group_by = _available_columns(frame, step.get("group_by") or step.get("group_by_columns"))
    output_column = _count_output_column(step, group_by)
    if group_by:
        result = frame.groupby(group_by, dropna=False)[count_column].nunique().reset_index(name=output_column)
    else:
        result = pd.DataFrame([{output_column: frame[count_column].nunique()}])
    return _select_step_columns(result, _step_output_columns(step))


def _fallback_step_detail_rows(
    step: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, Any],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources, plan, frames_by_step)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    frame = _apply_step_filters(frame, step)
    output_columns = _step_output_columns(step)
    if not output_columns:
        output_columns = _column_names_from_output_specs(step.get("columns", []) if isinstance(step.get("columns"), list) else [])
    if not output_columns:
        output_columns = _column_names_from_output_specs(
            step.get("required_columns", []) if isinstance(step.get("required_columns"), list) else []
        )
    return _select_step_columns(frame.drop_duplicates().reset_index(drop=True), output_columns)


def _fallback_step_left_join(step: dict[str, Any], frames_by_step: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    left_step = str(step.get("left_step") or step.get("left_step_id") or "").strip()
    right_step = str(step.get("right_step") or step.get("right_step_id") or "").strip()
    if not left_step or not right_step or left_step not in frames_by_step or right_step not in frames_by_step:
        return None
    left = frames_by_step[left_step]
    right = frames_by_step[right_step]
    join_pairs = _step_join_key_pairs(step, left, right)
    if not join_pairs:
        return None
    left_on = [pair[0] for pair in join_pairs]
    right_on = [pair[1] for pair in join_pairs]
    if left_on == right_on:
        result = left.merge(right, on=left_on, how="left")
    else:
        result = left.merge(right, left_on=left_on, right_on=right_on, how="left")
    for column in _step_output_columns(step):
        if column not in result.columns:
            result[column] = 0 if column.endswith("_COUNT") else None
    return _select_step_columns(result, _step_output_columns(step))


def _frame_for_step_source(
    step: dict[str, Any],
    runtime_sources: dict[str, Any],
    plan: dict[str, Any],
    frames_by_step: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame | None:
    frames = frames_by_step or {}
    input_step_id = str(step.get("input_step_id") or step.get("source_step_id") or step.get("source_data_step_id") or "").strip()
    if input_step_id and input_step_id in frames:
        return frames[input_step_id].copy()
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
    join_pairs = _step_join_key_pairs(step, frame, previous)
    if not join_pairs:
        default_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "TSV_DIE_TYP"]
        join_pairs = [(column, column) for column in default_keys if column in frame.columns and column in previous.columns]
    if not join_pairs:
        return frame
    left_on = [pair[0] for pair in join_pairs]
    right_on = [pair[1] for pair in join_pairs]
    right_columns = _unique_columns([*right_on, *[column for column in previous.columns if column not in frame.columns]])
    selected = previous[right_columns].drop_duplicates()
    if left_on == right_on:
        return frame.merge(selected, on=left_on, how="inner")
    return frame.merge(selected, left_on=left_on, right_on=right_on, how="inner")


def _apply_step_filters(frame: pd.DataFrame, step: dict[str, Any]) -> pd.DataFrame:
    filters = step.get("filters")
    if frame.empty or not filters:
        return frame
    conditions: list[dict[str, Any]] = []
    if isinstance(filters, list):
        conditions = [item for item in filters if isinstance(item, dict)]
    elif isinstance(filters, dict):
        for field, condition in filters.items():
            if isinstance(condition, dict):
                next_condition = {"field": field, **condition}
            else:
                next_condition = {"field": field, "op": "eq", "value": condition}
            conditions.append(next_condition)
    result = frame.copy()
    for condition in conditions:
        field = str(condition.get("field") or "").strip()
        if not field or field not in result.columns:
            continue
        series = result[field]
        if condition.get("exists") is True or str(condition.get("op") or "").lower() in {"exists", "not_empty"}:
            result = result[series.notna() & (series.astype(str).str.strip() != "")]
            series = result[field]
        values = condition.get("values")
        if values is None and "value" in condition:
            values = [condition.get("value")]
        if values is None and "not_in" in condition:
            values = condition.get("not_in")
            normalized_values = {_normalize_compare_value(value) for value in (values if isinstance(values, list) else [values])}
            result = result[~series.map(_normalize_compare_value).isin(normalized_values)]
            continue
        if values is None:
            continue
        value_list = values if isinstance(values, list) else [values]
        normalized_values = {_normalize_compare_value(value) for value in value_list}
        op = str(condition.get("op") or "eq").lower()
        if op in {"eq", "="}:
            result = result[series.map(_normalize_compare_value).isin(normalized_values)]
        elif op in {"ne", "!=", "not_in"}:
            result = result[~series.map(_normalize_compare_value).isin(normalized_values)]
        elif op == "in":
            result = result[series.map(_normalize_compare_value).isin(normalized_values)]
    return result


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
    candidates = [column_text, *_quantity_name_variants(column_text)]
    job = _job_for_source_alias(alias, plan)
    if isinstance(job, dict):
        candidates.extend(_primary_quantity_column_matches(job, column_text))
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mapping = job.get(field) if isinstance(job.get(field), dict) else {}
            mapped = mapping.get(column_text)
            if mapped is not None:
                if not isinstance(mapped, list):
                    mapped = [mapped]
                for item in mapped:
                    item_text = str(item or "").strip()
                    if item_text:
                        candidates.extend([item_text, *_quantity_name_variants(item_text)])
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
    return [left_key for left_key, right_key in _step_join_key_pairs(step, left, right) if left_key == right_key]


def _step_join_key_pairs(step: dict[str, Any], left: pd.DataFrame, right: pd.DataFrame) -> list[tuple[str, str]]:
    raw_keys = step.get("join_keys") if isinstance(step.get("join_keys"), list) else []
    if not raw_keys and step.get("join_key"):
        raw_keys = [step.get("join_key")]
    pairs: list[tuple[str, str]] = []
    for raw_key in raw_keys:
        if isinstance(raw_key, dict):
            left_key = str(raw_key.get("left") or raw_key.get("left_on") or raw_key.get("source") or "").strip()
            right_key = str(raw_key.get("right") or raw_key.get("right_on") or raw_key.get("target") or "").strip()
        else:
            left_key = right_key = str(raw_key or "").strip()
        if left_key and right_key and left_key in left.columns and right_key in right.columns:
            pairs.append((left_key, right_key))
    return pairs


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


def _step_metric_specs(step: dict[str, Any], plan: dict[str, Any], frame: pd.DataFrame) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    raw_metrics = step.get("metrics") if isinstance(step.get("metrics"), list) else []
    for metric in raw_metrics:
        if isinstance(metric, dict):
            source_column = str(
                metric.get("quantity_column")
                or metric.get("source_column")
                or metric.get("column")
                or metric.get("metric")
                or ""
            ).strip()
            aggregation = _normalize_aggregation(metric.get("aggregation") or metric.get("agg") or step.get("aggregation"))
            output_column = str(metric.get("output_column") or metric.get("name") or source_column).strip()
        else:
            source_column = str(metric or "").strip()
            aggregation = _step_aggregation(step)
            output_column = source_column
        if source_column and source_column in frame.columns and aggregation:
            specs.append(
                {
                    "source_column": source_column,
                    "aggregation": aggregation,
                    "output_column": output_column or source_column,
                }
            )
    if specs:
        return specs
    aggregation = _step_aggregation(step)
    return [
        {"source_column": column, "aggregation": aggregation, "output_column": column}
        for column in _step_metric_columns(step, plan, frame)
        if aggregation
    ]


def _step_aggregation(step: dict[str, Any]) -> str:
    return _normalize_aggregation(step.get("aggregation") or step.get("agg") or step.get("agg_func") or "sum")


def _normalize_aggregation(value: Any) -> str:
    raw_value = str(value or "sum").strip().lower()
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
    if isinstance(plan.get("analysis_output_columns"), list):
        explicit = _column_names_from_output_specs(plan["analysis_output_columns"])
        if explicit:
            return explicit
    final_step_columns = _final_step_output_columns(plan)
    if final_step_columns:
        return final_step_columns
    product_keys = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    kind = plan.get("analysis_kind")
    if kind == "aggregate_join":
        return [*product_keys, "PRODUCTION", "WIP"]
    if kind == "production_wip_target_rate":
        return [*product_keys, "WIP", "PRODUCTION", "OUT_PLAN", "ACHIEVEMENT_RATE"]
    if kind == "low_output_vs_target":
        return [*product_keys, "PRODUCTION", "TARGET_QTY", "ACHIEVEMENT_RATE", "BALANCE", "LOW_OUTPUT_FLAG"]
    if kind == "aggregate_wip_total":
        return ["SCOPE", "WIP"]
    if kind == "overall_production_wip_target":
        return ["SCOPE", "PRODUCTION", "WIP", "OUT_PLAN"]
    if kind == "date_split_production_plan_gap":
        return [*product_keys, "PRODUCTION", "OUT_PLAN", "BALANCE"]
    if kind == "equipment_by_model":
        return ["EQP_MODEL", "EQP_COUNT", "PRESS_CNT"]
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
        for standard in standard_candidates:
            standard_text = str(standard or "").strip()
            if not standard_text:
                continue
            quantity_candidates = [
                candidate
                for candidate in [*_quantity_name_variants(standard_text), *_primary_quantity_column_matches(job, standard_text)]
                if candidate and candidate != standard_text
            ]
            if quantity_candidates:
                aliases.setdefault(standard_text, [])
                aliases[standard_text].extend(quantity_candidates)
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


def _quantity_name_variants(column: str) -> list[str]:
    text = str(column or "").strip()
    if not text:
        return []
    compact = re.sub(r"\s+", "", text)
    variants: list[str] = []
    if compact and compact != text:
        variants.append(compact)
    normalized = _quantity_semantic_key(text)
    if normalized == "INPUT_PLAN":
        variants.extend(["INPUT_PLAN", "INPUT계획", "INPUT 계획"])
    elif normalized == "OUT_PLAN":
        variants.extend(["OUT_PLAN", "OUT계획", "OUT 계획"])
    return _unique_columns([variant for variant in variants if variant and variant != text])


def _primary_quantity_column_matches(job: dict[str, Any], column: str) -> list[str]:
    target_key = _quantity_semantic_key(column)
    if not target_key:
        return []
    quantity = job.get("primary_quantity_column")
    quantity_columns = quantity if isinstance(quantity, list) else [quantity] if quantity else []
    return [
        str(item).strip()
        for item in quantity_columns
        if str(item or "").strip() and _quantity_semantic_key(str(item)) == target_key
    ]


def _quantity_semantic_key(value: Any) -> str:
    text = re.sub(r"[\s_]+", "", str(value or "").strip().upper())
    if text in {"INPUTPLAN", "INPUT계획"}:
        return "INPUT_PLAN"
    if text in {"OUTPLAN", "OUT계획", "TARGET"}:
        return "OUT_PLAN"
    return ""


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
        result = execute_initial_pandas_from_llm(
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
