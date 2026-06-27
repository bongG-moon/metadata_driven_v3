from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

PROMPT_DIR = PROJECT_ROOT / "langflow_components" / "data_analysis_flow" / "prompts"


REQUIRED_TOKENS_BY_FILE = {
    "02_intent_prompt_ko.md": [
        "intent_type",
        "analysis_kind",
        "retrieval_jobs",
        "step_plan",
        "pandas_function_case",
        "apply_pandas_function_case",
    ],
    "02_SPECIALIZED_INTENT_PROMPT.md": [
        "component_token_product_lookup",
        "match_product_tokens",
        "product_terms",
        "equipment_status",
        "lot_status",
    ],
    "14_pandas_prompt_ko.md": [
        "result_df",
        "pd",
        "sources",
        "plan",
        "state",
        "step_outputs",
        "input_step_id",
        "apply_pandas_function_case",
        "function_code",
    ],
    "18_answer_prompt_ko.md": [
        "answer_message",
        "data.rows",
        "column_standardization",
        "PKG_TYPE1",
        "MCP_NO",
    ],
}


VALIDATION_QUESTIONS = [
    "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘",
    "T1234567GEN1 LOT의 HOLD이력 알려줘",
    "현재 hold된 lot list 알려줘",
    "현재 DA공정 재공 수량 알려줘",
    "오늘 D/A1공정에서 목표값 대비해서 생산량이 저조한 제품을 알려줘",
    "오늘 HBM 장비 보유 현황을 EQP_MODEL별로 알려줘",
    "64G L-269P1Q 제품 찾아줘",
    "오늘 lpddr4 lc 64g 제품 생산량 알려줘",
    "오늘 HBM 제품 생산량 알려줘",
    "Lot ID와 Hold 사유, IN_TAT 조건을 섞은 Lot/Hold 조회",
]

REFERENCE_CASE_IDS = [
    "multi_step_rank_wip_with_production",
    "hold_history_detail",
    "hold_lot_list",
    "da_wip_quantity_uses_wip_dataset",
    "da1_low_output_vs_target",
    "hbm_equipment_by_model",
]


def main() -> int:
    failures: list[str] = []
    failures.extend(_validate_prompt_docs())
    failures.extend(_validate_question_matrix())
    reference_passed, reference_failures = _validate_reference_question_contracts()
    component_passed, component_failures = _validate_component_question_contracts()
    failures.extend(reference_failures)
    failures.extend(component_failures)

    if failures:
        print("Prompt language guide validation failed")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Prompt language guide validation passed")
    print(f"- prompt files checked: {len(REQUIRED_TOKENS_BY_FILE)} Korean files")
    print(f"- validation questions checked: {len(VALIDATION_QUESTIONS)}")
    print(f"- deterministic reference question contracts passed: {reference_passed}/{len(REFERENCE_CASE_IDS)}")
    print(f"- component-level product/function-case contracts passed: {component_passed}/4")
    return 0


def _read(filename: str) -> str:
    return (PROMPT_DIR / filename).read_text(encoding="utf-8")


def _validate_prompt_docs() -> list[str]:
    failures = []
    for filename, tokens in REQUIRED_TOKENS_BY_FILE.items():
        text = _read(filename)
        for token in tokens:
            if token not in text:
                failures.append(f"{filename} missing token: {token}")
    return failures


def _validate_question_matrix() -> list[str]:
    failures = []
    matrix = _read("PROMPT_LANGUAGE_VALIDATION_MATRIX.md")
    for question in VALIDATION_QUESTIONS:
        if question not in matrix:
            failures.append(f"validation matrix missing question: {question}")
    return failures


