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


PRODUCT_STATE = {
    "current_data": {
        "columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "WIP"],
        "rows": [
            {
                "TECH": "FC",
                "DEN": "128G",
                "MODE": "LPDDR5",
                "PKG_TYPE1": "UFBGA",
                "PKG_TYPE2": "MOBILE",
                "LEAD": "LF",
                "MCP_NO": "EMPTY",
                "WIP": 10,
            }
        ],
        "product_key_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
        "product_key_values": [
            {
                "TECH": "FC",
                "DEN": "128G",
                "MODE": "LPDDR5",
                "PKG_TYPE1": "UFBGA",
                "PKG_TYPE2": "MOBILE",
                "LEAD": "LF",
                "MCP_NO": "EMPTY",
            }
        ],
        "product_key_count": 1,
        "data_ref": {"store": "mongodb", "ref_id": "previous-result", "collection_name": "agent_v3_result_store"},
    }
}


CASES: list[dict[str, Any]] = [
    {
        "id": "mongo_product_production_wip_join_today",
        "question": "오늘 DA공정에서 재공과 생산량을 제품별로 알려줘",
        "expected_recipe": "product_production_wip_join",
        "expected_datasets": {"production_today", "wip_today"},
        "expected_ops": ["aggregate_by_group", "aggregate_by_group", "left_join"],
        "expected_columns_any": {"PRODUCTION", "WIP"},
    },
    {
        "id": "mongo_product_production_wip_join_yesterday",
        "question": "어제 DA공정에서 재공과 생산량을 제품별로 알려줘",
        "expected_recipe": "product_production_wip_join",
        "expected_datasets": {"production", "wip"},
        "expected_ops": ["aggregate_by_group", "aggregate_by_group", "left_join"],
        "expected_columns_any": {"PRODUCTION", "WIP"},
    },
    {
        "id": "mongo_rank_wip_then_join_production",
        "question": "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘",
        "expected_recipe": "rank_wip_then_join_production",
        "expected_datasets": {"wip_today", "production_today"},
        "expected_ops": ["rank_top_n", "aggregate_by_group", "left_join"],
        "expected_columns_any": {"WIP", "PRODUCTION"},
    },
    {
        "id": "mongo_lot_quantity_summary",
        "question": "현재 DA공정에서 재공 lot은 몇개고 wafer와 die 수량은 몇개야?",
        "expected_recipe": "lot_quantity_summary",
        "expected_datasets": {"lot_status"},
        "expected_ops": ["aggregate_by_group"],
        "expected_columns_any": {"LOT_COUNT", "WF_QTY", "DIE_QTY"},
    },
    {
        "id": "mongo_top_wip_process_hold_lot_in_tat",
        "question": "오늘 재공이 많은 세부공정 top 3을 찾고, 해당 공정의 HOLD Lot 수와 평균 IN_TAT도 알려줘",
        "expected_recipe": "top_wip_process_hold_lot_in_tat",
        "expected_datasets": {"wip_today", "lot_status"},
        "expected_ops": ["rank_top_n", "aggregate_by_group", "left_join"],
        "expected_columns_any": {"WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"},
    },
    {
        "id": "mongo_top_wip_product_oldest_lot",
        "question": "현재 재공이 가장 많은 제품을 찾고 그 제품의 IN_TAT가 가장 오래된 LOT를 보여줘",
        "expected_recipe": "top_wip_product_oldest_lot",
        "expected_datasets": {"wip_today", "lot_status"},
        "expected_ops": ["rank_top_n", "rank_top_n", "left_join"],
        "expected_columns_any": {"WIP", "LOT_ID", "IN_TAT"},
    },
    {
        "id": "mongo_followup_equipment_count_previous_products",
        "question": "이 제품들의 장비는 몇 대야?",
        "state": PRODUCT_STATE,
        "expected_recipe": "equipment_count_for_previous_products",
        "expected_datasets": {"equipment_status"},
        "expected_ops": ["unique_count_by_group"],
        "expected_columns_any": {"EQP_COUNT"},
    },
]


