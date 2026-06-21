from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from reference_runtime import run_agent


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    questions = _read_json(PROJECT_ROOT / "metadata" / "regression_questions.json")
    results = []
    state_by_case: dict[str, dict] = {}

    for case in questions:
        state = {}
        if case.get("requires_state_from"):
            state = state_by_case[case["requires_state_from"]]

        payload = run_agent(case["question"], state=state, session_id="regression", root=str(PROJECT_ROOT))
        checks = _check_case(case, payload)
        passed = all(check["passed"] for check in checks)
        results.append({"id": case["id"], "passed": passed, "checks": checks, "payload": _compact_payload(payload)})
        state_by_case[case["id"]] = payload["state"]

    run_dir = PROJECT_ROOT / "validation_runs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(_build_report(results), encoding="utf-8")

    passed_count = sum(1 for item in results if item["passed"])
    print(f"{passed_count}/{len(results)} regression cases passed")
    print(f"report: {run_dir / 'REPORT.md'}")
    return 0 if passed_count == len(results) else 1


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _check_case(case: dict, payload: dict) -> list[dict]:
    datasets = set(payload["applied_scope"].get("datasets", []))
    columns = set(payload["data"].get("columns", []))
    filter_fields = _filter_fields(payload)
    checks = [
        {
            "name": "expected_datasets",
            "passed": set(case.get("expected_datasets", [])).issubset(datasets),
            "expected": case.get("expected_datasets", []),
            "actual": sorted(datasets),
        },
        {
            "name": "expected_columns",
            "passed": set(case.get("expected_columns", [])).issubset(columns),
            "expected": case.get("expected_columns", []),
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
        checks.append(
            {
                "name": "expected_intent_type",
                "passed": payload["intent_plan"].get("intent_type") == case["expected_intent_type"],
                "expected": case["expected_intent_type"],
                "actual": payload["intent_plan"].get("intent_type"),
            }
        )
    if case.get("expected_analysis_kind"):
        checks.append(
            {
                "name": "expected_analysis_kind",
                "passed": payload["intent_plan"].get("analysis_kind") == case["expected_analysis_kind"],
                "expected": case["expected_analysis_kind"],
                "actual": payload["intent_plan"].get("analysis_kind"),
            }
        )
    if case.get("expected_step_ids"):
        checks.append(
            {
                "name": "expected_step_ids",
                "passed": payload["applied_scope"].get("step_ids", []) == case["expected_step_ids"],
                "expected": case["expected_step_ids"],
                "actual": payload["applied_scope"].get("step_ids", []),
            }
        )
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
        checks.append(_check_params_by_dataset(case["expected_params_by_dataset"], payload))
    if case["id"] == "multi_step_rank_wip_with_production":
        step_ids = payload["applied_scope"].get("step_ids", [])
        checks.append(
            {
                "name": "multi_step_order",
                "passed": step_ids
                == [
                    "rank_wip_by_process_group",
                    "aggregate_production_for_ranked_products",
                    "join_rank_and_production",
                ],
                "expected": "rank -> dependent production -> join",
                "actual": step_ids,
            }
        )
        rank_groups = sorted({row.get("RANK_GROUP") for row in payload["data"].get("rows", [])})
        checks.append(
            {
                "name": "rank_group_split",
                "passed": rank_groups == ["DA", "WB"],
                "expected": ["DA", "WB"],
                "actual": rank_groups,
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


def _filter_fields(payload: dict) -> set[str]:
    fields = set()
    for filters in payload["applied_scope"].get("filters_by_source", {}).values():
        for condition in filters:
            if condition.get("field"):
                fields.add(condition["field"])
    return fields


def _check_params_by_dataset(expected: dict, payload: dict) -> dict:
    actual: dict[str, list[dict]] = {}
    for result in payload.get("source_results", []):
        actual.setdefault(result["dataset_key"], []).append(result.get("applied_params", {}))
    passed = True
    for dataset_key, expected_params in expected.items():
        candidate_params = actual.get(dataset_key, [])
        if not any(all(params.get(key) == value for key, value in expected_params.items()) for params in candidate_params):
            passed = False
    return {
        "name": "expected_params_by_dataset",
        "passed": passed,
        "expected": expected,
        "actual": actual,
    }


def _compact_payload(payload: dict) -> dict:
    return {
        "status": payload["status"],
        "answer_message": payload["answer_message"],
        "intent_type": payload["intent_plan"].get("intent_type"),
        "analysis_kind": payload["intent_plan"].get("analysis_kind"),
        "retrieval_jobs": payload.get("retrieval_jobs", []),
        "data": payload.get("data", {}),
        "applied_scope": payload.get("applied_scope", {}),
        "errors": payload.get("errors", []),
    }


def _build_report(results: list[dict]) -> str:
    lines = ["# Regression Validation Report", ""]
    passed_count = sum(1 for item in results if item["passed"])
    lines.append(f"- Passed: {passed_count}/{len(results)}")
    lines.append("")
    for item in results:
        mark = "PASS" if item["passed"] else "FAIL"
        lines.append(f"## {mark} {item['id']}")
        lines.append("")
        for check in item["checks"]:
            check_mark = "PASS" if check["passed"] else "FAIL"
            lines.append(f"- {check_mark} {check['name']}")
            lines.append(f"  - expected: `{check['expected']}`")
            lines.append(f"  - actual: `{check['actual']}`")
        lines.append("")
    return "\n".join(lines)


def _read_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    raise SystemExit(main())