def _validate_reference_question_contracts() -> tuple[int, list[str]]:
    from reference_runtime import run_agent
    from tools import validate_regression

    cases = {
        item["id"]: item
        for item in validate_regression._read_json(PROJECT_ROOT / "metadata" / "regression_questions.json")
    }
    failures = []
    passed = 0
    for case_id in REFERENCE_CASE_IDS:
        case = cases[case_id]
        payload = run_agent(case["question"], state={}, session_id="prompt-language-validation", root=str(PROJECT_ROOT))
        checks = validate_regression._check_case(case, payload)
        failed_checks = [check for check in checks if not check["passed"]]
        if failed_checks:
            failures.append(f"reference case failed: {case_id} -> {[check['name'] for check in failed_checks]}")
        else:
            passed += 1
    return passed, failures


def _validate_component_question_contracts() -> tuple[int, list[str]]:
    from tools import validate_component_llm_flow as component_tools

    component_tools.install_lfx_stubs()
    request_loader = component_tools.load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    normalizer = component_tools.load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    executor = component_tools.load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    metadata = component_tools.load_seed_metadata()

    checks = [
        _check_product_token_detail(request_loader, normalizer, metadata),
        _check_product_token_metric(request_loader, normalizer, metadata),
        _check_product_terms_priority(request_loader, normalizer, metadata),
        _check_missing_function_case_helper_guard(executor),
    ]
    failures = [message for passed, message in checks if not passed]
    return len(checks) - len(failures), failures


def _normalize_with_llm_json(request_loader, normalizer, metadata: dict, question: str, llm_json: dict, request_date: str):
    payload = request_loader.build_request_payload(question, "prompt-language-validation", request_date=request_date)
    payload["metadata"] = metadata
    payload["metadata_context"] = {"domain_refs": [], "table_refs": [], "filter_refs": [], "metadata_load": {"source": "seed-json"}}
    return normalizer.normalize_intent_payload(payload, json.dumps(llm_json, ensure_ascii=False))


def _check_product_token_detail(request_loader, normalizer, metadata: dict) -> tuple[bool, str]:
    question = "64G L-269P1Q 제품 찾아줘"
    llm_json = {
        "intent_type": "detail_lookup",
        "analysis_kind": "detail_rows",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "product_data",
                "params": {"DATE": "20260627"},
                "filters": [
                    {"field": "DEN", "op": "eq", "value": "64G"},
                    {"field": "MCP_NO", "op": "eq", "value": "L-269P1Q"},
                    {"field": "DATE", "op": "eq", "value": "20260627"},
                ],
            }
        ],
        "step_plan": [{"step_id": "filter_product_data", "operation": "filter_data", "source_alias": "product_data"}],
    }
    payload = _normalize_with_llm_json(request_loader, normalizer, metadata, question, llm_json, "20260627")
    plan = payload["intent_plan"]
    fields = _job_filter_fields(payload["retrieval_jobs"][0])
    passed = (
        plan.get("pandas_function_case", {}).get("key") == "component_token_product_lookup"
        and plan.get("pandas_function_case", {}).get("function_name") == "match_product_tokens"
        and plan.get("step_plan", [{}])[0].get("operation") == "apply_pandas_function_case"
        and "DEN" not in fields
        and "MCP_NO" not in fields
    )
    return passed, "component case failed: product token detail should use match_product_tokens"


def _check_product_token_metric(request_loader, normalizer, metadata: dict) -> tuple[bool, str]:
    question = "오늘 lpddr4 lc 64g 제품 생산량 알려줘"
    llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_total",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "params": {"DATE": "20260627"},
                "filters": [
                    {"field": "MODE", "op": "eq", "value": "LPDDR4"},
                    {"field": "DEN", "op": "eq", "value": "64G"},
                    {"field": "PKG_TYPE1", "op": "eq", "value": "LC"},
                    {"field": "DATE", "op": "eq", "value": "20260627"},
                ],
            }
        ],
        "step_plan": [
            {
                "step_id": "total_production",
                "operation": "aggregate_data",
                "source_alias": "production_data",
                "metric": "PRODUCTION",
                "group_by": [],
            }
        ],
    }
    payload = _normalize_with_llm_json(request_loader, normalizer, metadata, question, llm_json, "20260627")
    plan = payload["intent_plan"]
    fields = _job_filter_fields(payload["retrieval_jobs"][0])
    steps = plan.get("step_plan", [])
    passed = (
        plan.get("pandas_function_case", {}).get("key") == "component_token_product_lookup"
        and len(steps) >= 2
        and steps[0].get("operation") == "apply_pandas_function_case"
        and steps[1].get("input_step_id") == "component_token_product_lookup"
        and "MODE" not in fields
        and "DEN" not in fields
        and "PKG_TYPE1" not in fields
        and "DATE" in fields
    )
    return passed, "component case failed: product token metric should helper-filter before aggregation"


