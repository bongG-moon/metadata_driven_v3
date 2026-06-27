from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools import validate_component_llm_flow as component_flow
from tools import validate_llm_in_loop as llm_tools


REQUEST_DATE = "20260627"


CASES: list[dict[str, Any]] = [
    {
        "id": "current_da_wip_total",
        "question": "현재 DA공정 재공 수량 알려줘",
        "expected_datasets": {"wip_today"},
        "expected_analysis_any": {"aggregate_wip_total"},
        "expected_columns_any": {"WIP"},
        "expected_filter_fields_any": {"OPER_NAME", "OPER_SHORT_DESC"},
        "forbid_function_case": True,
    },
    {
        "id": "today_hbm_production_registered_product",
        "question": "오늘 HBM 제품 생산량 알려줘",
        "expected_datasets": {"production_today"},
        "expected_columns_any": {"PRODUCTION"},
        "expected_filter_fields_any": {"TSV_DIE_TYP", "PKG_TYPE1", "PROD_TYP", "MODE", "TECH", "PRODUCT_GROUP"},
        "forbid_function_case": True,
    },
    {
        "id": "today_lpddr4_lc_64g_product_production",
        "question": "오늘 lpddr4 lc 64g 제품 생산량 알려줘",
        "expected_datasets": {"production_today"},
        "expected_columns_any": {"PRODUCTION", "TOTAL_PRODUCTION_QTY"},
        "expect_function_case": "component_token_product_lookup",
        "expect_helper_call": "match_product_tokens",
    },
    {
        "id": "yesterday_product_token_production_wip_by_process",
        "question": "512G G-777 제품의 어제 생산량과 재공을 세부 공정별로 알려줘",
        "expected_datasets": {"production", "wip"},
        "expected_columns_any": {"PRODUCTION", "WIP"},
        "expected_group_or_output_any": {"OPER_NAME", "OPER_SHORT_DESC", "OPER_NUM"},
        "expect_function_case": "component_token_product_lookup",
        "expect_helper_call": "match_product_tokens",
    },
    {
        "id": "today_da_wb_top_wip_then_production",
        "question": "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘",
        "expected_datasets": {"wip_today", "production_today"},
        "expected_columns_any": {"WIP", "PRODUCTION"},
        "expected_analysis_any": {"rank_wip_then_join_production", "multi_step_analysis", "aggregate_join"},
        "forbid_function_case": True,
    },
    {
        "id": "yesterday_top_production_then_current_wip",
        "question": "어제 생산량 상위 5개 제품을 찾고, 그 제품들의 현재 재공 수량도 같이 보여줘",
        "expected_datasets": {"production", "wip_today"},
        "expected_columns_any": {"PRODUCTION", "WIP", "YESTERDAY_PRODUCTION_QTY", "CURRENT_WIP_QTY"},
        "forbid_function_case": True,
    },
    {
        "id": "today_top_wip_then_hold_lots_avg_in_tat",
        "question": "오늘 재공이 많은 제품 TOP 3를 찾고, 각 제품의 HOLD Lot 수와 평균 IN_TAT도 알려줘",
        "expected_datasets": {"wip_today", "lot_status"},
        "expected_columns_any": {"WIP"},
        "expected_group_or_output_any": {"HOLD_LOT_COUNT", "AVG_IN_TAT", "IN_TAT", "LOT_ID"},
        "forbid_function_case": True,
    },
    {
        "id": "ambiguous_product_token_no_dataset",
        "question": "64G L-269 ASSY 제품 찾아줘",
        "expected_no_retrieval_jobs": True,
        "expect_function_case_if_planned": "component_token_product_lookup",
    },
    {
        "id": "lot_hold_history_detail",
        "question": "T1234567GEN1 LOT의 HOLD이력 알려줘",
        "expected_datasets": {"hold_history"},
        "expected_columns_any": {"LOT_ID", "HOLD_CD", "HOLD_DESC", "HOLD_TM"},
        "forbid_function_case": True,
    },
    {
        "id": "current_hold_lot_in_tat_by_process",
        "question": "현재 hold된 lot 중 IN_TAT 24시간 이상인 Lot을 공정별로 집계해서 보여줘",
        "expected_datasets": {"lot_status"},
        "expected_columns_any": {"LOT_ID", "IN_TAT", "LOT_COUNT"},
        "expected_group_or_output_any": {"OPER_SHORT_DESC", "OPER_NAME", "LOT_COUNT"},
        "forbid_function_case": True,
    },
]


