from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools import validate_component_llm_flow as comp
from tools import validate_llm_in_loop as llm_tools


CASES = [
    {"id": "shift_a_fcb1_output", "question": "오늘 Shift A조 FCB1 공정 OUTPUT 가르쳐줘"},
    {"id": "time_shift_fcb1_output", "question": "오늘 07:00 ~ 15:00 까지 FCB1 공정 OUTPUT 가르쳐줘"},
    {"id": "3ds_device_code_today_input", "question": "금일 투입된 3DS 제품 Device 첨자 알려줘"},
    {"id": "da1_input_vs_wip_0624", "question": "6/24 D/A 1차 공정 일 투입 량 대비 WIP 많은 제품 알려줘"},
    {"id": "product_da_16g_fc180_fcb_output_0604", "question": "DA 16G FC180제품 6/4 FCB공정 Out Put 알려줘"},
    {"id": "sbm_wip_without_sg_wip", "question": "SBM공정 WIP있는 제품 중 S/G공정 WIP없는 제품 알려줘"},
    {"id": "sg_wip_over_100k_korean", "question": "오늘 S/G공정에서 재공이 100K이상인 제품 알려줘"},
    {"id": "sg_wip_over_100k_wip", "question": "오늘 S/G공정에서 WIP이 100K이상인 제품 알려줘"},
    {"id": "yesterday_no_input_today_input", "question": "전일 투입 안된 제품 중에 금일 투입 된 제품 알려줘"},
    {"id": "input_lt_out_0624", "question": "6/24 INPUT된 자재 L/T OUT 알려줘"},
    {"id": "da_wb_prod_wip_each", "question": "오늘 da공정 생산량,재공과 wb공정 생산량,재공을 각각 보여줄래?"},
]


def main() -> int:
    comp.install_lfx_stubs()
    llm_tools.load_env_file(PROJECT_ROOT / ".env")
    components = comp.load_components()
    metadata = comp.load_seed_metadata()
    llm = llm_tools.build_gemini_llm(
        os.getenv("LLM_MODEL_NAME", "").strip(),
        float(os.getenv("LLM_TEMPERATURE", "0") or 0),
    )
    request_date = os.getenv("DOMAIN_VALIDATION_DATE") or os.getenv("AGENT_DEFAULT_DATE", "20260625")

    cases = select_cases()
    results = []
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case['id']}: {case['question']}")
        result = run_one(case, request_date, metadata, components, llm)
        results.append(result)
        print(
            "  "
            + ("OK" if result.get("ok") else "CHECK")
            + f" kind={result.get('analysis_kind')}"
            + f" recipe={result.get('matched_analysis_recipe')}"
            + f" rows={result.get('row_count')}"
            + f" cols={result.get('columns')}"
            + f" errors={len(result.get('errors') or [])}"
            + (f" exception={result.get('exception')}" if result.get("exception") else "")
        )

    run_dir = PROJECT_ROOT / "validation_runs" / "domain_problem_cases" / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(build_report(results, request_date), encoding="utf-8")
    print(f"report: {run_dir / 'REPORT.md'}")
    print(f"results: {run_dir / 'results.json'}")
    return 0


def select_cases() -> list[dict[str, str]]:
    case_ids = [value.strip() for value in os.getenv("DOMAIN_VALIDATION_CASE_IDS", "").split(",") if value.strip()]
    if case_ids:
        wanted = set(case_ids)
        return [case for case in CASES if case["id"] in wanted]
    limit = os.getenv("DOMAIN_VALIDATION_LIMIT", "").strip()
    if limit:
        return CASES[: int(limit)]
    return CASES


