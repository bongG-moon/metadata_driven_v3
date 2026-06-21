from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    install_lfx_stubs()
    sys.path.insert(0, str(PROJECT_ROOT))
    from tools import validate_llm_in_loop as llm_tools

    llm_tools.load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Run Gemini validation through the numbered Langflow components.")
    parser.add_argument("--case", action="append", default=[], help="Run only this regression id. Can be repeated.")
    parser.add_argument("--limit", type=int, default=0, help="Max cases to run. 0 means all selected cases.")
    parser.add_argument("--request-date", default=os.getenv("AGENT_DEFAULT_DATE", "20260612"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL_NAME", "").strip())
    parser.add_argument("--temperature", type=float, default=float(os.getenv("LLM_TEMPERATURE", "0") or 0))
    args = parser.parse_args()

    llm = llm_tools.build_gemini_llm(args.model, args.temperature)
    components = load_components()
    metadata = load_seed_metadata()
    cases = load_cases(args.case, args.limit)

    state_by_case: dict[str, dict[str, Any]] = {}
    results = []
    for case in cases:
        state = state_by_case.get(case.get("requires_state_from", ""), {}) if case.get("requires_state_from") else {}
        try:
            result = run_case(case, state, args.request_date, metadata, components, llm, llm_tools)
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
                "payload": {},
                "next_state": state,
            }
        results.append(result)
        state_by_case[case["id"]] = result.get("next_state", state)
        print(("PASS" if result["passed"] else "FAIL") + " " + case["id"])

    run_dir = PROJECT_ROOT / "validation_runs" / datetime.now().strftime("%Y%m%d_%H%M%S_component_llm")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(build_report(results), encoding="utf-8")

    passed = sum(1 for result in results if result["passed"])
    print(f"{passed}/{len(results)} component LLM cases passed")
    print(f"report: {run_dir / 'REPORT.md'}")
    return 0 if passed == len(results) else 1


def install_lfx_stubs() -> None:
    def ensure_module(name: str) -> types.ModuleType:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
        return sys.modules[name]

    ensure_module("lfx")
    ensure_module("lfx.custom")
    ensure_module("lfx.custom.custom_component")
    component_mod = ensure_module("lfx.custom.custom_component.component")
    io_mod = ensure_module("lfx.io")
    ensure_module("lfx.schema")
    data_mod = ensure_module("lfx.schema.data")
    message_mod = ensure_module("lfx.schema.message")

    class Component:
        pass

    class Input:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.name = kwargs.get("name") or (args[0] if args else None)
            for key, value in kwargs.items():
                setattr(self, key, value)

    class Data:
        def __init__(self, data: Any = None, **kwargs: Any) -> None:
            self.data = data if data is not None else kwargs

    class Message:
        def __init__(self, text: str = "", **kwargs: Any) -> None:
            self.text = text
            for key, value in kwargs.items():
                setattr(self, key, value)

    component_mod.Component = Component
    for name in ("DataInput", "MessageTextInput", "Output", "DropdownInput", "BoolInput", "IntInput"):
        setattr(io_mod, name, Input)
    data_mod.Data = Data
    message_mod.Message = Message


def load_components() -> dict[str, Any]:
    return {
        "request_loader": load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py"),
        "intent_prompt_builder": load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py"),
        "intent_normalizer": load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py"),
        "dummy_retriever": load_component("langflow_components/data_analysis_flow/07_dummy_data_retriever.py"),
        "retrieval_adapter": load_component("langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py"),
        "pandas_prompt_builder": load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py"),
        "pandas_executor": load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py"),
        "pandas_repair_payload_builder": load_component(
            "langflow_components/data_analysis_flow/16a_pandas_repair_payload_builder.py"
        ),
        "pandas_repair_prompt_builder": load_component(
            "langflow_components/data_analysis_flow/16b_pandas_repair_prompt_builder.py"
        ),
        "answer_builder": load_component("langflow_components/data_analysis_flow/19_answer_response_builder.py"),
    }


def load_component(path: str) -> Any:
    component_path = PROJECT_ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_seed_metadata() -> dict[str, Any]:
    return {
        "domain_items": read_json(PROJECT_ROOT / "metadata" / "domain_items.json"),
        "table_catalog": read_json(PROJECT_ROOT / "metadata" / "table_catalog.json"),
        "main_flow_filters": read_json(PROJECT_ROOT / "metadata" / "main_flow_filters.json"),
    }


def load_cases(case_ids: list[str], limit: int) -> list[dict[str, Any]]:
    cases = read_json(PROJECT_ROOT / "metadata" / "regression_questions.json")
    if case_ids:
        allowed = set(case_ids)
        cases = [case for case in cases if case["id"] in allowed or case["question"] in allowed]
    if limit > 0:
        cases = cases[:limit]
    return cases


def run_case(
    case: dict[str, Any],
    state: dict[str, Any],
    request_date: str,
    metadata: dict[str, Any],
    components: dict[str, Any],
    llm: Any,
    llm_tools: Any,
) -> dict[str, Any]:
    payload = components["request_loader"].build_request_payload(
        case["question"],
        "component-llm-validation",
        state=state,
    )
    payload.setdefault("request", {})["date"] = request_date
    payload["metadata"] = metadata
    payload["metadata_context"] = {
        "domain_refs": [],
        "table_refs": [],
        "filter_refs": [],
        "metadata_load": {"source": "seed-json"},
    }

    intent_prompt = components["intent_prompt_builder"].build_intent_prompt_payload(payload)["prompt"]
    intent_raw = llm_tools.call_llm_json(llm, intent_prompt)
    payload = components["intent_normalizer"].normalize_intent_payload(
        payload,
        json.dumps(intent_raw["json"], ensure_ascii=False),
    )
    retrieval_payload = components["dummy_retriever"].retrieve_dummy_data(payload)
    payload = components["retrieval_adapter"].adapt_retrieval_payload(payload, retrieval_payload)
    pandas_prompt = components["pandas_prompt_builder"].build_pandas_prompt_payload(payload)["prompt"]
    pandas_raw = llm_tools.call_llm_json(llm, pandas_prompt)
    first_pandas_payload = components["pandas_executor"].execute_pandas_from_llm(
        payload,
        json.dumps(pandas_raw["json"], ensure_ascii=False),
    )
    repair_payload = components["pandas_repair_payload_builder"].build_pandas_repair_payload(first_pandas_payload)
    pandas_repair_raw = None
    if (repair_payload.get("pandas_repair") or {}).get("required"):
        repair_prompt = components["pandas_repair_prompt_builder"].build_pandas_repair_prompt_payload(repair_payload)["prompt"]
        pandas_repair_raw = llm_tools.call_llm_json(llm, repair_prompt)
        payload = components["pandas_executor"].execute_pandas_from_llm(
            repair_payload,
            json.dumps(pandas_repair_raw["json"], ensure_ascii=False),
        )
    else:
        payload = repair_payload
    payload = components["answer_builder"].build_answer_response_payload(
        payload,
        '{"answer_message":"component validation"}',
    )

    checks = checks_for_case(case, payload)
    return {
        "id": case["id"],
        "question": case["question"],
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "payload": {
            "intent_type": payload["intent_plan"].get("intent_type"),
            "analysis_kind": payload["intent_plan"].get("analysis_kind"),
            "retrieval_jobs": payload.get("retrieval_jobs", []),
            "applied_scope": payload.get("applied_scope", {}),
            "data": payload.get("data", {}),
            "info": payload.get("info", []),
            "warnings": payload.get("warnings", []),
            "errors": payload.get("errors", []),
        },
        "llm_intent": intent_raw["json"],
        "llm_pandas": pandas_raw["json"],
        "llm_pandas_repair": pandas_repair_raw["json"] if pandas_repair_raw else None,
        "pandas_repair": payload.get("pandas_repair", {}),
        "next_state": payload.get("state", {}),
    }


def checks_for_case(case: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    datasets = set((payload.get("applied_scope") or {}).get("datasets", []))
    columns = set((payload.get("data") or {}).get("columns", []))
    fields = filter_fields(payload)
    checks = []

    def add(name: str, passed: bool, expected: Any, actual: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "expected": expected, "actual": actual})

    add(
        "normalized_expected_intent_type",
        payload["intent_plan"].get("intent_type") == case.get("expected_intent_type"),
        case.get("expected_intent_type"),
        payload["intent_plan"].get("intent_type"),
    )
    add(
        "normalized_expected_analysis_kind",
        payload["intent_plan"].get("analysis_kind") == case.get("expected_analysis_kind"),
        case.get("expected_analysis_kind"),
        payload["intent_plan"].get("analysis_kind"),
    )
    add(
        "normalized_expected_datasets",
        set(case.get("expected_datasets", [])).issubset(datasets),
        sorted(case.get("expected_datasets", [])),
        sorted(datasets),
    )
    add(
        "expected_columns",
        set(case.get("expected_columns", [])).issubset(columns),
        sorted(case.get("expected_columns", [])),
        list((payload.get("data") or {}).get("columns", [])),
    )
    add(
        "non_empty_result",
        (payload.get("data") or {}).get("row_count", 0) > 0,
        "row_count > 0",
        (payload.get("data") or {}).get("row_count", 0),
    )
    if case.get("expected_filter_fields"):
        add(
            "expected_filter_fields",
            set(case["expected_filter_fields"]).issubset(fields),
            case["expected_filter_fields"],
            sorted(fields),
        )
    if case.get("forbidden_filter_fields"):
        forbidden = set(case["forbidden_filter_fields"]) & fields
        add(
            "forbidden_filter_fields",
            not forbidden,
            f"not present: {case['forbidden_filter_fields']}",
            sorted(forbidden),
        )
    if case.get("expected_params_by_dataset"):
        ok, actual = check_params(case["expected_params_by_dataset"], payload)
        add("expected_params_by_dataset", ok, case["expected_params_by_dataset"], actual)
    if case["id"] == "followup_equipment_for_product":
        add(
            "followup_uses_state",
            bool(payload["intent_plan"].get("state_product_keys")),
            "state_product_keys not empty",
            payload["intent_plan"].get("state_product_keys"),
        )
    return checks


def filter_fields(payload: dict[str, Any]) -> set[str]:
    fields = set()
    for result in payload.get("source_results", []):
        for item in result.get("applied_filters", []):
            if isinstance(item, dict) and item.get("field"):
                fields.add(item["field"])
    return fields


def check_params(expected: dict[str, dict[str, Any]], payload: dict[str, Any]) -> tuple[bool, dict[str, list[dict[str, Any]]]]:
    actual: dict[str, list[dict[str, Any]]] = {}
    for result in payload.get("source_results", []):
        actual.setdefault(result.get("dataset_key"), []).append(result.get("applied_params", {}))
    ok = all(
        any(all(params.get(key) == value for key, value in expected_params.items()) for params in actual.get(dataset_key, []))
        for dataset_key, expected_params in expected.items()
    )
    return ok, actual


def build_report(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Component LLM Validation Report",
        "",
        "- Path: numbered Langflow components with Gemini intent/pandas nodes",
        "",
    ]
    for result in results:
        lines.append(f"## {'PASS' if result['passed'] else 'FAIL'} {result['id']}")
        lines.append("")
        for check in result["checks"]:
            lines.append(f"- {'PASS' if check['passed'] else 'FAIL'} {check['name']}")
            lines.append(f"  - expected: `{check['expected']}`")
            lines.append(f"  - actual: `{check['actual']}`")
        lines.append("")
    return "\n".join(lines)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