def main() -> int:
    component_flow.install_lfx_stubs()
    llm_tools.load_env_file(PROJECT_ROOT / ".env")
    components = component_flow.load_components()
    metadata = component_flow.load_seed_metadata()
    model_name = os.getenv("LLM_MODEL_NAME", "").strip()
    temperature = float(os.getenv("LLM_TEMPERATURE", "0") or 0)
    llm = llm_tools.build_gemini_llm(model_name, temperature)
    prompt_dir = PROJECT_ROOT / "langflow_components" / "data_analysis_flow" / "prompts"
    specialized_intent = (prompt_dir / "02_SPECIALIZED_INTENT_PROMPT.md").read_text(encoding="utf-8")
    specialized_functions = (prompt_dir / "SPECIALIZED_FUNCTIONS_INPUT_GUIDE.md").read_text(encoding="utf-8")

    results = []
    for case in CASES:
        print(f"RUN {case['id']}: {case['question']}", flush=True)
        try:
            result = run_case(case, components, metadata, llm, specialized_intent, specialized_functions)
        except Exception as exc:
            result = {
                "id": case["id"],
                "question": case["question"],
                "passed": False,
                "checks": [
                    {
                        "name": "exception",
                        "passed": False,
                        "expected": "no exception",
                        "actual": f"{type(exc).__name__}: {exc}",
                    }
                ],
                "summary": {},
            }
        results.append(result)
        print(("PASS" if result["passed"] else "FAIL") + " " + case["id"], flush=True)

    run_dir = PROJECT_ROOT / "validation_runs" / datetime.now().strftime("%Y%m%d_%H%M%S_current_stage_component_llm")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(build_report(results, model_name), encoding="utf-8")
    passed = sum(1 for result in results if result["passed"])
    print(f"{passed}/{len(results)} current-stage component LLM cases passed")
    print(f"report: {run_dir / 'REPORT.md'}")
    return 0 if passed == len(results) else 1


def run_case(
    case: dict[str, Any],
    components: dict[str, Any],
    metadata: dict[str, Any],
    llm: Any,
    specialized_intent: str,
    specialized_functions: str,
) -> dict[str, Any]:
    payload = components["request_loader"].build_request_payload(case["question"], "current-stage-validation")
    payload.setdefault("request", {})["date"] = REQUEST_DATE
    payload["metadata"] = metadata
    payload["metadata_context"] = {
        "domain_refs": [],
        "table_refs": [],
        "filter_refs": [],
        "metadata_load": {"source": "seed-json"},
    }

    intent_prompt = components["intent_prompt_builder"].build_intent_prompt_payload(payload, specialized_intent)["prompt"]
    intent_raw = llm_tools.call_llm_json(llm, intent_prompt)
    payload = components["intent_normalizer"].normalize_intent_payload(
        payload,
        json.dumps(intent_raw["json"], ensure_ascii=False),
    )
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}

    retrieval_payload = components["dummy_retriever"].retrieve_dummy_data(payload)
    payload = components["retrieval_adapter"].adapt_retrieval_payload(payload, retrieval_payload)

    pandas_raw = {"json": {}, "text": ""}
    pandas_repair_raw = None
    repair_payload: dict[str, Any] = {}
    if plan.get("retrieval_jobs"):
        pandas_prompt_payload = components["pandas_prompt_builder"].build_pandas_prompt_payload(payload, specialized_functions)
        pandas_raw = llm_tools.call_llm_json(llm, pandas_prompt_payload["prompt"])
        first_pandas_payload = components["pandas_executor"].execute_pandas_from_llm(
            payload,
            json.dumps(pandas_raw["json"], ensure_ascii=False),
            specialized_functions,
        )
        repair_payload = components["pandas_repair_payload_builder"].build_pandas_repair_payload(first_pandas_payload)
        if (repair_payload.get("pandas_repair") or {}).get("required"):
            repair_prompt = components["pandas_repair_prompt_builder"].build_pandas_repair_prompt_payload(repair_payload)["prompt"]
            pandas_repair_raw = llm_tools.call_llm_json(llm, repair_prompt)
            payload = components["pandas_executor"].execute_pandas_from_llm(
                repair_payload,
                json.dumps(pandas_repair_raw["json"], ensure_ascii=False),
                specialized_functions,
            )
        else:
            payload = repair_payload
        payload = components["answer_builder"].build_answer_response_payload(payload, '{"answer_message":"validation"}')
    else:
        payload = {**payload, "analysis": {}, "data": {"columns": [], "rows": [], "row_count": 0}}

    checks = build_checks(case, payload, pandas_raw)
    return {
        "id": case["id"],
        "question": case["question"],
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "summary": summarize_payload(payload, repair_payload),
        "llm_intent": intent_raw["json"],
        "llm_pandas": pandas_raw["json"],
        "llm_pandas_repair": pandas_repair_raw["json"] if pandas_repair_raw else None,
    }