def _check_product_terms_priority(request_loader, normalizer, metadata: dict) -> tuple[bool, str]:
    question = "오늘 HBM 제품 생산량 알려줘"
    llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_total",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "params": {"DATE": "20260627"},
                "filters": [{"field": "DATE", "op": "eq", "value": "20260627"}],
            }
        ],
        "step_plan": [
            {
                "step_id": "total_production",
                "operation": "aggregate_data",
                "source_alias": "production_data",
                "metric": "PRODUCTION",
                "group_by": [],
            }
        ],
    }
    payload = _normalize_with_llm_json(request_loader, normalizer, metadata, question, llm_json, "20260627")
    plan = payload["intent_plan"]
    filters = payload["retrieval_jobs"][0].get("filters", [])
    has_hbm_filter = any(
        (
            item.get("field") in {"PKG_TYPE1", "PKG_TYP1"}
            and (item.get("value") == "HBM" or "HBM" in item.get("values", []))
        )
        or (item.get("field") == "TSV_DIE_TYP" and item.get("op") in {"not_empty", "exists"})
        for item in filters
    )
    passed = "pandas_function_case" not in plan and has_hbm_filter
    return passed, "component case failed: HBM product_terms should not use product-token function case"


def _check_missing_function_case_helper_guard(executor) -> tuple[bool, str]:
    payload = {
        "metadata": {
            "domain_items": {
                "pandas_function_cases": {
                    "lot_hold_complex_lookup": {
                        "function_name": "match_lot_hold_conditions",
                        "use_when": "Use for mixed Lot/Hold condition lookup.",
                    }
                }
            }
        },
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "pandas_function_case": {
                "key": "lot_hold_complex_lookup",
                "function_name": "match_lot_hold_conditions",
                "input_text": "T1234567GEN1 Hold info",
            },
            "step_plan": [
                {
                    "step_id": "lot_hold_complex_lookup",
                    "operation": "apply_pandas_function_case",
                    "source_alias": "hold_data",
                    "function_case_key": "lot_hold_complex_lookup",
                    "function_name": "match_lot_hold_conditions",
                    "input_text": "T1234567GEN1 Hold info",
                }
            ],
        },
        "runtime_sources": {"hold_data": [{"LOT_ID": "T1234567GEN1", "HOLD_CD": "QA_HOLD"}]},
        "state": {},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "def match_lot_hold_conditions(input_text, frame):",
                "    return frame.copy()",
                "result_df = match_lot_hold_conditions(plan['pandas_function_case']['input_text'], sources['hold_data'])",
            ]
        ),
        "output_columns": ["LOT_ID", "HOLD_CD"],
        "reasoning_steps": ["Incorrectly synthesize the selected helper."],
    }
    result = executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))
    errors = result.get("analysis", {}).get("errors", [])
    passed = result.get("analysis", {}).get("status") == "error" and any("implementation is missing" in error for error in errors)
    return passed, "component case failed: missing function-case helper should stop execution"


def _job_filter_fields(job: dict) -> set[str]:
    return {str(item.get("field") or "") for item in job.get("filters", []) if isinstance(item, dict)}


if __name__ == "__main__":
    raise SystemExit(main())