def run_one(
    case: dict[str, str],
    request_date: str,
    metadata: dict[str, Any],
    components: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {"id": case["id"], "question": case["question"]}
    try:
        payload = components["request_loader"].build_request_payload(
            case["question"],
            "domain-problem-case-validation",
            state={},
        )
        payload.setdefault("request", {})["date"] = request_date
        payload["metadata"] = metadata
        payload["metadata_context"] = {"metadata_load": {"source": "seed-json-from-current-mongodb-export"}}

        intent_prompt = components["intent_prompt_builder"].build_intent_prompt_payload(payload)["prompt"]
        intent_json = llm_tools.call_llm_json(llm, intent_prompt)["json"]
        payload = components["intent_normalizer"].normalize_intent_payload(
            payload,
            json.dumps(intent_json, ensure_ascii=False),
        )

        retrieval_payload = components["dummy_retriever"].retrieve_dummy_data(payload)
        payload = components["retrieval_adapter"].adapt_retrieval_payload(payload, retrieval_payload)

        pandas_prompt = components["pandas_prompt_builder"].build_pandas_prompt_payload(payload)["prompt"]
        pandas_json = llm_tools.call_llm_json(llm, pandas_prompt)["json"]
        first_payload = components["pandas_executor"].execute_pandas_from_llm(
            payload,
            json.dumps(pandas_json, ensure_ascii=False),
        )

        repair_payload = components["pandas_repair_payload_builder"].build_pandas_repair_payload(first_payload)
        repair_json = None
        final_payload = first_payload
        if (repair_payload.get("pandas_repair") or {}).get("required"):
            repair_prompt = components["pandas_repair_prompt_builder"].build_pandas_repair_prompt_payload(repair_payload)[
                "prompt"
            ]
            repair_json = llm_tools.call_llm_json(llm, repair_prompt)["json"]
            final_payload = components["pandas_executor"].execute_pandas_from_llm(
                repair_payload,
                json.dumps(repair_json, ensure_ascii=False),
            )

        analysis = final_payload.get("analysis") if isinstance(final_payload.get("analysis"), dict) else {}
        data = final_payload.get("data") if isinstance(final_payload.get("data"), dict) else {}
        pandas_info = final_payload.get("pandas") if isinstance(final_payload.get("pandas"), dict) else {}
        result_columns = data.get("columns") or analysis.get("columns") or []
        result_rows = data.get("rows") or analysis.get("rows") or []
        result_row_count = data.get("row_count")
        if result_row_count is None:
            result_row_count = analysis.get("row_count")
        result_errors = final_payload.get("errors") or analysis.get("errors") or []
        result_warnings = final_payload.get("warnings") or []
        result.update(
            {
                "ok": not result_errors and (result_row_count or 0) > 0,
                "intent_type": (final_payload.get("intent_plan") or {}).get("intent_type"),
                "analysis_kind": (final_payload.get("intent_plan") or {}).get("analysis_kind"),
                "matched_analysis_recipe": (final_payload.get("intent_plan") or {}).get("matched_analysis_recipe"),
                "datasets": (final_payload.get("applied_scope") or {}).get("datasets"),
                "retrieval_jobs": summarize_jobs(final_payload),
                "columns": result_columns,
                "row_count": result_row_count,
                "rows_preview": result_rows[:5],
                "errors": result_errors,
                "warnings": result_warnings,
                "pandas_status": pandas_info.get("status") or analysis.get("status"),
                "pandas_executed": pandas_info.get("executed") if "executed" in pandas_info else analysis.get("executed"),
                "pandas_safety_ok": pandas_info.get("safety_ok")
                if "safety_ok" in pandas_info
                else analysis.get("safety_passed"),
                "pandas_code": pandas_info.get("executed_code")
                or pandas_info.get("analysis_code")
                or analysis.get("analysis_code")
                or pandas_json.get("code")
                or pandas_json.get("analysis_code"),
                "pandas_raw": pandas_json,
                "repair_required": bool((repair_payload.get("pandas_repair") or {}).get("required")),
                "repair_json": repair_json,
                "intent_raw": intent_json,
            }
        )
    except Exception as exc:
        result.update({"ok": False, "exception": f"{type(exc).__name__}: {exc}"})
    return result


def summarize_jobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for job in payload.get("retrieval_jobs", []):
        if not isinstance(job, dict):
            continue
        rows.append(
            {
                "dataset_key": job.get("dataset_key"),
                "source_alias": job.get("source_alias"),
                "params": job.get("params") or job.get("query_params") or {},
                "filters": job.get("filters") or [],
                "required_columns": job.get("required_columns") or [],
            }
        )
    return rows


def build_report(results: list[dict[str, Any]], request_date: str) -> str:
    lines = ["# Domain Problem Case Validation", "", f"- Request date: {request_date}", f"- Cases: {len(results)}", ""]
    for item in results:
        lines.extend(
            [
                f"## {'OK' if item.get('ok') else 'CHECK'} {item['id']}",
                "",
                f"- Question: {item['question']}",
                f"- Intent: {item.get('intent_type')} / {item.get('analysis_kind')}",
                f"- Recipe: {item.get('matched_analysis_recipe')}",
                f"- Datasets: {item.get('datasets')}",
                f"- Rows/Columns: {item.get('row_count')} / {item.get('columns')}",
            ]
        )
        if item.get("exception"):
            lines.append(f"- Exception: `{item['exception']}`")
        if item.get("errors"):
            lines.append(f"- Errors: `{item.get('errors')}`")
        if item.get("warnings"):
            lines.append(f"- Warnings: `{item.get('warnings')[:3]}`")
        lines.append("- Retrieval jobs:")
        for job in item.get("retrieval_jobs") or []:
            lines.append(
                f"  - {job.get('source_alias')}:{job.get('dataset_key')} "
                f"params={job.get('params')} filters={job.get('filters')}"
            )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