def main() -> int:
    component_flow.install_lfx_stubs()
    llm_tools.load_env_file(PROJECT_ROOT / ".env")
    components = component_flow.load_components()
    metadata_payload = load_mongodb_metadata()
    metadata = metadata_payload["metadata"]
    model_name = os.getenv("LLM_MODEL_NAME", "").strip()
    llm = llm_tools.build_gemini_llm(model_name, float(os.getenv("LLM_TEMPERATURE", "0") or 0))
    prompt_dir = PROJECT_ROOT / "langflow_components" / "data_analysis_flow" / "prompts"
    specialized_intent = (prompt_dir / "02_SPECIALIZED_INTENT_PROMPT.md").read_text(encoding="utf-8")
    specialized_functions = (prompt_dir / "SPECIALIZED_FUNCTIONS_INPUT_GUIDE.md").read_text(encoding="utf-8")

    results = []
    for case in CASES:
        print(f"RUN {case['id']}: {case['question']}", flush=True)
        try:
            result = run_case(case, components, metadata, metadata_payload, llm, specialized_intent, specialized_functions)
        except Exception as exc:
            result = {
                "id": case["id"],
                "question": case["question"],
                "passed": False,
                "checks": [{"name": "exception", "passed": False, "expected": "no exception", "actual": f"{type(exc).__name__}: {exc}"}],
                "summary": {},
            }
        results.append(result)
        print(("PASS" if result["passed"] else "FAIL") + f" {case['id']}", flush=True)

    run_dir = PROJECT_ROOT / "validation_runs" / datetime.now().strftime("%Y%m%d_%H%M%S_mongodb_recipe_component_llm")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(build_report(results, model_name), encoding="utf-8")
    passed = sum(1 for result in results if result["passed"])
    print(f"{passed}/{len(results)} mongodb recipe component LLM cases passed")
    print(f"report: {run_dir / 'REPORT.md'}")
    return 0 if passed == len(results) else 1


def load_mongodb_metadata() -> dict[str, Any]:
    metadata_loader = component_flow.load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    return metadata_loader.load_metadata_payload(
        {},
        mongo_uri=os.getenv("MONGODB_URI", ""),
        mongo_database=os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v3"),
        domain_collection_name=os.getenv("MONGODB_DOMAIN_COLLECTION", "agent_v3_domain_items"),
        table_catalog_collection_name=os.getenv("MONGODB_TABLE_CATALOG_COLLECTION", "agent_v3_table_catalog_items"),
        main_flow_filter_collection_name=os.getenv("MONGODB_MAIN_FLOW_FILTER_COLLECTION", "agent_v3_main_flow_filters"),
        load_limit="1000",
    )


def run_case(
    case: dict[str, Any],
    components: dict[str, Any],
    metadata: dict[str, Any],
    metadata_payload: dict[str, Any],
    llm: Any,
    specialized_intent: str,
    specialized_functions: str,
) -> dict[str, Any]:
    payload = components["request_loader"].build_request_payload(
        case["question"],
        "mongo-recipe-validation",
        state=case.get("state") or {},
    )
    payload.setdefault("request", {})["date"] = REQUEST_DATE
    payload["metadata"] = metadata
    payload["metadata_context"] = {
        "domain_refs": [],
        "table_refs": [],
        "filter_refs": [],
        "metadata_load": (metadata_payload.get("metadata_context") or {}).get("metadata_load", {"source": "mongodb"}),
    }

    intent_prompt = components["intent_prompt_builder"].build_intent_prompt_payload(payload, specialized_intent)["prompt"]
    intent_raw = llm_tools.call_llm_json(llm, intent_prompt)
    payload = components["intent_normalizer"].normalize_intent_payload(payload, json.dumps(intent_raw["json"], ensure_ascii=False))

    retrieval_payload = components["dummy_retriever"].retrieve_dummy_data(payload)
    payload = components["retrieval_adapter"].adapt_retrieval_payload(payload, retrieval_payload)

    pandas_raw: dict[str, Any] = {"json": {}, "text": ""}
    pandas_repair_raw = None
    if (payload.get("intent_plan") or {}).get("retrieval_jobs"):
        pandas_prompt = components["pandas_prompt_builder"].build_pandas_prompt_payload(payload, specialized_functions)["prompt"]
        pandas_raw = llm_tools.call_llm_json(llm, pandas_prompt)
        payload = components["pandas_executor"].execute_pandas_from_llm(payload, json.dumps(pandas_raw["json"], ensure_ascii=False))
        repair_payload = components["pandas_repair_payload_builder"].build_pandas_repair_payload(payload)
        if (repair_payload.get("pandas_repair") or {}).get("required"):
            repair_prompt = components["pandas_repair_prompt_builder"].build_pandas_repair_prompt_payload(repair_payload)["prompt"]
            pandas_repair_raw = llm_tools.call_llm_json(llm, repair_prompt)
            payload = components["pandas_executor"].execute_pandas_from_llm(repair_payload, json.dumps(pandas_repair_raw["json"], ensure_ascii=False))
        else:
            payload = repair_payload

    checks = checks_for_case(case, payload)
    return {
        "id": case["id"],
        "question": case["question"],
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "summary": summarize_payload(payload),
        "llm_intent": intent_raw.get("json"),
        "llm_pandas": pandas_raw.get("json"),
        "llm_pandas_repair": pandas_repair_raw.get("json") if pandas_repair_raw else None,
    }


