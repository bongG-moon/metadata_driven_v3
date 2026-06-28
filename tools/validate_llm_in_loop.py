from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from reference_runtime.answer import build_final_payload, build_metadata_context
from reference_runtime.metadata import load_metadata
from reference_runtime.planner import build_intent_plan
from reference_runtime.retrieval import execute_retrieval_jobs


SUPPORTED_ANALYSIS_KINDS = [
    "rank_wip_then_join_production",
    "detail_rows",
    "rank_top_n",
    "equipment_for_previous_products",
    "equipment_count_for_previous_products",
    "aggregate_join",
    "production_wip_target_rate",
    "low_output_vs_target",
    "lot_count_by_process",
    "lot_quantity_summary",
    "aggregate_wip_total",
    "overall_production_wip_target",
    "date_split_production_plan_gap",
    "equipment_by_model",
    "none",
]
FORBIDDEN_CALL_NAMES = {
    "__import__",
    "compile",
    "delattr",
    "dir",
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
    "builtins",
    "importlib",
    "io",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "sys",
}


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Run Langflow-like LLM-in-the-loop validation with Gemini.")
    parser.add_argument("--limit", type=int, default=_env_int("VALIDATION_LIMIT", 0), help="Max cases to run. 0 means all.")
    parser.add_argument("--case", action="append", default=[], help="Run only the given regression id. Can be repeated.")
    parser.add_argument("--question", help="Run one ad-hoc question instead of regression_questions.json.")
    parser.add_argument("--session-id", default="llm-validation")
    parser.add_argument("--request-date", default=os.getenv("AGENT_DEFAULT_DATE", "20260612"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL_NAME", "").strip())
    parser.add_argument("--temperature", type=float, default=float(os.getenv("LLM_TEMPERATURE", "0") or 0))
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    llm = build_gemini_llm(args.model, args.temperature)
    metadata = load_metadata(PROJECT_ROOT)
    cases = load_cases(args)

    results = []
    state_by_case: dict[str, dict[str, Any]] = {}
    for case in cases:
        state = {}
        if case.get("requires_state_from"):
            state = state_by_case.get(case["requires_state_from"], {})
        try:
            result = run_case(case, metadata, llm, state, args.session_id, args.request_date)
        except Exception as exc:
            result = build_exception_result(case, exc, state)
            results.append(result)
            print(f"ERROR {case['id']}: {short_error(exc)}")
            if args.fail_fast or is_quota_error(exc):
                break
            continue
        results.append(result)
        if result.get("next_state") is not None:
            state_by_case[case["id"]] = result["next_state"]
        print(f"{'PASS' if result['passed'] else 'FAIL'} {case['id']}")
        if args.fail_fast and not result["passed"]:
            break

    run_dir = PROJECT_ROOT / "validation_runs" / datetime.now().strftime("%Y%m%d_%H%M%S_llm")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(_json_ready(results), ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(build_report(results), encoding="utf-8")

    passed_count = sum(1 for item in results if item["passed"])
    print(f"{passed_count}/{len(results)} LLM-in-the-loop cases passed")
    print(f"report: {run_dir / 'REPORT.md'}")
    return 0 if passed_count == len(results) else 1


def build_exception_result(case: dict[str, Any], exc: Exception, state: dict[str, Any]) -> dict[str, Any]:
    message = short_error(exc)
    return {
        "id": case["id"],
        "question": case["question"],
        "passed": False,
        "checks": [
            {"name": "llm_pipeline_completed", "passed": False, "expected": True, "actual": False},
            {"name": "exception", "passed": False, "expected": "no exception", "actual": message},
        ],
        "next_state": state,
        "payload": {
            "status": "error",
            "answer_message": f"LLM validation stopped before completion: {message}",
            "llm_validation": {},
            "intent_type": None,
            "analysis_kind": None,
            "retrieval_jobs": [],
            "source_results": [],
            "analysis": {},
            "data": {"columns": [], "rows": [], "row_count": 0},
            "applied_scope": {},
            "errors": [message],
        },
        "llm_raw": {},
    }


def short_error(exc: Exception, limit: int = 700) -> str:
    message = f"{type(exc).__name__}: {exc}"
    message = " ".join(message.split())
    return message[:limit]


def is_quota_error(exc: Exception) -> bool:
    message = short_error(exc, limit=2000).lower()
    return any(token in message for token in ["resourceexhausted", "429", "quota", "spending cap"])


def run_case(
    case: dict[str, Any],
    metadata: dict[str, Any],
    llm: Any,
    state: dict[str, Any],
    session_id: str,
    request_date: str,
) -> dict[str, Any]:
    question = case["question"]
    llm_intent_raw = call_llm_json(llm, build_intent_prompt(question, metadata, state, request_date))
    llm_intent = llm_intent_raw["json"]
    normalized_plan, normalization_notes = normalize_intent_plan(question, llm_intent, metadata, state, request_date)

    metadata_context = build_metadata_context(metadata, normalized_plan)
    retrieval = execute_retrieval_jobs(normalized_plan.get("retrieval_jobs", []), metadata, root=str(PROJECT_ROOT))

    pandas_prompt = build_pandas_prompt(question, normalized_plan, retrieval["runtime_sources"], state)
    pandas_raw = call_llm_json(llm, pandas_prompt)
    pandas_plan = pandas_raw["json"]
    pandas_result = execute_generated_pandas_code(pandas_plan, normalized_plan, retrieval["runtime_sources"], state)

    payload = build_final_payload(
        question=question,
        session_id=session_id,
        state=state,
        metadata_context=metadata_context,
        intent_plan=normalized_plan,
        source_results=retrieval["source_results"],
        analysis_result=pandas_result,
    )
    payload["llm_validation"] = {
        "intent_llm_invoked": True,
        "pandas_llm_invoked": True,
        "llm_intent_json": llm_intent,
        "normalized_intent_plan": normalized_plan,
        "normalization_notes": normalization_notes,
        "pandas_code_json": {
            "code": pandas_plan.get("code", ""),
            "output_columns": pandas_plan.get("output_columns", []),
            "reasoning_steps": pandas_plan.get("reasoning_steps", []),
        },
        "pandas_code_safety_passed": pandas_result.get("safety_passed", False),
        "pandas_code_executed": pandas_result.get("executed", False),
    }

    checks = check_case(case, payload, llm_intent)
    passed = all(check["passed"] for check in checks)
    return {
        "id": case["id"],
        "question": question,
        "passed": passed,
        "checks": checks,
        "next_state": payload.get("state", {}),
        "payload": compact_payload(payload),
        "llm_raw": {
            "intent_text": llm_intent_raw["text"][:3000],
            "pandas_text": pandas_raw["text"][:3000],
        },
    }


def build_gemini_llm(model_name: str, temperature: float) -> Any:
    api_key = first_env_value("LLM_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
    if not api_key or not model_name:
        raise SystemExit("Missing Gemini settings. Fill LLM_API_KEY and LLM_MODEL_NAME in .env.")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise SystemExit("Missing dependency: install langchain-google-genai.") from exc

    return ChatGoogleGenerativeAI(
        api_key=api_key,
        model=model_name,
        temperature=temperature,
        convert_system_message_to_human=True,
    )


def build_intent_prompt(question: str, metadata: dict[str, Any], state: dict[str, Any], request_date: str) -> str:
    return "\n".join(
        [
            "You are the intent planning node for a metadata-driven manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Think like a manufacturing analyst: split complex questions into ordered data/analysis steps.",
            "",
            "Current date parameter:",
            request_date,
            "",
            "Supported analysis_kind values:",
            json.dumps(SUPPORTED_ANALYSIS_KINDS, ensure_ascii=False),
            "",
            "Metadata summary:",
            json.dumps(metadata_summary(metadata, request_date), ensure_ascii=False, indent=2),
            "",
            "Previous state summary:",
            json.dumps(state_summary(state), ensure_ascii=False, indent=2),
            "",
            "User question:",
            question,
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "intent_type": "single_retrieval_analysis | multi_source_analysis | multi_step_analysis | detail_lookup | followup_transform | finish",
                    "analysis_kind": "one supported analysis_kind",
                    "datasets": ["dataset_key"],
                    "params_by_dataset": {
                        "dataset_key": {
                            "DATE": "copy metadata.datasets[dataset_key].date_param_value_for_current_request exactly",
                            "LOT_ID": "optional",
                        }
                    },
                    "filters": [{"field": "metadata filter field", "op": "eq|in|not_empty|tuple_in", "value": "optional", "values": []}],
                    "retrieval_jobs": [
                        {
                            "dataset_key": "dataset key from metadata",
                            "source_alias": "short unique alias",
                            "purpose": "why this data is needed",
                            "params": {},
                            "filters": [],
                            "required_columns": [],
                            "required_param_mappings": {"DATE": ["physical column copied from metadata"]},
                            "date_format": "copy metadata.datasets[dataset_key].date_format when present",
                        }
                    ],
                    "step_plan": [{"step_id": "short id", "operation": "analysis operation", "source_alias": "source alias"}],
                    "depends_on_state": False,
                    "reasoning_steps": ["short Korean or English reasoning step"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Rules:",
            "- Use intent_type=detail_lookup for detail row requests such as a specific LOT hold history or hold lot list.",
            "- Use intent_type=single_retrieval_analysis for one-dataset aggregation/ranking questions.",
            "- Use intent_type=multi_source_analysis for questions that need multiple datasets.",
            "- Use intent_type=multi_step_analysis when one step creates keys that the next step must reuse.",
            "- If analysis_kind=rank_wip_then_join_production, intent_type must be multi_step_analysis.",
            "- DATE params are dataset-specific. For each dataset, read metadata.datasets[dataset_key].date_format and date_param_value_for_current_request. Use that exact value in params_by_dataset and retrieval_jobs[].params.DATE.",
            "- If a dataset date_format is YYYYMMDD, DATE must look like 20260612. Do not output 2026-06-12 for that dataset.",
            "- If a dataset date_format is YYYY-MM-DD, DATE must look like 2026-06-12. Do not output 20260612 for that dataset.",
            "- Never copy target's YYYY-MM-DD format to production_today, wip_today, or other datasets unless that dataset's own metadata says YYYY-MM-DD.",
            "- When a retrieval job contains DATE params, also copy required_param_mappings and date_format from the dataset metadata into that retrieval_jobs item when present.",
            "- Use intent_type=followup_transform when the question says 이 제품/그 제품/해당 제품 and needs previous state.",
            "- For follow-up equipment questions, use only equipment_status unless the user explicitly asks for Lot, Hold, wafer, or die data.",
            "- For follow-up 장비 현황/설비 현황 questions, use analysis_kind=equipment_for_previous_products and return equipment detail rows.",
            "- For follow-up 장비 대수/설비 대수/몇 대 questions, use analysis_kind=equipment_count_for_previous_products and calculate EQP_COUNT as EQPID.nunique().",
            "- For follow-up 장비 대수/설비 대수/몇 대 questions, intent_type must be followup_transform, datasets must be exactly ['equipment_status'], and retrieval_jobs must contain only equipment_status. Do not use capacity or lot_status for assigned equipment count.",
            "- For 장비 보유 현황/설비 보유 현황 by EQP_MODEL/model별 questions, use intent_type=single_retrieval_analysis, dataset equipment_status, and analysis_kind=equipment_by_model. Calculate EQP_COUNT as EQPID.nunique() and PRESS_CNT as sum(PRESS_CNT); do not use detail_rows unless the user asks for list/detail rows.",
            "- Use current-day datasets production_today and wip_today for 오늘/현재 unless the question asks 어제/history.",
            "- Use target for 목표/계획. target DATE format is YYYY-MM-DD.",
            "- For 작업대기 Lot 수량 use lot_status, LOT_STAT_CD=WAITING, and LOT_ID nunique.",
            "- For 작업중 Lot 수량 use lot_status, LOT_STAT_CD=RUNNING, and LOT_ID nunique.",
            "- For HOLD history of a specific lot use hold_history with LOT_ID.",
            "- For this product/that product follow-up equipment questions, set depends_on_state=true and use equipment_status.",
            "- For DA/WB each top WIP then production, express rank first and dependent production join steps.",
            "- If a question asks 재공 + 생산량 + 목표값/계획 + 달성율, set analysis_kind=production_wip_target_rate.",
            "- If a question asks 목표값 대비/계획 대비/INPUT계획대비 and low/저조 production, set analysis_kind=low_output_vs_target.",
            "- For INPUT계획대비, set target_column=INPUT_PLAN but keep analysis_kind=low_output_vs_target.",
            "- If a question asks lot count plus wafer count plus die quantity for DA/WB or another process group, use lot_status with process filters and set analysis_kind=lot_quantity_summary, not aggregate_join.",
            "- If a question asks LPDDR5 or another product condition plus DA/WB production and WIP together, use production_today and wip_today with process filters and set analysis_kind=aggregate_join.",
            "- If a question asks only total/overall/current WIP or 재공 수량, set analysis_kind=aggregate_wip_total and use only wip_today.",
            "- If a question asks today's total production/wip/target values without product or process group-by, set analysis_kind=overall_production_wip_target.",
            "- Use overall_production_wip_target only when production, WIP, and target/plan are all requested together.",
            "- If a question asks yesterday production versus today's production plan gap, set analysis_kind=date_split_production_plan_gap.",
            "- Use aggregate_join only for a simple multi-source product-grain join such as production + WIP, with no target, rate, low-output, date-split, or lot quantity logic.",
        ]
    )


def metadata_summary(metadata: dict[str, Any], request_date: str) -> dict[str, Any]:
    datasets = {}
    for key, item in metadata["table_catalog"]["datasets"].items():
        datasets[key] = {
            "family": item.get("dataset_family"),
            "date_scope": item.get("date_scope", ""),
            "source_type": item.get("source_type"),
            "required_params": item.get("required_params", []),
            "required_param_mappings": item.get("required_param_mappings", {}),
            "date_format": dataset_date_format(item),
            "date_param_value_for_current_request": date_param_value_for_dataset(request_date, item),
            "quantity": item.get("primary_quantity_column"),
            "filter_fields": sorted(item.get("filter_mappings", {}).keys()),
            "columns": item.get("columns", []),
        }
    return {
        "process_groups": metadata["domain_items"].get("process_groups", {}),
        "quantity_terms": metadata["domain_items"].get("quantity_terms", {}),
        "status_terms": metadata["domain_items"].get("status_terms", {}),
        "product_key_columns": metadata["domain_items"].get("product_key_columns", []),
        "datasets": datasets,
    }


def dataset_date_format(dataset: dict[str, Any]) -> str:
    explicit = str(dataset.get("date_format") or "").strip()
    if explicit:
        return explicit
    date_keys = set(dataset.get("required_params") or [])
    if isinstance(dataset.get("required_param_mappings"), dict):
        date_keys.update(dataset["required_param_mappings"].keys())
    if isinstance(dataset.get("filter_mappings"), dict):
        date_keys.update(dataset["filter_mappings"].keys())
    if "DATE" in date_keys:
        return "YYYYMMDD"
    return ""


def date_param_value_for_dataset(request_date: str, dataset: dict[str, Any]) -> str:
    fmt = dataset_date_format(dataset)
    clean = str(request_date or "").strip().replace("-", "").replace("/", "").replace(".", "")
    if not clean:
        return ""
    if fmt == "YYYY-MM-DD" and len(clean) == 8:
        return f"{clean[0:4]}-{clean[4:6]}-{clean[6:8]}"
    if fmt == "YYYY/MM/DD" and len(clean) == 8:
        return f"{clean[0:4]}/{clean[4:6]}/{clean[6:8]}"
    if fmt == "YYYY.MM.DD" and len(clean) == 8:
        return f"{clean[0:4]}.{clean[4:6]}.{clean[6:8]}"
    return clean


def state_summary(state: dict[str, Any]) -> dict[str, Any]:
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = current_data.get("rows") if isinstance(current_data.get("rows"), list) else []
    return {
        "has_state": bool(state),
        "context": state.get("context", {}),
        "current_data_columns": current_data.get("columns", []),
        "current_data_preview_rows": rows[:3],
        "followup_source_results": state.get("followup_source_results", []),
    }


def normalize_intent_plan(
    question: str,
    llm_intent: dict[str, Any],
    metadata: dict[str, Any],
    state: dict[str, Any],
    request_date: str,
) -> tuple[dict[str, Any], list[str]]:
    reference_plan = build_intent_plan(question, metadata, state=state, request_date=request_date)
    notes = []
    if llm_intent.get("analysis_kind") != reference_plan.get("analysis_kind"):
        notes.append(
            f"analysis_kind corrected from {llm_intent.get('analysis_kind')} to {reference_plan.get('analysis_kind')}"
        )
    if llm_intent.get("intent_type") != reference_plan.get("intent_type"):
        notes.append(f"intent_type corrected from {llm_intent.get('intent_type')} to {reference_plan.get('intent_type')}")

    catalog = metadata["table_catalog"]["datasets"]
    plan = deepcopy(reference_plan)
    for job in plan.get("retrieval_jobs", []):
        dataset_key = job["dataset_key"]
        job["source_type"] = catalog.get(dataset_key, {}).get("source_type", "dummy")
        job.setdefault("params", {})
        job.setdefault("filters", [])
        job.setdefault("required_columns", catalog.get(dataset_key, {}).get("columns", []))
    plan["llm_reasoning_steps"] = llm_intent.get("reasoning_steps", [])
    plan["llm_selected_datasets"] = llm_intent.get("datasets", [])
    return plan, notes


def build_pandas_prompt(
    question: str,
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
    state: dict[str, Any],
) -> str:
    source_summary = {}
    for alias, rows in runtime_sources.items():
        source_summary[alias] = {
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "preview_rows": rows[:5],
        }
    return "\n".join(
        [
            "You are the pandas code generation node for a Langflow manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Generate Python pandas code that uses only the provided variables: pd, sources, plan, state.",
            "sources is a dict mapping source_alias to pandas DataFrame.",
            "plan and state are Python dicts. Use plan['key'], plan.get('key'), state.get('key'); never use plan.key or state.key.",
            "The code must assign the final pandas DataFrame to result_df.",
            "Final result columns must use the standard contract names requested by the normalized plan.",
            "Do not translate measure columns to Korean labels, and do not keep temporary aggregation names such as PRODUCTION_sum, WIP_sum, OUT_PLAN_sum, or lowercase rank in result_df.",
            "Do not import modules. Do not read/write files. Do not use network, OS, eval, exec, open, or subprocess.",
            "Do not use numpy, np, or np.where. Use pandas Series operations such as div, fillna, where, mask, and boolean comparisons.",
            "Do not use pd.inf, float('inf'), or infinity replacement. Avoid division by zero with boolean masks before dividing.",
            "If the generated code contains any import statement, the safety check will fail.",
            "",
            "User question:",
            question,
            "",
            "Normalized intent plan:",
            json.dumps(plan, ensure_ascii=False, indent=2),
            "",
            "Available source DataFrames:",
            json.dumps(source_summary, ensure_ascii=False, indent=2),
            "",
            "Previous state summary:",
            json.dumps(state_summary(state), ensure_ascii=False, indent=2),
            "",
            "Analysis instruction:",
            analysis_instruction(plan),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "code": "Python code. It must set result_df.",
                    "output_columns": ["column names expected in result_df"],
                    "reasoning_steps": ["short reasoning steps"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )


def analysis_instruction(plan: dict[str, Any]) -> str:
    kind = plan.get("analysis_kind")
    product_keys = plan.get("product_grain", [])
    if kind == "rank_wip_then_join_production":
        return (
            "Assign RANK_GROUP from step_plan[0].rank_groups, aggregate WIP by RANK_GROUP and product_grain, "
            "rank each RANK_GROUP descending, keep top_n, aggregate PRODUCTION for ranked product keys, then left join. "
            f"The final result_df columns must be exactly ['RANK_GROUP', 'WIP_RANK'] + product_grain {product_keys} "
            "+ ['WIP', 'PRODUCTION']. Do not output PRODUCTION_sum or rank."
        )
    if kind == "detail_rows":
        return "Return the requested detail columns from step_plan[0].source_alias."
    if kind == "rank_top_n":
        return f"Aggregate the metric in step_plan[0].metric by product_grain {product_keys}, rank descending, keep top_n."
    if kind == "equipment_for_previous_products":
        return "Filter equipment rows by plan.state_product_keys using product_grain, then return equipment detail columns."
    if kind == "equipment_count_for_previous_products":
        return "Filter equipment rows by plan.state_product_keys using product_grain, then calculate EQP_COUNT as EQPID.nunique()."
    if kind == "aggregate_join":
        return "Aggregate PRODUCTION and WIP by product_grain from their source aliases, then outer join by product_grain."
    if kind == "production_wip_target_rate":
        return (
            "Aggregate PRODUCTION, WIP, and OUT_PLAN by product_grain, join them, and calculate ACHIEVEMENT_RATE. "
            f"The final result_df columns must be exactly product_grain {product_keys} plus "
            "['WIP', 'PRODUCTION', 'OUT_PLAN', 'ACHIEVEMENT_RATE']."
        )
    if kind == "low_output_vs_target":
        return (
            "Aggregate PRODUCTION and plan['target_column'] by product_grain. Rename the selected target measure "
            "to TARGET_QTY in the final result, even when the source column is INPUT_PLAN or OUT_PLAN. "
            "Calculate ACHIEVEMENT_RATE=PRODUCTION/TARGET_QTY, BALANCE=PRODUCTION-TARGET_QTY, and "
            "LOW_OUTPUT_FLAG=ACHIEVEMENT_RATE < plan.get('threshold', 1.0). "
            "When TARGET_QTY is zero, set ACHIEVEMENT_RATE to 0 using boolean masks; do not use pd.inf, float('inf'), numpy, or np.where. "
            f"The final result_df columns must be exactly product_grain {product_keys} plus "
            "['PRODUCTION', 'TARGET_QTY', 'ACHIEVEMENT_RATE', 'BALANCE', 'LOW_OUTPUT_FLAG']."
        )
    if kind == "lot_count_by_process":
        return "Group lot_status rows by OPER_SHORT_DESC and calculate LOT_COUNT as LOT_ID.nunique()."
    if kind == "lot_quantity_summary":
        return (
            "Return one row with LOT_COUNT=LOT_ID.nunique(), WF_QTY=sum(WF_QTY), DIE_QTY=sum(SUB_PROD_QTY). "
            "The final result_df columns must be exactly ['LOT_COUNT', 'WF_QTY', 'DIE_QTY']."
        )
    if kind == "aggregate_wip_total":
        return "Return one row with SCOPE=plan.scope_label or ALL and WIP=sum(WIP)."
    if kind == "overall_production_wip_target":
        return (
            "Sum PRODUCTION, WIP, and OUT_PLAN independently and return one row. "
            "Do not rename OUT_PLAN to TARGET. The final result_df columns must include ['PRODUCTION', 'WIP', 'OUT_PLAN']; "
            "if you add SCOPE, set it to ALL."
        )
    if kind == "date_split_production_plan_gap":
        return (
            "Aggregate yesterday PRODUCTION and today OUT_PLAN by product_grain, join by product_grain, and calculate "
            "BALANCE=OUT_PLAN-PRODUCTION. In the final result, keep the measure columns named PRODUCTION, OUT_PLAN, "
            f"and BALANCE. The final result_df columns must be exactly product_grain {product_keys} plus "
            "['PRODUCTION', 'OUT_PLAN', 'BALANCE']; do not use names like yesterday_PRODUCTION or today_OUT_PLAN."
        )
    if kind == "equipment_by_model":
        return "Group equipment rows by EQP_MODEL, calculate EQP_COUNT=EQPID.nunique() and PRESS_CNT=sum(PRESS_CNT)."
    return "Return an empty DataFrame with no rows."


def execute_generated_pandas_code(
    pandas_plan: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
    state: dict[str, Any],
) -> dict[str, Any]:
    code = strip_harmless_pandas_import(str(pandas_plan.get("code", "")))
    safety_errors = check_code_safety(code)
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

    sources = {alias: pd.DataFrame(rows) for alias, rows in runtime_sources.items()}
    local_vars: dict[str, Any] = {"pd": pd, "sources": sources, "plan": deepcopy(plan), "state": deepcopy(state)}
    safe_globals = {"__builtins__": safe_builtins(), "pd": pd}
    try:
        exec(compile(code, "<llm_pandas_code>", "exec"), safe_globals, local_vars)
        result_df = local_vars.get("result_df")
        if result_df is None or not hasattr(result_df, "to_dict"):
            raise ValueError("Generated code must assign a pandas DataFrame to result_df.")
        result_df = result_df.copy()
        result_df = normalize_result_columns(result_df, plan)
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
            "safety_passed": True,
            "executed": False,
        }

    rows = result_df.to_dict(orient="records")
    return {
        "status": "ok",
        "analysis_kind": plan.get("analysis_kind"),
        "analysis_code": code,
        "columns": list(result_df.columns),
        "rows": _json_ready(rows),
        "row_count": len(rows),
        "intermediate_refs": {},
        "errors": [],
        "safety_passed": True,
        "executed": True,
    }


def normalize_result_columns(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    result = frame.copy()
    rename_map: dict[str, str] = {}
    analysis_kind = plan.get("analysis_kind")

    for base_name in ["PRODUCTION", "WIP", "OUT_PLAN", "TARGET_QTY", "LOT_COUNT", "WF_QTY", "DIE_QTY", "PRESS_CNT"]:
        for suffix in ("_sum", "_total"):
            alias = f"{base_name}{suffix}"
            if base_name not in result.columns and alias in result.columns:
                rename_map[alias] = base_name

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
    return order_result_columns(result, plan)


def order_result_columns(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    preferred = preferred_columns(plan)
    if not preferred:
        return frame
    ordered = [column for column in preferred if column in frame.columns]
    remaining = [column for column in frame.columns if column not in ordered]
    return frame[ordered + remaining]


def preferred_columns(plan: dict[str, Any]) -> list[str]:
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
    return []


def strip_harmless_pandas_import(code: str) -> str:
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped in {"import pandas as pd", "import pandas"}:
            continue
        lines.append(line)
    return rewrite_pandas_compatibility("\n".join(lines).strip())


def rewrite_pandas_compatibility(code: str) -> str:
    # Keep validation behavior aligned with the production Langflow component.
    return re.sub(r"(?<![\w.])pd\.inf\b", 'float("inf")', code, flags=re.IGNORECASE)


def check_code_safety(code: str) -> list[str]:
    if not code:
        return ["Generated pandas code is empty."]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"Generated pandas code has syntax error: {exc}"]

    errors = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errors.append("Imports are not allowed in generated pandas code.")
        if isinstance(node, ast.Call):
            name = call_name(node.func)
            if name in FORBIDDEN_CALL_NAMES:
                errors.append(f"Forbidden call: {name}")
            root = name.split(".", 1)[0] if name else ""
            if root in FORBIDDEN_ROOT_NAMES:
                errors.append(f"Forbidden call root: {root}")
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_ROOT_NAMES:
            errors.append(f"Forbidden name: {node.id}")
        if isinstance(node, ast.Attribute):
            value_name = root_name(node.value)
            if value_name in FORBIDDEN_ROOT_NAMES:
                errors.append(f"Forbidden attribute root: {value_name}")
    return sorted(set(errors))


def call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = call_name(func.value)
        return f"{prefix}.{func.attr}" if prefix else func.attr
    return ""


def root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return root_name(node.value)
    return ""


def safe_builtins() -> dict[str, Any]:
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


def check_case(case: dict[str, Any], payload: dict[str, Any], llm_intent: dict[str, Any]) -> list[dict[str, Any]]:
    datasets = set(payload["applied_scope"].get("datasets", []))
    columns = set(payload["data"].get("columns", []))
    filter_fields = filter_fields_from_payload(payload)
    expected_datasets = set(case.get("expected_datasets", []))
    expected_columns = set(case.get("expected_columns", []))
    llm_datasets = set(llm_intent.get("datasets", []))

    checks = [
        check("intent_llm_invoked", True, payload["llm_validation"].get("intent_llm_invoked")),
        check("pandas_llm_invoked", True, payload["llm_validation"].get("pandas_llm_invoked")),
        check("pandas_code_safety_passed", True, payload["llm_validation"].get("pandas_code_safety_passed")),
        check("pandas_code_executed", True, payload["llm_validation"].get("pandas_code_executed")),
        check("llm_expected_analysis_kind", case.get("expected_analysis_kind"), llm_intent.get("analysis_kind")),
        check("normalized_expected_analysis_kind", case.get("expected_analysis_kind"), payload["intent_plan"].get("analysis_kind")),
        {
            "name": "llm_expected_datasets",
            "passed": expected_datasets.issubset(llm_datasets),
            "expected": sorted(expected_datasets),
            "actual": sorted(llm_datasets),
        },
        {
            "name": "normalized_expected_datasets",
            "passed": expected_datasets.issubset(datasets),
            "expected": sorted(expected_datasets),
            "actual": sorted(datasets),
        },
        {
            "name": "expected_columns",
            "passed": expected_columns.issubset(columns),
            "expected": sorted(expected_columns),
            "actual": list(payload["data"].get("columns", [])),
        },
        {
            "name": "non_empty_result",
            "passed": payload["data"].get("row_count", 0) > 0,
            "expected": "row_count > 0",
            "actual": payload["data"].get("row_count", 0),
        },
    ]
    if case.get("expected_intent_type"):
        checks.append(check("llm_expected_intent_type", case["expected_intent_type"], llm_intent.get("intent_type")))
        checks.append(check("normalized_expected_intent_type", case["expected_intent_type"], payload["intent_plan"].get("intent_type")))
    if case.get("expected_filter_fields"):
        checks.append(
            {
                "name": "expected_filter_fields",
                "passed": set(case["expected_filter_fields"]).issubset(filter_fields),
                "expected": case["expected_filter_fields"],
                "actual": sorted(filter_fields),
            }
        )
    if case.get("forbidden_filter_fields"):
        forbidden = set(case["forbidden_filter_fields"]).intersection(filter_fields)
        checks.append(
            {
                "name": "forbidden_filter_fields",
                "passed": not forbidden,
                "expected": f"not present: {case['forbidden_filter_fields']}",
                "actual": sorted(forbidden),
            }
        )
    if case.get("expected_params_by_dataset"):
        checks.append(check_params_by_dataset(case["expected_params_by_dataset"], payload))
    if case["id"] == "multi_step_rank_wip_with_production":
        checks.append(
            {
                "name": "rank_group_split",
                "passed": sorted({row.get("RANK_GROUP") for row in payload["data"].get("rows", [])}) == ["DA", "WB"],
                "expected": ["DA", "WB"],
                "actual": sorted({row.get("RANK_GROUP") for row in payload["data"].get("rows", [])}),
            }
        )
    if case["id"] == "followup_equipment_for_product":
        checks.append(
            {
                "name": "followup_uses_state",
                "passed": bool(payload["intent_plan"].get("state_product_keys")),
                "expected": "state_product_keys not empty",
                "actual": payload["intent_plan"].get("state_product_keys"),
            }
        )
    return checks


def check(name: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {"name": name, "passed": actual == expected, "expected": expected, "actual": actual}


def filter_fields_from_payload(payload: dict[str, Any]) -> set[str]:
    fields = set()
    for filters in payload["applied_scope"].get("filters_by_source", {}).values():
        for condition in filters:
            if condition.get("field"):
                fields.add(condition["field"])
    return fields


def check_params_by_dataset(expected: dict[str, dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    actual: dict[str, list[dict[str, Any]]] = {}
    for result in payload.get("source_results", []):
        actual.setdefault(result["dataset_key"], []).append(result.get("applied_params", {}))
    passed = True
    for dataset_key, expected_params in expected.items():
        candidate_params = actual.get(dataset_key, [])
        if not any(all(params.get(key) == value for key, value in expected_params.items()) for params in candidate_params):
            passed = False
    return {"name": "expected_params_by_dataset", "passed": passed, "expected": expected, "actual": actual}


def call_llm_json(llm: Any, prompt: str) -> dict[str, Any]:
    response = llm.invoke(prompt)
    text = str(getattr(response, "content", response))
    return {"text": text, "json": extract_json_object(text)}


def extract_json_object(text: str) -> dict[str, Any]:
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


def load_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.question:
        return [{"id": "adhoc_question", "question": args.question, "expected_datasets": [], "expected_columns": []}]
    questions = read_json(PROJECT_ROOT / "metadata" / "regression_questions.json")
    if args.case:
        allowed = set(args.case)
        questions = [item for item in questions if item["id"] in allowed or item["question"] in allowed]
    if args.limit and args.limit > 0:
        questions = questions[: args.limit]
    return questions


def compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "answer_message": payload.get("answer_message"),
        "llm_validation": payload.get("llm_validation"),
        "intent_type": payload.get("intent_plan", {}).get("intent_type"),
        "analysis_kind": payload.get("intent_plan", {}).get("analysis_kind"),
        "retrieval_jobs": _retrieval_jobs(payload),
        "source_results": payload.get("source_results", []),
        "analysis": payload.get("analysis", {}),
        "data": payload.get("data", {}),
        "applied_scope": payload.get("applied_scope", {}),
        "errors": payload.get("errors", []),
    }


def _retrieval_jobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    return plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []


def build_report(results: list[dict[str, Any]]) -> str:
    lines = ["# LLM In The Loop Validation Report", ""]
    passed_count = sum(1 for item in results if item["passed"])
    lines.append(f"- Passed: {passed_count}/{len(results)}")
    lines.append("- LLM path: question -> Gemini intent JSON -> normalizer -> retrieval -> Gemini pandas code JSON -> safety check -> pandas execution -> answer")
    lines.append("")
    for item in results:
        mark = "PASS" if item["passed"] else "FAIL"
        lines.append(f"## {mark} {item['id']}")
        lines.append("")
        lines.append(f"- question: `{item['question']}`")
        payload = item.get("payload", {})
        lines.append(f"- answer: `{payload.get('answer_message', '')}`")
        lines.append(f"- analysis_kind: `{payload.get('analysis_kind')}`")
        lines.append(f"- datasets: `{payload.get('applied_scope', {}).get('datasets', [])}`")
        for check_item in item["checks"]:
            check_mark = "PASS" if check_item["passed"] else "FAIL"
            lines.append(f"- {check_mark} {check_item['name']}")
            lines.append(f"  - expected: `{check_item['expected']}`")
            lines.append(f"  - actual: `{check_item['actual']}`")
        lines.append("")
    return "\n".join(lines)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def first_env_value(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, "") or default)
    except ValueError:
        return default


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