def build_checks(case: dict[str, Any], payload: dict[str, Any], pandas_raw: dict[str, Any]) -> list[dict[str, Any]]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    datasets = selected_datasets(plan)
    columns = selected_columns(data, analysis)
    fields = applied_filter_fields(payload)
    cases = selected_function_cases(plan)
    step_tokens = step_values(plan, "group_by", "output_columns", "metric", "metrics", "join_keys")
    pandas_json = analysis.get("pandas_code_json") if isinstance(analysis.get("pandas_code_json"), dict) else pandas_raw["json"]
    code = str((pandas_json or {}).get("code") or analysis.get("analysis_code") or "")

    checks: list[dict[str, Any]] = []
    add_check(checks, "intent_plan_created", bool(plan), True, bool(plan))
    add_check(checks, "intent_has_reasoning", bool(plan.get("reasoning_steps")), "reasoning_steps not empty", plan.get("reasoning_steps", [])[:3])

    if case.get("expected_no_retrieval_jobs"):
        jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
        add_check(checks, "no_retrieval_jobs_for_ambiguous_source", len(jobs) == 0, 0, len(jobs))
    else:
        add_check(checks, "retrieval_jobs_created", bool(plan.get("retrieval_jobs")), True, plan.get("retrieval_jobs"))
        if case.get("expected_datasets"):
            add_check(checks, "expected_datasets", set(case["expected_datasets"]).issubset(datasets), sorted(case["expected_datasets"]), sorted(datasets))
        if case.get("expected_columns_any"):
            add_check(checks, "expected_columns_any", bool(set(case["expected_columns_any"]) & columns), sorted(case["expected_columns_any"]), sorted(columns))
        add_check(checks, "pandas_code_generated", bool(str(pandas_raw["json"].get("code") or "").strip()), "code not empty", str(pandas_raw["json"].get("code") or "")[:500])
        add_check(checks, "pandas_executor_ok", analysis.get("status") == "ok", "ok", {"status": analysis.get("status"), "errors": analysis.get("errors"), "repairable_errors": analysis.get("repairable_errors")})
        add_check(checks, "pandas_executed", bool(analysis.get("executed")), True, analysis.get("executed"))

    if case.get("expected_analysis_any"):
        actual = {str(plan.get("analysis_kind") or ""), str(plan.get("intent_type") or "")}
        add_check(checks, "expected_analysis_any", bool(set(case["expected_analysis_any"]) & actual), sorted(case["expected_analysis_any"]), sorted(actual))
    if case.get("expected_filter_fields_any"):
        add_check(checks, "expected_filter_fields_any", bool(set(case["expected_filter_fields_any"]) & fields), sorted(case["expected_filter_fields_any"]), sorted(fields))
    if case.get("expected_group_or_output_any"):
        add_check(checks, "expected_group_or_output_any", bool(set(case["expected_group_or_output_any"]) & (step_tokens | columns)), sorted(case["expected_group_or_output_any"]), sorted(step_tokens | columns))
    if case.get("expect_function_case"):
        add_check(checks, "expected_function_case_selected", case["expect_function_case"] in cases, case["expect_function_case"], sorted(cases))
    if case.get("expect_function_case_if_planned") and plan.get("retrieval_jobs"):
        add_check(checks, "expected_function_case_if_planned", case["expect_function_case_if_planned"] in cases, case["expect_function_case_if_planned"], sorted(cases))
    if case.get("forbid_function_case"):
        add_check(checks, "forbid_function_case", not cases, "no pandas_function_case", sorted(cases))
    if case.get("expect_helper_call") and plan.get("retrieval_jobs"):
        add_check(checks, "expected_helper_call_in_generated_or_executed_code", f"{case['expect_helper_call']}(" in code, f"{case['expect_helper_call']}(...) ", code[:500])
    return checks