def checks_for_case(case: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    datasets = set((payload.get("applied_scope") or {}).get("datasets") or plan.get("datasets") or [])
    operations = [step.get("operation") for step in plan.get("step_plan", []) if isinstance(step, dict)]
    columns = set(analysis.get("columns") or data.get("columns") or [])
    checks = []

    def add(name: str, passed: bool, expected: Any, actual: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "expected": expected, "actual": actual})

    add("matched_recipe", plan.get("matched_analysis_recipe") == case["expected_recipe"], case["expected_recipe"], plan.get("matched_analysis_recipe"))
    add("expected_datasets", case["expected_datasets"].issubset(datasets), sorted(case["expected_datasets"]), sorted(datasets))
    add("expected_step_ops", operations[: len(case["expected_ops"])] == case["expected_ops"], case["expected_ops"], operations)
    add("expected_columns_any", bool(case["expected_columns_any"] & columns), sorted(case["expected_columns_any"]), sorted(columns))
    add("pandas_status_ok", analysis.get("status") == "ok", "ok", analysis.get("status"))
    add("no_executor_fallback", not analysis.get("used_executor_fallback"), False, analysis.get("used_executor_fallback"))
    return checks


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    datasets = (payload.get("applied_scope") or {}).get("datasets") or plan.get("datasets") or []
    return {
        "intent_type": plan.get("intent_type"),
        "analysis_kind": plan.get("analysis_kind"),
        "matched_analysis_recipe": plan.get("matched_analysis_recipe"),
        "datasets": datasets,
        "operations": [step.get("operation") for step in plan.get("step_plan", []) if isinstance(step, dict)],
        "columns": analysis.get("columns") or data.get("columns"),
        "row_count": analysis.get("row_count") or data.get("row_count"),
        "pandas_status": analysis.get("status"),
        "used_executor_fallback": analysis.get("used_executor_fallback"),
        "repairable_errors": analysis.get("repairable_errors") or [],
        "errors": analysis.get("errors") or payload.get("errors"),
    }


def build_report(results: list[dict[str, Any]], model_name: str) -> str:
    lines = [
        "# MongoDB Recipe Component LLM Validation",
        "",
        f"- Model: {model_name}",
        f"- Metadata source: MongoDB {os.getenv('MONGODB_DATABASE', 'metadata_driven_agent_v3')}.{os.getenv('MONGODB_DOMAIN_COLLECTION', 'agent_v3_domain_items')}",
        "",
    ]
    for result in results:
        lines.append(f"## {'PASS' if result['passed'] else 'FAIL'} {result['id']}")
        lines.append("")
        for check in result["checks"]:
            lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} {check['name']}")
            lines.append(f"  - expected: `{check['expected']}`")
            lines.append(f"  - actual: `{check['actual']}`")
        lines.append(f"- summary: `{result.get('summary')}`")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