def summarize_payload(payload: dict[str, Any], repair_payload: dict[str, Any]) -> dict[str, Any]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return {
        "intent_type": plan.get("intent_type"),
        "analysis_kind": plan.get("analysis_kind"),
        "datasets": sorted(selected_datasets(plan)),
        "step_plan": [
            {
                key: step.get(key)
                for key in (
                    "step_id",
                    "operation",
                    "source_alias",
                    "function_case_key",
                    "function_name",
                    "input_text",
                    "group_by",
                    "metric",
                    "output_columns",
                )
                if step.get(key) not in (None, "", [], {})
            }
            for step in (plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else [])
            if isinstance(step, dict)
        ],
        "selected_function_cases": sorted(selected_function_cases(plan)),
        "filter_fields": sorted(applied_filter_fields(payload)),
        "pandas_status": analysis.get("status"),
        "pandas_executed": analysis.get("executed"),
        "pandas_errors": analysis.get("errors"),
        "repair_required": (repair_payload.get("pandas_repair") or {}).get("required") if isinstance(repair_payload, dict) else None,
        "row_count": data.get("row_count"),
        "columns": sorted(selected_columns(data, analysis)),
        "info": payload.get("info", []),
        "warnings": payload.get("warnings", []),
    }


def selected_datasets(plan: dict[str, Any]) -> set[str]:
    datasets = set(plan.get("datasets") if isinstance(plan.get("datasets"), list) else [])
    datasets.update(job.get("dataset_key") for job in plan.get("retrieval_jobs", []) if isinstance(job, dict) and job.get("dataset_key"))
    return {str(dataset) for dataset in datasets if str(dataset or "").strip()}


def selected_columns(data: dict[str, Any], analysis: dict[str, Any]) -> set[str]:
    columns = set(data.get("columns") if isinstance(data.get("columns"), list) else [])
    columns.update(analysis.get("columns") if isinstance(analysis.get("columns"), list) else [])
    return {str(column) for column in columns if str(column or "").strip()}


def step_values(plan: dict[str, Any], *keys: str) -> set[str]:
    values: set[str] = set()
    for step in plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []:
        if not isinstance(step, dict):
            continue
        for key in keys:
            collect_values(values, step.get(key))
    for key in keys:
        collect_values(values, plan.get(key))
    return values


def collect_values(values: set[str], value: Any) -> None:
    if isinstance(value, list):
        values.update(str(item) for item in value if str(item or "").strip())
    elif value not in (None, "", [], {}):
        values.add(str(value))


def selected_function_cases(plan: dict[str, Any]) -> set[str]:
    cases: set[str] = set()
    value = plan.get("pandas_function_case")
    if isinstance(value, dict):
        for key in ("key", "case_key", "function_case_key"):
            if value.get(key):
                cases.add(str(value[key]))
    elif value:
        cases.add(str(value))
    for step in plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []:
        if not isinstance(step, dict):
            continue
        for key in ("function_case_key", "case_key", "key"):
            if step.get(key):
                cases.add(str(step[key]))
    return cases


def applied_filter_fields(payload: dict[str, Any]) -> set[str]:
    fields: set[str] = set()
    for source in payload.get("source_results") if isinstance(payload.get("source_results"), list) else []:
        for item in source.get("applied_filters") if isinstance(source.get("applied_filters"), list) else []:
            if isinstance(item, dict) and item.get("field"):
                fields.add(str(item["field"]))
    return fields


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, expected: Any, actual: Any) -> None:
    checks.append({"name": name, "passed": bool(passed), "expected": expected, "actual": actual})


def build_report(results: list[dict[str, Any]], model_name: str) -> str:
    lines = [
        "# Current Stage Component LLM Validation",
        "",
        f"- Model: {model_name}",
        "- Path: 00 -> 02(+specialized) -> 03 -> 07 -> 13 -> 14(+specialized functions) -> LLM -> 15(+specialized functions) -> 16 repair if needed -> 19",
        f"- Request date: {REQUEST_DATE}",
        "",
    ]
    for result in results:
        lines.append(f"## {'PASS' if result['passed'] else 'FAIL'} {result['id']}")
        lines.append("")
        lines.append(f"- question: `{result['question']}`")
        summary = result.get("summary", {})
        if summary:
            lines.append(f"- intent_type: `{summary.get('intent_type')}`")
            lines.append(f"- analysis_kind: `{summary.get('analysis_kind')}`")
            lines.append(f"- datasets: `{summary.get('datasets')}`")
            lines.append(f"- selected_function_cases: `{summary.get('selected_function_cases')}`")
            lines.append(
                f"- pandas_status: `{summary.get('pandas_status')}`, executed: `{summary.get('pandas_executed')}`, row_count: `{summary.get('row_count')}`"
            )
        for check in result["checks"]:
            lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} {check['name']}")
            lines.append(f"  - expected: `{check['expected']}`")
            actual = str(check["actual"]).replace("`", "'")
            if len(actual) > 900:
                actual = actual[:900] + "..."
            lines.append(f"  - actual: `{actual}`")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
