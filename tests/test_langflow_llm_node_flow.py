from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_component(path: str):
    component_path = ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    if hasattr(module, "_runtime_reference_date"):
        module._runtime_reference_date = lambda: "20260612"
    return module


def test_langflow_llm_node_style_flow_contract(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_prompt_builder = load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    dummy_retriever = load_component("langflow_components/data_analysis_flow/07_dummy_data_retriever.py")
    retrieval_adapter = load_component("langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py")
    data_store = load_component("langflow_components/data_analysis_flow/17_mongodb_data_store.py")
    data_loader = load_component("langflow_components/data_analysis_flow/05_mongodb_data_loader.py")
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    answer_prompt_builder = load_component("langflow_components/data_analysis_flow/18_answer_prompt_builder.py")
    answer_builder = load_component("langflow_components/data_analysis_flow/19_answer_response_builder.py")
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/20_answer_message_adapter.py")

    payload = request_loader.build_request_payload("오늘 전체 재공 수량 알려줘", "test-session")
    payload = data_loader.load_payload_from_mongodb(payload, enabled="false")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)

    intent_prompt = intent_prompt_builder.build_intent_prompt_payload(payload)["prompt"]
    assert "Langflow Gemini/LLM node" in intent_prompt
    assert "Required JSON schema" in intent_prompt

    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_wip_total",
        "datasets": ["wip_today"],
        "params_by_dataset": {"wip_today": {"DATE": "20260612"}},
        "filters": [],
        "retrieval_jobs": [
            {
                "dataset_key": "wip_today",
                "source_alias": "wip_total",
                "purpose": "current total WIP",
                "params": {"DATE": "20260612"},
                "filters": [],
                "required_columns": ["WORK_DT", "OPER_NAME", "WIP"],
            }
        ],
        "step_plan": [{"step_id": "sum_wip", "operation": "aggregate_sum", "source_alias": "wip_total"}],
        "depends_on_state": False,
        "reasoning_steps": ["Use current-day WIP and sum the WIP measure."],
    }
    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    assert payload["intent_plan"]["route"] == "single_retrieval"
    assert payload["retrieval_jobs"][0]["source_type"] == "oracle"

    retrieval_payload = dummy_retriever.retrieve_dummy_data(payload)
    payload = retrieval_adapter.adapt_retrieval_payload(payload, retrieval_payload)
    assert payload["runtime_sources"]["wip_total"]
    assert payload["source_results"][0]["preview_rows"]

    pandas_prompt = pandas_prompt_builder.build_pandas_prompt_payload(payload)["prompt"]
    assert "result_df" in pandas_prompt
    assert "aggregate_wip_total" in pandas_prompt

    pandas_llm_json = {
        "code": "\n".join(
            [
                "df = sources['wip_total']",
                "result_df = pd.DataFrame([{'SCOPE': plan.get('scope_label', 'ALL'), 'WIP': int(df['WIP'].sum())}])",
            ]
        ),
        "output_columns": ["SCOPE", "WIP"],
        "reasoning_steps": ["Sum WIP from the current WIP source."],
    }
    payload = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))
    assert payload["analysis"]["safety_passed"] is True
    assert payload["analysis"]["executed"] is True
    assert payload["analysis"]["row_count"] == 1
    assert payload["analysis"]["rows"][0]["WIP"] > 0

    payload = data_store.store_payload_in_mongodb(payload, enabled="false")
    answer_prompt = answer_prompt_builder.build_answer_prompt_payload(payload)["prompt"]
    assert "Answer in Korean" in answer_prompt
    assert "wip_today" in answer_prompt

    answer_llm_json = {"answer_message": "오늘 전체 재공 수량은 계산 결과 기준으로 확인되었습니다."}
    payload = answer_builder.build_answer_response_payload(payload, json.dumps(answer_llm_json, ensure_ascii=False))
    assert payload["answer_message"] == answer_llm_json["answer_message"]
    assert payload["data"]["row_count"] == 1
    assert payload["applied_scope"]["datasets"] == ["wip_today"]
    assert "runtime_sources" not in payload
    assert payload["state"]["current_data"]["source_dataset_keys"] == ["wip_today"]

    playground_message = answer_message_adapter.build_playground_message(payload)
    assert "### 답변" in playground_message
    assert "### 결과 테이블" in playground_message
    assert "### 의도 분석" in playground_message
    assert "### Pandas 처리" in playground_message
    assert "| SCOPE | WIP |" in playground_message
    assert "aggregate_wip_total" in playground_message
    assert "- 처리 경로:" in playground_message
    assert "- 의도 유형:" in playground_message
    assert "- 분석 단계:" in playground_message
    assert "- 조회 작업:" in playground_message
    assert "- 상태:" in playground_message
    assert "- 안전성 검사:" in playground_message
    assert "- Pandas 처리 근거:" in playground_message
    assert "step_plan:" not in playground_message
    assert "pandas_reasoning:" not in playground_message
    assert "```python" in playground_message


def test_intent_prompt_exposes_dataset_specific_date_formats(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_prompt_builder = load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py")

    payload = request_loader.build_request_payload("show today's production, wip, and target", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)

    prompt = intent_prompt_builder.build_intent_prompt_payload(payload)["prompt"]
    metadata_json = prompt.split("Metadata summary:\n", 1)[1].split("\n\nPrevious state summary:", 1)[0]
    summary = json.loads(metadata_json)

    production = summary["datasets"]["production_today"]
    target = summary["datasets"]["target"]
    assert production["required_param_mappings"] == {"DATE": ["WORK_DT"]}
    assert production["date_format"] == "YYYYMMDD"
    assert production["date_param_value_for_current_request"] == "20260612"
    assert target["date_format"] == "YYYY-MM-DD"
    assert target["date_param_value_for_current_request"] == "2026-06-12"
    assert "Do not output 2026-06-12 for that dataset" in prompt
    assert "Never copy target's YYYY-MM-DD format to production_today" in prompt


def test_request_date_overrides_stale_llm_date_params_and_filters(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_prompt_builder = load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘",
        "test-session",
        request_date="20260617",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    prompt = intent_prompt_builder.build_intent_prompt_payload(payload)["prompt"]
    metadata_json = prompt.split("Metadata summary:\n", 1)[1].split("\n\nPrevious state summary:", 1)[0]
    summary = json.loads(metadata_json)
    assert summary["datasets"]["production_today"]["date_param_value_for_current_request"] == "20260617"
    assert summary["datasets"]["target"]["date_param_value_for_current_request"] == "2026-06-17"

    stale_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "datasets": ["production_today", "wip_today", "target"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "prod",
                "params": {"DATE": "20260612"},
                "filters": [{"field": "DATE", "op": "eq", "value": "20260612"}],
            },
            {
                "dataset_key": "wip_today",
                "source_alias": "wip",
                "params": {"DATE": "20260612"},
                "filters": [{"field": "DATE", "op": "eq", "value": "20260612"}],
            },
            {
                "dataset_key": "target",
                "source_alias": "target",
                "params": {"DATE": "2026-06-12"},
                "filters": [{"field": "DATE", "op": "eq", "value": "2026-06-12"}],
            },
        ],
        "step_plan": [{"step_id": "join", "operation": "production_wip_target_rate"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(stale_llm_json, ensure_ascii=False))
    jobs = {job["dataset_key"]: job for job in payload["retrieval_jobs"]}

    assert jobs["production_today"]["params"]["DATE"] == "20260617"
    assert jobs["wip_today"]["params"]["DATE"] == "20260617"
    assert jobs["target"]["params"]["DATE"] == "2026-06-17"
    assert _filter_values(jobs["production_today"], "DATE") == ["20260617"]
    assert _filter_values(jobs["wip_today"], "DATE") == ["20260617"]
    assert _filter_values(jobs["target"], "DATE") == ["2026-06-17"]


def test_intent_normalizer_builds_recipe_jobs_when_llm_omits_jobs(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "datasets": ["production_today", "wip_today", "target"],
        "params_by_dataset": {"production_today": {"DATE": "20260612"}, "wip_today": {"DATE": "20260612"}},
        "reasoning_steps": ["Need production, WIP, and target values for DA."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["route"] == "multi_retrieval"
    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert [job["source_alias"] for job in payload["retrieval_jobs"]] == [
        "production_data",
        "wip_data",
        "target_data",
    ]
    assert [job["source_type"] for job in payload["retrieval_jobs"]] == ["oracle", "oracle", "goodocs"]
    assert payload["intent_plan"]["step_plan"][0]["recipe_key"] == "production_wip_target_rate"
    assert payload["intent_plan"]["step_plan"][0]["group_by"] == [
        "TECH",
        "DEN",
        "MODE",
        "PKG_TYPE1",
        "PKG_TYPE2",
        "LEAD",
        "MCP_NO",
    ]
    assert any("분석 recipe 'production_wip_target_rate'" in item for item in payload["info"])
    assert not any("분석 recipe 'production_wip_target_rate'" in item for item in payload["warnings"])
    assert not any("fallback jobs" in item for item in payload["warnings"])
    assert not any("fallback step_plan" in item for item in payload["warnings"])


def test_intent_normalizer_builds_recipe_jobs_when_llm_omits_specialized_datasets(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "reasoning_steps": ["Need production, WIP, and target values."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert payload["intent_plan"]["analysis_kind"] == "production_wip_target_rate"
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["production_today", "wip_today", "target"]
    assert payload["intent_plan"]["step_plan"][0]["recipe_key"] == "production_wip_target_rate"
    assert payload["intent_plan"]["route"] == "multi_retrieval"
    assert any("분석 recipe 'production_wip_target_rate'" in item for item in payload["info"])
    assert not any("분석 recipe 'production_wip_target_rate'" in item for item in payload["warnings"])


def test_intent_normalizer_does_not_build_specialized_jobs_without_recipe_metadata(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    payload["metadata"]["domain_items"]["analysis_recipes"] = {}
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "reasoning_steps": ["Need production, WIP, and target values."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["retrieval_jobs"] == []
    assert payload["intent_plan"]["step_plan"] == []
    assert any("datasets도 없어 조회 작업을 보완할 수 없습니다" in item for item in payload["warnings"])


def test_intent_normalizer_recipe_grain_policy_uses_question_scope(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 전체 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert payload["intent_plan"]["product_grain"] == []
    assert payload["intent_plan"]["step_plan"][0]["group_by"] == []


def test_intent_normalizer_adds_result_scope_columns_from_process_group(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 WB공정에서 생산량 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_sum",
        "datasets": ["production_today"],
        "retrieval_jobs": [{"dataset_key": "production_today", "source_alias": "production_data"}],
        "step_plan": [
            {
                "step_id": "sum_production",
                "operation": "aggregate_sum",
                "source_alias": "production_data",
                "metric": "PRODUCTION",
                "output_columns": ["PRODUCTION"],
            }
        ],
        "analysis_output_columns": ["PRODUCTION"],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["result_scope_columns"] == [{"column": "OPER_GROUP", "value": "WB", "source_field": "OPER_NAME"}]
    assert any(item.get("field") == "OPER_NAME" for item in payload["retrieval_jobs"][0]["filters"])


def test_intent_normalizer_does_not_add_raw_process_list_scope_column(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["wip_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "wip_today",
                "source_alias": "wip_data",
                "filters": [
                    {
                        "field": "OPER_NAME",
                        "op": "in",
                        "values": ["D/A1", "D/A2", "W/B1", "W/B2"],
                    }
                ],
            }
        ],
        "step_plan": [
            {
                "step_id": "rank_wip",
                "operation": "rank_top_n",
                "source_alias": "wip_data",
                "metric": "WIP",
                "top_n": 3,
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    scope_columns = payload["intent_plan"].get("result_scope_columns", [])
    assert all(item.get("column") != "OPER_NAME" for item in scope_columns)


def test_intent_normalizer_detail_request_overrides_recipe_grouping(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 DA공정에서 재공, 생산량과 목표값 세부 데이터를 집계하지 말고 보여줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert payload["intent_plan"]["detail_rows_requested"] is True
    assert payload["intent_plan"]["analysis_kind"] == "detail_rows"
    assert payload["intent_plan"]["original_analysis_kind"] == "production_wip_target_rate"
    assert payload["intent_plan"]["product_grain"] == []
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["production_today", "wip_today", "target"]
    assert payload["intent_plan"]["step_plan"] == [
        {
            "step_id": "detail_rows",
            "operation": "detail_rows",
            "source_alias": "production_data",
            "source_aliases": ["production_data", "wip_data", "target_data"],
        }
    ]
    assert "group_by" not in payload["intent_plan"]["step_plan"][0]
    assert "OPER_NAME" in payload["retrieval_jobs"][0]["required_columns"]
    assert "PRODUCTION" in payload["retrieval_jobs"][0]["required_columns"]


def test_intent_normalizer_recipe_defaults_populate_plan(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 INPUT계획대비 D/A공정에서 생산량이 저조한 제품을 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "low_output_vs_target",
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "low_output_vs_target"
    assert payload["intent_plan"]["production_column"] == "PRODUCTION"
    assert payload["intent_plan"]["target_column"] == "INPUT_PLAN"
    assert payload["intent_plan"]["threshold"] == 1.0


def test_intent_normalizer_recipe_promotes_generic_lot_quantity_plan(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "현재 DA공정에서 재공 lot이 몇개인지, wafer가 몇개인지, die수량은 몇개인지 알려줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["lot_status"],
        "retrieval_jobs": [
            {
                "dataset_key": "lot_status",
                "source_alias": "lot_data",
                "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1"]}],
                "required_columns": ["LOT_ID", "OPER_NAME", "WF_QTY", "SUB_PROD_QTY"],
            }
        ],
        "step_plan": [{"step_id": "aggregate_lot_quantities", "operation": "aggregate", "source_alias": "lot_data"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "lot_quantity_summary"
    assert payload["intent_plan"]["analysis_kind"] == "lot_quantity_summary"
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["lot_status"]
    assert {"LOT_ID", "WF_QTY", "SUB_PROD_QTY"}.issubset(set(payload["retrieval_jobs"][0]["required_columns"]))


def test_intent_normalizer_recipe_aligns_history_dataset_for_date_split(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("어제 생산량과 오늘 생산계획의 차이수량을 제품별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "date_split_production_plan_gap",
        "datasets": ["production_today", "target"],
        "params_by_dataset": {
            "production_today": {"DATE": "20260611"},
            "target": {"DATE": "20260612"},
        },
        "retrieval_jobs": [
            {"dataset_key": "production_today", "source_alias": "production_data", "params": {"DATE": "20260611"}},
            {"dataset_key": "target", "source_alias": "target_data", "params": {"DATE": "20260612"}},
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "date_split_production_plan_gap"
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["production", "target"]
    assert payload["intent_plan"]["datasets"] == ["production", "target"]
    assert "production_today" not in payload["intent_plan"]["params_by_dataset"]
    assert payload["intent_plan"]["params_by_dataset"]["production"]["DATE"] == "20260611"
    assert any("dataset family" in item and "정렬" in item for item in payload["info"])
    assert not any("dataset family" in item and "정렬" in item for item in payload["warnings"])


def test_intent_normalizer_builds_generic_rank_fallback_step(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 재공 상위 3개 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["wip_today"],
        "top_n": 3,
        "reasoning_steps": ["Rank current WIP."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    product_keys = payload["metadata"]["domain_items"]["product_key_columns"]

    assert [job["source_alias"] for job in payload["retrieval_jobs"]] == ["wip_today"]
    assert payload["retrieval_jobs"][0]["params"]["DATE"] == "20260612"
    assert payload["retrieval_jobs"][0]["primary_quantity_column"] == "WIP"
    assert payload["intent_plan"]["step_plan"] == [
        {
            "step_id": "rank_items",
            "operation": "rank_top_n",
            "source_alias": "wip_today",
            "metric": "WIP",
            "top_n": 3,
            "rank_order": "desc",
            "group_by": product_keys,
        }
    ]
    assert any("step_plan이 없어" in item for item in payload["info"])
    assert not any("step_plan이 없어" in item for item in payload["warnings"])


def test_intent_normalizer_absorbs_loose_rank_fields_before_fallback(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("현재 DA공정에서 재공이 가장 많은 제품 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    product_keys = payload["metadata"]["domain_items"]["product_key_columns"]
    output_columns = [*product_keys, "WIP"]
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["wip_today"],
        "params_by_dataset": {"wip_today": {"DATE": "20260612"}},
        "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]}],
        "rank": {
            "quantity_column": "WIP",
            "rank_column": "WIP",
            "sort_order": "desc",
            "top_n": 1,
        },
        "group_by": product_keys,
        "output_columns": output_columns,
        "reasoning_steps": ["Rank DA WIP by product and return the largest product."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    step = plan["step_plan"][0]

    assert plan["metric"] == "WIP"
    assert plan["top_n"] == 1
    assert plan["rank_order"] == "desc"
    assert plan["product_grain"] == product_keys
    assert plan["analysis_output_columns"] == output_columns
    assert step["metric"] == "WIP"
    assert step["top_n"] == 1
    assert step["rank_order"] == "desc"
    assert step["group_by"] == product_keys
    assert step["output_columns"] == output_columns
    assert _filter_values(payload["retrieval_jobs"][0], "OPER_NAME") == ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]
    assert any("retrieval_jobs가 없어" in item for item in payload["info"])
    assert any("step_plan이 없어" in item for item in payload["info"])
    assert not any("retrieval_jobs가 없어" in item for item in payload["warnings"])


def test_intent_prompt_tells_llm_to_use_group_label_not_raw_rank_field(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_prompt_builder = load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py")

    payload = request_loader.build_request_payload(
        "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)

    prompt = intent_prompt_builder.build_intent_prompt_payload(payload)["prompt"]

    assert "rank_group_output_column" in prompt
    assert '"grain": "optional semantic grain' in prompt
    assert "Separate filter scope from grouping grain" in prompt
    assert "Choose group_by from the entity being ranked or aggregated" in prompt
    assert "rank_groups[].field" in prompt
    assert "Do not include that raw field in final output_columns" in prompt
    assert "use OPER_GROUP in final output_columns rather than OPER_NAME" in prompt


def test_intent_normalizer_augments_existing_jobs_from_metadata(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "datasets": ["production_today", "wip_today", "target"],
        "retrieval_jobs": [
            {"dataset_key": "production_today", "source_alias": "prod", "filters": [], "params": {}, "source_config": {}},
            {"dataset_key": "wip_today", "source_alias": "wip", "filters": [], "params": {}},
            {"dataset_key": "target", "source_alias": "target", "filters": [], "params": {}},
        ],
        "step_plan": [{"step_id": "join", "operation": "join"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    jobs = {job["dataset_key"]: job for job in payload["retrieval_jobs"]}

    assert jobs["production_today"]["params"]["DATE"] == "20260612"
    assert jobs["wip_today"]["params"]["DATE"] == "20260612"
    assert jobs["production_today"]["source_config"]["db_key"] == "PNT_RPT"
    assert "query_template" in jobs["production_today"]["source_config"]
    assert jobs["target"]["source_config"]["doc_id"] == "GOODOCS_TARGET2_DOCUMENT_ID"
    assert jobs["target"]["date_format"] == "YYYY-MM-DD"
    assert _filter_values(jobs["production_today"], "DATE") == ["20260612"]
    assert _filter_values(jobs["wip_today"], "DATE") == ["20260612"]
    assert _filter_values(jobs["target"], "DATE") == ["2026-06-12"]
    assert _filter_values(jobs["production_today"], "OPER_NAME") == ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]
    assert {"TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"}.issubset(
        set(jobs["production_today"]["required_columns"])
    )
    assert {"TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"}.issubset(
        set(jobs["target"]["required_columns"])
    )
    assert any("params/filters를 보완" in item for item in payload["info"])
    assert not any("params/filters를 보완" in item for item in payload["warnings"])


def test_intent_normalizer_uses_product_terms_for_existing_jobs(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 LPDDR5 W/B 공정 재공과 생산량을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["production_today", "wip_today"],
        "retrieval_jobs": [
            {"dataset_key": "production_today", "source_alias": "prod", "filters": [], "params": {}},
            {"dataset_key": "wip_today", "source_alias": "wip", "filters": [], "params": {}},
        ],
        "step_plan": [{"step_id": "join", "operation": "join"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = payload["retrieval_jobs"][0]

    assert _filter_values(job, "MODE") == ["LPDDR5"]
    assert _filter_values(job, "OPER_NAME") == ["W/B1", "W/B2", "W/B3", "W/B4", "W/B5", "W/B6"]


def test_intent_normalizer_replaces_wrong_product_alias_filter_with_metadata_condition(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("HBM 제품의 장비 모델별 현황을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status"],
        "retrieval_jobs": [
            {
                "dataset_key": "equipment_status",
                "source_alias": "equipment",
                "filters": [{"field": "TECH", "op": "eq", "value": "HBM"}],
                "params": {},
            }
        ],
        "step_plan": [{"step_id": "by_model", "operation": "group_by"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = payload["retrieval_jobs"][0]

    assert _filter_values(job, "PKG_TYPE1") == ["HBM"]
    assert _filter_values(job, "TECH") == []


def test_intent_normalizer_aligns_followup_equipment_to_state_products(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("그 제품에 물려 있는 장비를 보여줘", "test-session")
    payload["state"] = {
        "current_data": {
            "rows": [
                {"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "MCP_NO": "EMPTY"}
            ]
        }
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "followup_transform",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status"],
        "retrieval_jobs": [
            {"dataset_key": "equipment_status", "source_alias": "equipment", "filters": [], "params": {}}
        ],
        "step_plan": [{"step_id": "equipment", "operation": "detail_rows"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["analysis_kind"] == "equipment_for_previous_products"
    assert plan["state_product_keys"] == [
        {"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "MCP_NO": "EMPTY"}
    ]
    assert any(item.get("field") == "PRODUCT_GRAIN" for item in payload["retrieval_jobs"][0]["filters"])


def test_intent_normalizer_uses_state_product_key_summary_without_full_rows(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("그 제품이 물려 있는 설비를 보여줘", "test-session")
    payload["state"] = {
        "current_data": {
            "columns": ["MODE", "WIP"],
            "rows": [{"MODE": "LPDDR5", "WIP": 10}],
            "row_count": 200,
            "data_is_preview": True,
            "product_key_columns": ["MODE"],
            "product_key_values": [{"MODE": "LPDDR5"}, {"MODE": "HBM"}],
            "product_key_count": 2,
        }
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "followup_transform",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status"],
        "retrieval_jobs": [
            {"dataset_key": "equipment_status", "source_alias": "equipment", "filters": [], "params": {}}
        ],
        "step_plan": [{"step_id": "equipment", "operation": "detail_rows"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["analysis_kind"] == "equipment_for_previous_products"
    assert plan["state_product_keys"] == [{"MODE": "LPDDR5"}, {"MODE": "HBM"}]
    assert any(item.get("field") == "PRODUCT_GRAIN" for item in payload["retrieval_jobs"][0]["filters"])


def test_intent_normalizer_prunes_lot_status_for_followup_equipment_count(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("이 제품의 이 공정에 할당된 장비 대수를 알려줘", "test-session")
    payload["state"] = {
        "current_data": {
            "columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "WIP"],
            "rows": [{"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "EMPTY", "WIP": 10}],
            "product_key_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
            "product_key_values": [{"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "EMPTY"}],
            "product_key_count": 1,
            "data_ref": {"store": "mongodb", "ref_id": "previous-result", "collection_name": "agent_v3_result_store"},
        }
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "followup_transform",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status", "lot_status"],
        "retrieval_jobs": [
            {"dataset_key": "equipment_status", "source_alias": "equipment", "filters": [], "params": {}},
            {"dataset_key": "lot_status", "source_alias": "lot_status", "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1"]}], "params": {}},
        ],
        "step_plan": [{"step_id": "equipment_count", "operation": "count", "source_alias": "equipment"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["analysis_kind"] == "equipment_count_for_previous_products"
    assert plan["datasets"] == ["equipment_status"]
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["equipment_status"]
    assert payload["retrieval_jobs"][0]["filters"] == [{"field": "PRODUCT_GRAIN", "op": "from_state"}]
    assert plan["step_plan"][0]["operation"] == "equipment_count_for_previous_products"
    assert plan["analysis_output_columns"] == [
        "TECH",
        "DEN",
        "MODE",
        "PKG_TYPE1",
        "PKG_TYPE2",
        "LEAD",
        "MCP_NO",
        "EQP_COUNT",
    ]
    assert plan["previous_result_restore_mode"] == "summary"


def test_retrieval_adapter_adds_standard_columns_from_physical_catalog_aliases(monkeypatch: Any) -> None:
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    retrieval_adapter = load_component("langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py")

    payload = load_seed_metadata_payload(metadata_loader, {"state": {}}, monkeypatch)
    retrieval_payload = {
        "source_results": [
            {
                "dataset_key": "equipment_status",
                "source_alias": "equipment",
                "source_type": "oracle",
                "data": [{"EQPID": "EQP1", "PKG1": "UFBGA", "PKG2": "MOBILE", "MCPSALENO": "EMPTY", "MODE": "LPDDR5"}],
            }
        ]
    }

    adapted = retrieval_adapter.adapt_retrieval_payload(payload, retrieval_payload)
    row = adapted["runtime_sources"]["equipment"][0]

    assert row["PKG_TYPE1"] == "UFBGA"
    assert row["PKG_TYPE2"] == "MOBILE"
    assert row["MCP_NO"] == "EMPTY"


def test_intent_normalizer_marks_full_previous_result_restore_for_previous_result_row_analysis(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("이전 결과 전체 데이터를 다시 보여줘", "test-session")
    payload["state"] = {
        "current_data": {
            "columns": ["MODE", "WIP"],
            "rows": [{"MODE": "LPDDR5", "WIP": 10}],
            "row_count": 200,
            "data_ref": {"store": "mongodb", "ref_id": "previous-result", "collection_name": "agent_v3_result_store"},
            "data_is_preview": True,
        }
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "followup_transform",
        "analysis_kind": "detail_rows",
        "datasets": [],
        "retrieval_jobs": [],
        "depends_on_state": True,
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["requires_full_previous_result_restore"] is True
    assert plan["previous_result_restore_mode"] == "full"
    assert plan["previous_result_restore_reason"] == "followup_analysis_needs_previous_rows"
    assert any("MongoDB에서 전체 row를 복원" in item for item in payload["info"])


def test_intent_normalizer_reuses_previous_source_rows_for_this_time_breakdown(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("이때 상세 device별로 알려줘", "test-session")
    payload["state"] = {
        "current_data": {
            "columns": ["MODE", "PRODUCTION"],
            "rows": [{"MODE": "LPDDR5", "PRODUCTION": 100}],
            "row_count": 2,
            "data_ref": {"store": "mongodb", "ref_id": "previous-result", "collection_name": "agent_v3_result_store"},
            "data_is_preview": True,
            "product_key_columns": ["MODE"],
            "source_dataset_keys": ["production_today"],
        },
        "followup_source_results": [
            {
                "source_alias": "production_data",
                "dataset_key": "production_today",
                "source_type": "oracle",
                "data_ref": {"store": "mongodb", "ref_id": "source-ref", "collection_name": "agent_v3_result_store"},
                "row_count": 100,
                "columns": ["MODE", "DEVICE", "PRODUCTION"],
            }
        ],
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "detail_rows",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "params": {"DATE": "20260612"},
            }
        ],
        "step_plan": [{"step_id": "detail", "operation": "detail_rows", "source_alias": "production_data"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["intent_type"] == "followup_transform"
    assert plan["analysis_kind"] == "aggregate_previous_source"
    assert plan["reuse_previous_runtime_sources"] is True
    assert plan["requires_full_previous_result_restore"] is True
    assert plan["previous_result_restore_mode"] == "full"
    assert plan["previous_result_restore_reason"] == "followup_reuses_previous_source_rows"
    assert plan["retrieval_jobs"] == []
    assert payload["retrieval_jobs"] == []
    assert plan["datasets"] == ["production_today"]
    assert plan["metric"] == "PRODUCTION"
    assert plan["product_grain"] == ["MODE", "DEVICE"]


def test_intent_normalizer_maps_logical_required_columns_to_dataset_columns(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("현재 작업대기 Lot 수량을 공정별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "lot_count_by_process",
        "datasets": ["lot_status"],
        "filters": [{"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]}],
        "retrieval_jobs": [
            {
                "dataset_key": "lot_status",
                "source_alias": "lot_status_data",
                "required_columns": ["OPER_NAME", "LOT_ID", "LOT_STAT_CD"],
                "filters": [{"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]}],
            }
        ],
        "step_plan": [
            {
                "step_id": "aggregate_waiting_lots",
                "operation": "group_by_count_unique",
                "source_alias": "lot_status_data",
                "group_by_columns": ["OPER_NAME"],
                "count_column": "LOT_ID",
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = payload["retrieval_jobs"][0]

    assert "OPER_SHORT_DESC" in job["required_columns"]
    assert "LOT_ID" in job["required_columns"]
    assert "WF_QTY" in job["required_columns"]
    assert payload["intent_plan"]["step_plan"][0]["group_by_columns"] == ["OPER_SHORT_DESC"]


def test_intent_normalizer_repairs_lot_count_kind_from_generic_aggregate(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("현재 작업대기 Lot 수량을 공정별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_wip_total",
        "datasets": ["lot_status"],
        "filters": [{"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]}],
        "metric": "LOT_ID",
        "analysis_output_columns": ["OPER_NAME", "LOT_COUNT"],
        "retrieval_jobs": [
            {
                "dataset_key": "lot_status",
                "source_alias": "lot_data",
                "filters": [{"field": "LOT_STAT_CD", "op": "in", "values": ["WAITING"]}],
                "required_columns": ["OPER_NAME", "LOT_ID"],
            }
        ],
        "step_plan": [
            {
                "step_id": "aggregate_waiting_lots",
                "operation": "aggregate",
                "source_alias": "lot_data",
                "metric": "LOT_ID",
                "aggregation": "nunique",
                "group_by": ["OPER_NAME"],
                "output_columns": ["OPER_NAME", "LOT_COUNT"],
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["analysis_kind"] == "lot_count_by_process"
    assert payload["intent_plan"]["step_plan"][0]["operation"] == "lot_count_by_process"
    assert payload["intent_plan"]["step_plan"][0]["group_by_columns"] == ["OPER_SHORT_DESC"]
    assert payload["retrieval_jobs"][0]["dataset_key"] == "lot_status"
    assert "OPER_SHORT_DESC" in payload["retrieval_jobs"][0]["required_columns"]
    assert any("LOT_ID unique count" in item for item in payload["info"])


def test_intent_normalizer_preserves_top_wip_process_then_lot_metrics_plan(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")

    payload = request_loader.build_request_payload(
        "오늘 DA공정에서 재공이 많은 세부공정 top 3을 찾고, 해당 공정들의 hold LOT 수와 평균 in tat를 같이 보여줘.",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "lot_count_by_process",
        "datasets": ["lot_status"],
        "filters": [
            {"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]},
            {"field": "LOT_HOLD_STAT_CD", "op": "in", "values": ["HOLD", "OnHold"]},
        ],
        "retrieval_jobs": [
            {
                "dataset_key": "lot_status",
                "source_alias": "lot_status_data",
                "purpose": "Retrieve lot status data for DA processes.",
                "filters": [
                    {"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]},
                    {"field": "LOT_HOLD_STAT_CD", "op": "in", "values": ["HOLD", "OnHold"]},
                ],
            }
        ],
        "step_plan": [{"step_id": "count_lots_by_process", "operation": "lot_count_by_process", "source_alias": "lot_status_data"}],
        "reasoning_steps": [
            "Retrieve today's WIP data for DA processes and rank them by WIP to find the top 3.",
            "Retrieve lot status data for DA processes.",
            "For the top 3 processes, calculate the number of hold lots and the average in-TAT.",
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    jobs = {job["dataset_key"]: job for job in payload["retrieval_jobs"]}

    assert plan["analysis_kind"] == "top_wip_process_hold_lot_in_tat"
    assert plan["matched_analysis_recipe"] == "top_wip_process_hold_lot_in_tat"
    assert plan["route"] == "multi_retrieval"
    assert plan["datasets"] == ["wip_today", "lot_status"]
    assert plan["top_n"] == 3
    assert plan["recipe_grain_policy"] == "recipe_step_grain"
    assert plan["analysis_output_columns"] == ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]
    assert [step["operation"] for step in plan["step_plan"]] == ["rank_top_n", "hold_lot_in_tat_by_process", "left_join"]
    assert plan["step_plan"][0]["top_n"] == 3
    assert jobs["wip_today"]["source_alias"] == "wip_data"
    assert jobs["lot_status"]["source_alias"] == "lot_status_data"
    assert "WIP" in jobs["wip_today"]["required_columns"]
    assert "IN_TAT" in jobs["lot_status"]["required_columns"]
    assert "LOT_HOLD_STAT_CD" not in {item["field"] for item in jobs["lot_status"]["filters"]}
    assert any("분석 recipe 'top_wip_process_hold_lot_in_tat'" in item for item in payload["info"])

    prompt = pandas_prompt_builder.build_pandas_prompt_payload({**payload, "runtime_sources": {"wip_data": [], "lot_status_data": []}})["prompt"]
    assert "implement every step in order" in prompt
    assert "HOLD_LOT_COUNT" in prompt
    assert "AVG_IN_TAT" in prompt


def test_intent_normalizer_does_not_hardcode_top_wip_process_lot_recipe(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 DA공정에서 재공이 많은 세부공정 top 3을 찾고, 해당 공정들의 hold LOT 수와 평균 in tat를 같이 보여줘.",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    payload["metadata"]["domain_items"]["analysis_recipes"].pop("top_wip_process_hold_lot_in_tat", None)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "lot_count_by_process",
        "datasets": ["lot_status"],
        "retrieval_jobs": [{"dataset_key": "lot_status", "source_alias": "lot_status_data"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["analysis_kind"] == "lot_count_by_process"
    assert "matched_analysis_recipe" not in payload["intent_plan"]
    assert [job["dataset_key"] for job in payload["retrieval_jobs"]] == ["lot_status"]


def test_intent_normalizer_does_not_apply_wip_lot_recipe_to_production_equipment_question(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 DA공정에서 생산량 상위 5개 제품과 각 제품별 할당 장비 대수를 보여줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_step_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["production_today", "equipment_status"],
        "retrieval_jobs": [
            {"dataset_key": "production_today", "source_alias": "production_data"},
            {"dataset_key": "equipment_status", "source_alias": "equipment_data"},
        ],
        "step_plan": [
            {"step_id": "rank_top_production_products", "operation": "rank_top_n", "source_alias": "production_data", "metric": "PRODUCTION", "top_n": 5},
            {"step_id": "get_equipment_count", "operation": "aggregate_join", "source_alias": "equipment_data", "metric": "EQPID"},
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    jobs = {job["dataset_key"]: job for job in payload["retrieval_jobs"]}

    assert plan["analysis_kind"] == "top_production_products_equipment_count"
    assert plan["matched_analysis_recipe"] == "top_production_products_equipment_count"
    assert plan["datasets"] == ["production_today", "equipment_status"]
    assert [step["operation"] for step in plan["step_plan"]] == ["rank_top_n", "equipment_count_by_product", "left_join"]
    assert plan["step_plan"][0]["metric"] == "PRODUCTION"
    assert plan["step_plan"][0]["top_n"] == 5
    assert plan["step_plan"][1]["count_column"] == "EQPID"
    assert jobs["production_today"]["source_alias"] == "production_data"
    assert jobs["equipment_status"]["source_alias"] == "equipment_data"
    assert "EQPID" in jobs["equipment_status"]["required_columns"]


def test_intent_normalizer_applies_top_wip_product_oldest_lot_recipe(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "지금 WB에서 재공이 가장 많은 제품 기준으로 LOT의 IN TAT를 보고, IN TAT가 가장 오래된 LOT을 찾아줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_step_analysis",
        "analysis_kind": "none",
        "datasets": ["wip_today", "lot_status"],
        "retrieval_jobs": [
            {"dataset_key": "wip_today", "source_alias": "wip_data"},
            {"dataset_key": "lot_status", "source_alias": "lot_data"},
        ],
        "step_plan": [
            {"step_id": "get_wb_wip", "operation": "aggregate_total", "source_alias": "wip_data", "metric": "WIP"},
            {"step_id": "get_top_in_tat_lot", "operation": "rank_top_n", "source_alias": "lot_data", "metric": "IN_TAT", "top_n": 1},
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    jobs = {job["dataset_key"]: job for job in payload["retrieval_jobs"]}

    assert plan["analysis_kind"] == "top_wip_product_oldest_lot"
    assert plan["matched_analysis_recipe"] == "top_wip_product_oldest_lot"
    assert plan["route"] == "multi_retrieval"
    assert plan["datasets"] == ["wip_today", "lot_status"]
    assert plan["analysis_output_columns"] == ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "WIP", "LOT_ID", "IN_TAT"]
    assert [step["step_id"] for step in plan["step_plan"]] == [
        "rank_top_wip_product",
        "find_oldest_lot_for_top_product",
        "join_top_product_and_oldest_lot",
    ]
    assert plan["step_plan"][0]["metric"] == "WIP"
    assert plan["step_plan"][1]["filter_from_step"] == "rank_top_wip_product"
    assert plan["step_plan"][1]["metric"] == "IN_TAT"
    assert plan["step_plan"][1]["rank_order"] == "desc"
    assert jobs["wip_today"]["source_alias"] == "wip_data"
    assert jobs["lot_status"]["source_alias"] == "lot_data"
    assert "WIP" in jobs["wip_today"]["required_columns"]
    assert "IN_TAT" in jobs["lot_status"]["required_columns"]


def test_intent_normalizer_adds_eqpid_primary_quantity_to_equipment_columns(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 HBM 장비 보유 현황을 EQP_MODEL별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "equipment_by_model",
        "datasets": ["equipment_status"],
        "retrieval_jobs": [
            {
                "dataset_key": "equipment_status",
                "source_alias": "equipment_data",
                "required_columns": ["EQP_MODEL"],
                "filters": [{"field": "PKG_TYPE1", "op": "eq", "value": "HBM"}],
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["retrieval_jobs"][0]["required_columns"] == ["EQP_MODEL", "EQPID"]


def test_pandas_executor_normalizes_llm_result_column_names() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "rank_wip_then_join_production",
            "product_grain": ["MODE"],
        },
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "result_df = pd.DataFrame([",
                "    {'RANK_GROUP': 'DA', 'MODE': 'LPDDR5', 'WIP_sum': 10, 'rank': 1, 'PRODUCTION_sum': 7}",
                "])",
            ]
        ),
        "output_columns": ["RANK_GROUP", "MODE", "WIP_sum", "rank", "PRODUCTION_sum"],
        "reasoning_steps": ["Return a ranked aggregate row."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["RANK_GROUP", "WIP_RANK", "MODE", "WIP", "PRODUCTION"]
    assert result["analysis"]["rows"][0]["WIP_RANK"] == 1
    assert result["analysis"]["rows"][0]["PRODUCTION"] == 7


def test_pandas_prompt_tells_llm_not_to_output_rank_group_source_field() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    payload = {
        "request": {"question": "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘"},
        "intent_plan": {
            "analysis_kind": "rank_wip_then_join_production",
            "product_grain": ["MODE"],
            "rank_group_output_column": "OPER_GROUP",
            "retrieval_jobs": [
                {
                    "dataset_key": "wip_today",
                    "source_alias": "wip_data",
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2", "W/B1", "W/B2"]}],
                },
                {
                    "dataset_key": "production_today",
                    "source_alias": "production_data",
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2", "W/B1", "W/B2"]}],
                },
            ],
            "step_plan": [
                {
                    "step_id": "rank_wip",
                    "operation": "rank_top_n_per_filter_group",
                    "source_alias": "wip_data",
                    "metric": "WIP",
                    "top_n": 3,
                    "rank_order": "desc",
                    "rank_groups": [
                        {"label": "DA", "field": "OPER_NAME", "values": ["D/A1", "D/A2"]},
                        {"label": "WB", "field": "OPER_NAME", "values": ["W/B1", "W/B2"]},
                    ],
                    "group_by": ["RANK_GROUP", "MODE"],
                    "output_columns": ["RANK_GROUP", "WIP_RANK", "MODE", "WIP"],
                },
                {
                    "step_id": "sum_production",
                    "operation": "aggregate_for_previous_keys",
                    "source_alias": "production_data",
                    "metric": "PRODUCTION",
                    "filter_from_step": "rank_wip",
                    "rank_groups": [
                        {"label": "DA", "field": "OPER_NAME", "values": ["D/A1", "D/A2"]},
                        {"label": "WB", "field": "OPER_NAME", "values": ["W/B1", "W/B2"]},
                    ],
                    "group_by": ["RANK_GROUP", "MODE"],
                    "output_columns": ["RANK_GROUP", "MODE", "PRODUCTION"],
                },
                {
                    "step_id": "join_result",
                    "operation": "left_join",
                    "left_step": "rank_wip",
                    "right_step": "sum_production",
                    "join_keys": ["RANK_GROUP", "MODE"],
                    "output_columns": ["OPER_GROUP", "WIP_RANK", "MODE", "WIP", "PRODUCTION"],
                },
            ],
            "analysis_output_columns": ["OPER_GROUP", "WIP_RANK", "MODE", "WIP", "PRODUCTION"],
        },
        "runtime_sources": {"wip_data": [], "production_data": []},
    }

    prompt = pandas_prompt_builder.build_pandas_prompt_payload(payload)["prompt"]

    assert "Do not include raw source/filter condition columns in result_df" in prompt
    assert "Maintain a local dict named step_outputs" in prompt
    assert "aggregate the rank metric at the intended grain before sorting" in prompt
    assert "rank separately within each group label" in prompt
    assert "restrict the later source to the ranked entity keys from step_outputs" in prompt
    assert "Use plan.rank_group_output_column as the final group label column" in prompt
    assert "OPER_GROUP" in prompt


def test_pandas_prompt_for_unknown_multi_step_plan_does_not_request_empty_result() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    payload = {
        "request": {"question": "지금 WB에서 재공이 가장 많은 제품 기준으로 LOT의 IN TAT를 보고, IN TAT가 가장 오래된 LOT을 찾아줘"},
        "intent_plan": {
            "analysis_kind": "custom_wip_lot_sequence",
            "product_grain": ["MODE"],
            "retrieval_jobs": [
                {"dataset_key": "wip_today", "source_alias": "wip_data"},
                {"dataset_key": "lot_status", "source_alias": "lot_data"},
            ],
            "step_plan": [
                {"operation": "rank_top_n", "source_alias": "wip_data", "metric": "WIP", "group_by": ["MODE"], "top_n": 1},
                {"operation": "rank_top_n", "source_alias": "lot_data", "metric": "IN_TAT", "rank_order": "desc", "top_n": 1},
            ],
        },
        "runtime_sources": {"wip_data": [], "lot_data": []},
    }

    prompt = pandas_prompt_builder.build_pandas_prompt_payload(payload)["prompt"]

    assert "sequential multi-source analysis" in prompt
    assert "IN_TAT" in prompt
    assert "Return an empty DataFrame with no rows" not in prompt


def test_pandas_executor_falls_back_when_llm_returns_empty_contract_for_wip_lot_sequence() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_grain = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    payload = {
        "intent_plan": {
            "analysis_kind": "custom_wip_lot_sequence",
            "product_grain": product_grain,
            "retrieval_jobs": [
                {"dataset_key": "wip_today", "source_alias": "wip_data"},
                {"dataset_key": "lot_status", "source_alias": "lot_data"},
            ],
            "step_plan": [
                {"operation": "rank_top_n", "source_alias": "wip_data", "metric": "WIP", "group_by": product_grain, "top_n": 1},
                {
                    "operation": "rank_top_n",
                    "source_alias": "lot_data",
                    "metric": "IN_TAT",
                    "rank_order": "desc",
                    "top_n": 1,
                    "filter_from_step": "top_wip_product",
                },
            ],
        },
        "state": {},
        "runtime_sources": {
            "wip_data": [
                {"TECH": "WB", "DEN": "512G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "AUTO", "LEAD": "LF", "MCP_NO": "A", "WIP": 40},
                {"TECH": "WB", "DEN": "1024G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "SERVER", "LEAD": "LF", "MCP_NO": "B", "WIP": 90},
            ],
            "lot_data": [
                {"TECH": "WB", "DEN": "512G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "AUTO", "LEAD": "LF", "MCP_NO": "A", "LOT_ID": "LOT-A1", "IN_TAT": 200},
                {"TECH": "WB", "DEN": "1024G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "SERVER", "LEAD": "LF", "MCP_NO": "B", "LOT_ID": "LOT-B1", "IN_TAT": 100},
                {"TECH": "WB", "DEN": "1024G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "SERVER", "LEAD": "LF", "MCP_NO": "B", "LOT_ID": "LOT-B2", "IN_TAT": 300},
            ],
        },
    }
    pandas_llm_json = {
        "code": "result_df = pd.DataFrame(columns=['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'WIP', 'LOT_ID', 'IN_TAT'])",
        "output_columns": [*product_grain, "WIP", "LOT_ID", "IN_TAT"],
        "reasoning_steps": ["No data processing is performed because the instruction explicitly requests an empty result."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["columns"] == [*product_grain, "WIP", "LOT_ID", "IN_TAT"]
    assert result["analysis"]["rows"][0]["MCP_NO"] == "B"
    assert result["analysis"]["rows"][0]["WIP"] == 90
    assert result["analysis"]["rows"][0]["LOT_ID"] == "LOT-B2"
    assert result["analysis"]["rows"][0]["IN_TAT"] == 300
    assert "executor_fallback" in result["analysis"]["analysis_code"]


def test_pandas_executor_falls_back_from_step_plan_primitives_for_production_equipment_count() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_grain = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    payload = {
        "intent_plan": {
            "analysis_kind": "generic_recipe_sequence",
            "product_grain": product_grain,
            "top_n": 2,
            "analysis_output_columns": [*product_grain, "PRODUCTION", "EQP_COUNT"],
            "retrieval_jobs": [
                {"dataset_key": "production_today", "source_alias": "production_data"},
                {"dataset_key": "equipment_status", "source_alias": "equipment_data"},
            ],
            "step_plan": [
                {
                    "step_id": "rank_top_production_products",
                    "operation": "rank_top_n",
                    "source_alias": "production_data",
                    "metric": "PRODUCTION",
                    "group_by": product_grain,
                    "top_n": 2,
                    "output_columns": [*product_grain, "PRODUCTION"],
                },
                {
                    "step_id": "summarize_equipment_count_for_top_products",
                    "operation": "equipment_count_by_product",
                    "source_alias": "equipment_data",
                    "count_column": "EQPID",
                    "filter_from_step": "rank_top_production_products",
                    "join_keys": product_grain,
                    "group_by": product_grain,
                    "output_columns": [*product_grain, "EQP_COUNT"],
                },
                {
                    "step_id": "join_production_and_equipment_count",
                    "operation": "left_join",
                    "left_step": "rank_top_production_products",
                    "right_step": "summarize_equipment_count_for_top_products",
                    "join_keys": product_grain,
                    "output_columns": [*product_grain, "PRODUCTION", "EQP_COUNT"],
                },
            ],
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {"TECH": "A", "DEN": "1", "MODE": "M1", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "A1", "PRODUCTION": 50},
                {"TECH": "B", "DEN": "1", "MODE": "M2", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "B1", "PRODUCTION": 90},
                {"TECH": "C", "DEN": "1", "MODE": "M3", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "C1", "PRODUCTION": 70},
            ],
            "equipment_data": [
                {"TECH": "B", "DEN": "1", "MODE": "M2", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "B1", "EQPID": "EQP-1"},
                {"TECH": "B", "DEN": "1", "MODE": "M2", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "B1", "EQPID": "EQP-2"},
                {"TECH": "C", "DEN": "1", "MODE": "M3", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "C1", "EQPID": "EQP-3"},
            ],
        },
    }
    pandas_llm_json = {
        "code": "result_df = pd.DataFrame(columns=['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO', 'PRODUCTION', 'EQP_COUNT'])",
        "output_columns": [*product_grain, "PRODUCTION", "EQP_COUNT"],
        "reasoning_steps": ["No data processing is performed because the instruction explicitly requests an empty result."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 2
    assert result["analysis"]["columns"] == [*product_grain, "PRODUCTION", "EQP_COUNT"]
    assert result["analysis"]["rows"][0]["MODE"] == "M2"
    assert result["analysis"]["rows"][0]["PRODUCTION"] == 90
    assert result["analysis"]["rows"][0]["EQP_COUNT"] == 2
    assert result["analysis"]["rows"][1]["MODE"] == "M3"
    assert result["analysis"]["rows"][1]["EQP_COUNT"] == 1
    assert "executor_fallback" in result["analysis"]["analysis_code"]


def test_pandas_executor_prefers_final_step_columns_over_narrow_plan_columns() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_grain = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    payload = {
        "intent_plan": {
            "analysis_kind": "equipment_count_for_previous_products",
            "product_grain": product_grain,
            "top_n": 2,
            "analysis_output_columns": ["EQP_COUNT"],
            "retrieval_jobs": [
                {
                    "dataset_key": "wip_today",
                    "source_alias": "wip_data",
                    "filters": [
                        {"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]},
                        {"field": "DATE", "op": "eq", "value": "20260620"},
                    ],
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_grain, "WIP"],
                },
                {
                    "dataset_key": "equipment_status",
                    "source_alias": "equipment_data",
                    "required_columns": [*product_grain, "EQPID"],
                },
            ],
            "step_plan": [
                {
                    "step_id": "rank_top_wip_products",
                    "operation": "rank_top_n",
                    "source_alias": "wip_data",
                    "metric": "WIP",
                    "group_by": product_grain,
                    "top_n": 2,
                    "rank_order": "desc",
                    "output_columns": [*product_grain, "WIP"],
                },
                {
                    "step_id": "summarize_equipment_count_for_top_products",
                    "operation": "equipment_count_by_product",
                    "source_alias": "equipment_data",
                    "count_column": "EQPID",
                    "filter_from_step": "rank_top_wip_products",
                    "join_keys": product_grain,
                    "group_by": product_grain,
                    "output_columns": [*product_grain, "EQP_COUNT"],
                },
                {
                    "step_id": "join_wip_and_equipment_count",
                    "operation": "left_join",
                    "left_step": "rank_top_wip_products",
                    "right_step": "summarize_equipment_count_for_top_products",
                    "join_keys": product_grain,
                    "output_columns": [*product_grain, "WIP", "EQP_COUNT"],
                },
            ],
        },
        "state": {},
        "runtime_sources": {
            "wip_data": [
                {"WORK_DT": "20260620", "OPER_NAME": "W/B1", "TECH": "A", "DEN": "1", "MODE": "M1", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "A1", "WIP": 50},
                {"WORK_DT": "20260620", "OPER_NAME": "W/B2", "TECH": "B", "DEN": "1", "MODE": "M2", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "B1", "WIP": 90},
                {"WORK_DT": "20260620", "OPER_NAME": "D/A1", "TECH": "C", "DEN": "1", "MODE": "M3", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "C1", "WIP": 999},
            ],
            "equipment_data": [
                {"TECH": "B", "DEN": "1", "MODE": "M2", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "B1", "EQPID": "EQP-1"},
                {"TECH": "B", "DEN": "1", "MODE": "M2", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "B1", "EQPID": "EQP-2"},
                {"TECH": "A", "DEN": "1", "MODE": "M1", "PKG_TYPE1": "P", "PKG_TYPE2": "Q", "LEAD": "L", "MCP_NO": "A1", "EQPID": "EQP-3"},
            ],
        },
    }
    bad_llm_json = {
        "code": "filtered_wip_data = sources['wip_data'][sources['wip_data']['DATE'] == '20260620']\nresult_df = pd.DataFrame({'EQP_COUNT': [4, 4, 4, 4, 4]})",
        "output_columns": [*product_grain, "WIP", "EQP_COUNT"],
        "reasoning_steps": ["Rank WIP products and join equipment counts."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(bad_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == [*product_grain, "WIP", "EQP_COUNT"]
    assert result["analysis"]["row_count"] == 2
    assert result["analysis"]["rows"][0]["MODE"] == "M2"
    assert result["analysis"]["rows"][0]["WIP"] == 90
    assert result["analysis"]["rows"][0]["EQP_COUNT"] == 2
    assert result["analysis"]["rows"][1]["MODE"] == "M1"
    assert result["analysis"]["rows"][1]["EQP_COUNT"] == 1
    assert "executor_fallback" in result["analysis"]["analysis_code"]


def test_pandas_repair_builder_builds_payload_and_prompt_on_failure() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    repair_payload_builder = load_component("langflow_components/data_analysis_flow/16a_pandas_repair_payload_builder.py")
    repair_prompt_builder = load_component("langflow_components/data_analysis_flow/16b_pandas_repair_prompt_builder.py")
    payload = {
        "request": {"question": "제품별 생산량을 알려줘"},
        "intent_plan": {
            "analysis_kind": "custom_repair_test",
            "product_grain": ["MODE"],
            "retrieval_jobs": [{"dataset_key": "production_today", "source_alias": "production_data"}],
        },
        "state": {"current_data": {"columns": ["MODE", "PRODUCTION"], "rows": [{"MODE": "A", "PRODUCTION": 10}]}},
        "runtime_sources": {
            "production_data": [
                {"MODE": "A", "PRODUCTION": 10},
                {"MODE": "B", "PRODUCTION": 20},
            ]
        },
    }
    bad_pandas_json = {
        "code": "result_df = sources['missing_alias']",
        "output_columns": ["MODE", "PRODUCTION"],
        "reasoning_steps": ["Use a wrong alias."],
    }

    failed = pandas_executor.execute_pandas_from_llm(payload, json.dumps(bad_pandas_json, ensure_ascii=False))
    repair_payload = repair_payload_builder.build_pandas_repair_payload(failed)
    prompt_payload = repair_prompt_builder.build_pandas_repair_prompt_payload(repair_payload)

    assert failed["analysis"]["status"] == "error"
    assert repair_payload["pandas_repair"]["required"] is True
    assert repair_payload["pandas_retry_attempt"] == 1
    assert repair_payload["pandas_execution_branch"]["route"] == "repair"
    assert "missing_alias" in repair_payload["pandas_repair"]["context"]["executed_code"]
    assert "production_data" in repair_payload["pandas_repair"]["context"]["runtime_source_summary"]
    assert not any(str(item).startswith("pandas_executor:") for item in repair_payload.get("warnings", []))
    assert prompt_payload["repair_required"] is True
    assert prompt_payload["prompt_type"] == "pandas_code_repair"
    assert "Failed execution context" in prompt_payload["prompt"]
    assert "missing_alias" in prompt_payload["prompt"]

    retry_exceeded = repair_payload_builder.build_pandas_repair_payload({**failed, "pandas_retry_attempt": 1})
    assert retry_exceeded["pandas_repair"]["required"] is False
    assert retry_exceeded["pandas_repair"]["route"] == "failed"
    assert retry_exceeded["pandas_execution_branch"]["route"] == "failed"


def test_pandas_executor_passes_successful_payload_through_repair_branch() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    repair_payload_builder = load_component("langflow_components/data_analysis_flow/16a_pandas_repair_payload_builder.py")
    payload = {
        "intent_plan": {"analysis_kind": "custom_repair_test", "product_grain": ["MODE"]},
        "state": {},
        "runtime_sources": {"production_data": [{"MODE": "A", "PRODUCTION": 10}]},
    }
    good_pandas_json = {
        "code": "result_df = sources['production_data'].groupby(['MODE'], as_index=False)['PRODUCTION'].sum()",
        "output_columns": ["MODE", "PRODUCTION"],
        "reasoning_steps": ["Aggregate production by MODE."],
    }

    successful = pandas_executor.execute_pandas_from_llm(payload, json.dumps(good_pandas_json, ensure_ascii=False))
    repair_payload = repair_payload_builder.build_pandas_repair_payload(successful)
    passed_through = pandas_executor.execute_pandas_from_llm(repair_payload, "{}")

    assert successful["analysis"]["status"] == "ok"
    assert repair_payload["pandas_repair"]["required"] is False
    assert repair_payload["pandas_execution_branch"]["route"] == "success"
    assert passed_through["analysis"]["rows"] == successful["analysis"]["rows"]


def test_pandas_executor_can_execute_repaired_code_after_failure() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    repair_payload_builder = load_component("langflow_components/data_analysis_flow/16a_pandas_repair_payload_builder.py")
    payload = {
        "intent_plan": {"analysis_kind": "custom_repair_test", "product_grain": ["MODE"]},
        "state": {},
        "runtime_sources": {
            "production_data": [
                {"MODE": "A", "PRODUCTION": 10},
                {"MODE": "A", "PRODUCTION": 15},
                {"MODE": "B", "PRODUCTION": 20},
            ]
        },
    }
    bad_pandas_json = {
        "code": "result_df = sources['missing_alias']",
        "output_columns": ["MODE", "PRODUCTION"],
        "reasoning_steps": ["Use a wrong alias."],
    }
    fixed_pandas_json = {
        "code": "result_df = sources['production_data'].groupby(['MODE'], as_index=False)['PRODUCTION'].sum()",
        "output_columns": ["MODE", "PRODUCTION"],
        "reasoning_steps": ["Use the available production_data source alias."],
    }

    failed = pandas_executor.execute_pandas_from_llm(payload, json.dumps(bad_pandas_json, ensure_ascii=False))
    repair_payload = repair_payload_builder.build_pandas_repair_payload(failed)
    repaired = pandas_executor.execute_pandas_from_llm(repair_payload, json.dumps(fixed_pandas_json, ensure_ascii=False))

    assert repaired["analysis"]["status"] == "ok"
    assert repaired["analysis"]["row_count"] == 2
    assert repaired["analysis"]["rows"][0] == {"MODE": "A", "PRODUCTION": 25}
    assert repaired["pandas_repair"]["status"] == "repaired"
    assert repaired["pandas_repair"]["completed"] is True
    assert not any(str(item).startswith("pandas_executor:") for item in repaired.get("warnings", []))


def test_pandas_executor_rewrites_pd_inf_for_pandas_compatibility() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {"analysis_kind": "production_wip_target_rate", "product_grain": []},
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "result_df = pd.DataFrame([{'WIP': 5, 'PRODUCTION': 10, 'OUT_PLAN': 0}])",
                "result_df['ACHIEVEMENT_RATE'] = result_df['PRODUCTION'].div(result_df['OUT_PLAN']).replace([pd.inf, -pd.inf], 0).fillna(0)",
            ]
        ),
        "output_columns": ["WIP", "PRODUCTION", "OUT_PLAN", "ACHIEVEMENT_RATE"],
        "reasoning_steps": ["Handle division by zero."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"][0]["ACHIEVEMENT_RATE"] == 0
    assert "pd.inf" not in result["analysis"]["analysis_code"]


def test_pandas_executor_normalizes_common_result_aliases() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    join_payload = {
        "intent_plan": {"analysis_kind": "aggregate_join", "product_grain": ["MODE"]},
        "state": {},
        "runtime_sources": {},
    }
    join_llm_json = {
        "code": "result_df = pd.DataFrame([{'MODE': 'LPDDR5', 'PRODUCTION_QUANTITY': 10, 'WIP_QUANTITY': 4}])",
        "output_columns": ["MODE", "PRODUCTION_QUANTITY", "WIP_QUANTITY"],
        "reasoning_steps": [],
    }

    join_result = pandas_executor.execute_pandas_from_llm(join_payload, json.dumps(join_llm_json, ensure_ascii=False))

    assert join_result["analysis"]["columns"] == ["MODE", "PRODUCTION", "WIP"]
    assert join_result["analysis"]["rows"][0]["PRODUCTION"] == 10
    assert join_result["analysis"]["rows"][0]["WIP"] == 4

    aggregate_payload = {
        "intent_plan": {"analysis_kind": "aggregate_wip_total", "scope_label": "DA"},
        "state": {},
        "runtime_sources": {},
    }
    aggregate_llm_json = {
        "code": "result_df = pd.DataFrame([{'TOTAL_WIP': 42}])",
        "output_columns": ["TOTAL_WIP"],
        "reasoning_steps": [],
    }

    aggregate_result = pandas_executor.execute_pandas_from_llm(
        aggregate_payload, json.dumps(aggregate_llm_json, ensure_ascii=False)
    )

    assert aggregate_result["analysis"]["columns"] == ["SCOPE", "WIP"]
    assert aggregate_result["analysis"]["rows"][0] == {"SCOPE": "DA", "WIP": 42}

    scoped_payload = {
        "intent_plan": {
            "analysis_kind": "aggregate_sum",
            "result_scope_columns": [{"column": "OPER_GROUP", "value": "WB", "source_field": "OPER_NAME"}],
            "analysis_output_columns": ["PRODUCTION"],
            "retrieval_jobs": [
                {
                    "dataset_key": "production_today",
                    "source_alias": "production_data",
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]}],
                }
            ],
            "step_plan": [
                {
                    "step_id": "sum_production",
                    "operation": "aggregate_sum",
                    "source_alias": "production_data",
                    "metric": "PRODUCTION",
                    "output_columns": ["PRODUCTION"],
                }
            ],
        },
        "state": {},
        "runtime_sources": {"production_data": [{"OPER_NAME": "W/B1", "PRODUCTION": 10}, {"OPER_NAME": "W/B2", "PRODUCTION": 20}]},
    }
    scoped_llm_json = {
        "code": "result_df = pd.DataFrame([{'PRODUCTION': 30}])",
        "output_columns": ["PRODUCTION"],
        "reasoning_steps": ["Sum production."],
    }

    scoped_result = pandas_executor.execute_pandas_from_llm(scoped_payload, json.dumps(scoped_llm_json, ensure_ascii=False))

    assert scoped_result["analysis"]["columns"] == ["OPER_GROUP", "PRODUCTION"]
    assert scoped_result["analysis"]["rows"] == [{"OPER_GROUP": "WB", "PRODUCTION": 30}]

    lot_payload = {
        "intent_plan": {"analysis_kind": "lot_quantity_summary"},
        "state": {},
        "runtime_sources": {},
    }
    lot_llm_json = {
        "code": "result_df = pd.DataFrame([{'LOT_COUNT': 3, 'WAFER_QTY': 12, 'DIE_QTY': 90}])",
        "output_columns": ["LOT_COUNT", "WAFER_QTY", "DIE_QTY"],
        "reasoning_steps": [],
    }

    lot_result = pandas_executor.execute_pandas_from_llm(lot_payload, json.dumps(lot_llm_json, ensure_ascii=False))

    assert lot_result["analysis"]["columns"] == ["LOT_COUNT", "WF_QTY", "DIE_QTY"]
    assert lot_result["analysis"]["rows"][0]["WF_QTY"] == 12

    equipment_payload = {
        "intent_plan": {"analysis_kind": "equipment_by_model"},
        "state": {},
        "runtime_sources": {},
    }
    equipment_llm_json = {
        "code": "result_df = pd.DataFrame([{'EQP_MODEL': 'MODEL-A', 'EQP_COUNT': 2, 'TOTAL_PRESS_CNT': 9}])",
        "output_columns": ["EQP_MODEL", "EQP_COUNT", "TOTAL_PRESS_CNT"],
        "reasoning_steps": [],
    }

    equipment_result = pandas_executor.execute_pandas_from_llm(
        equipment_payload, json.dumps(equipment_llm_json, ensure_ascii=False)
    )

    assert equipment_result["analysis"]["columns"] == ["EQP_MODEL", "EQP_COUNT", "PRESS_CNT"]
    assert equipment_result["analysis"]["rows"][0]["PRESS_CNT"] == 9


def test_answer_message_adapter_escapes_tilde_strikethrough_markdown() -> None:
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/20_answer_message_adapter.py")
    payload = {
        "answer_message": "결과는 ~~HOLD~~ 상태로 표시됩니다.",
        "data": {
            "columns": ["STATUS"],
            "rows": [{"STATUS": "~~HOLD~~"}],
            "row_count": 1,
        },
    }

    message = answer_message_adapter.build_playground_message(payload)

    assert "\\~\\~HOLD\\~\\~" in message
    assert "~~HOLD~~" not in message


def test_answer_message_adapter_koreanizes_plan_and_pandas_reasoning() -> None:
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/20_answer_message_adapter.py")
    payload = {
        "answer_message": "DA 공정 생산량 상위 제품과 장비 대수입니다.",
        "data": {
            "columns": ["MODE", "PRODUCTION", "EQP_COUNT"],
            "rows": [{"MODE": "HBM3E", "PRODUCTION": 100, "EQP_COUNT": 3}],
            "row_count": 1,
        },
        "applied_scope": {
            "datasets": ["production", "equipment_status"],
            "source_aliases": ["production_data", "equipment_data"],
            "filters_by_source": {"production_data": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1"]}]},
            "params_by_source": {"production_data": {"DATE": "20260617"}},
        },
        "intent_plan": {
            "route": "multi_retrieval",
            "intent_type": "multi_step_analysis",
            "analysis_kind": "rank_top_n",
            "step_plan": [
                {
                    "step_id": "rank_top_production_products",
                    "operation": "rank_top_n",
                    "source_alias": "production_data",
                    "group_by": ["TECH", "DEN", "MODE"],
                    "metric": "PRODUCTION",
                    "top_n": 5,
                    "rank_order": "desc",
                }
            ],
            "reasoning_steps": [
                "The user wants to see the top 5 products by production quantity in the DA process group.",
                "First, I need to retrieve production data filtered by the DA process group and rank products by production quantity.",
                "Then, for each of these top 5 products, I need to find the count of assigned equipment.",
                "This requires two datasets: 'production' for ranking and 'equipment_status' for equipment count.",
                "The analysis involves multiple steps: ranking, aggregating equipment count, and then joining the results.",
            ],
            "retrieval_jobs": [
                {
                    "dataset_key": "production",
                    "source_alias": "production_data",
                    "source_type": "oracle",
                    "purpose": "Get production data for ranking top products.",
                    "params": {"DATE": "20260617"},
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1"]}],
                },
                {
                    "dataset_key": "equipment_status",
                    "source_alias": "equipment_data",
                    "source_type": "oracle",
                    "purpose": "Get equipment status data for counting equipment for top products.",
                },
            ],
        },
        "analysis": {
            "status": "ok",
            "safety_passed": True,
            "executed": True,
            "row_count": 1,
            "columns": ["MODE", "PRODUCTION", "EQP_COUNT"],
            "reasoning_steps": [
                "필터링: Filter production data for DA process operations.",
                "그룹화: Group production data by product grain and sum production to identify top products, then rank and select top 5.",
                "컬럼명 변경: Rename columns in equipment data to match product grain for joining.",
                "필터링: Filter equipment data to include only the top 5 products identified.",
                "그룹화: Group filtered equipment data by product grain and count unique equipment IDs to get the equipment count for each product.",
                "Left join the top products with their total production and the corresponding equipment counts.",
                "Fill any missing equipment counts with 0 and ensure the final output columns match the plan.",
            ],
            "analysis_code": "result_df = sources['production_data']",
        },
    }

    message = answer_message_adapter.build_playground_message(payload)

    assert "사용자는 DA 공정군에서 생산량 기준 상위 5개 제품을 확인하려고 합니다." in message
    assert "먼저 DA 공정군으로 필터링한 생산 데이터를 조회하고 생산량 기준으로 제품 순위를 계산합니다." in message
    assert "상위 제품 순위를 계산하기 위한 생산 데이터를 조회합니다." in message
    assert "DA 공정에 해당하는 생산 데이터만 필터링합니다." in message
    assert "제품 기준으로 생산량을 합산한 뒤 생산량 기준 상위 5개 제품을 선택합니다." in message
    assert "상위 제품별 생산량 결과에 제품별 장비 대수를 left join합니다." in message
    assert "The user wants" not in message
    assert "Filter production data" not in message
    assert "Group production data" not in message
    assert "Get production data" not in message


def test_answer_message_adapter_rebuilds_generic_repeated_intent_reasoning() -> None:
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/20_answer_message_adapter.py")
    payload = {
        "answer_message": "DA/WB 재공 상위 제품과 생산량입니다.",
        "data": {
            "columns": ["RANK_GROUP", "MODE", "WIP", "PRODUCTION"],
            "rows": [{"RANK_GROUP": "DA", "MODE": "LPDDR5", "WIP": 10, "PRODUCTION": 7}],
            "row_count": 1,
        },
        "applied_scope": {
            "datasets": ["wip_today", "production_today"],
            "source_aliases": ["wip_data", "production_data"],
            "filters_by_source": {
                "wip_data": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2"]}],
                "production_data": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2"]}],
            },
            "params_by_source": {
                "wip_data": {"DATE": "20260620"},
                "production_data": {"DATE": "20260620"},
            },
        },
        "intent_plan": {
            "route": "multi_retrieval",
            "intent_type": "multi_step_analysis",
            "analysis_kind": "rank_wip_then_join_production",
            "result_scope_columns": [{"column": "OPER_GROUP", "value": "DA", "source_field": "OPER_NAME"}],
            "reasoning_steps": [
                "Process the required data according to the analysis plan.",
                "Process the required data according to the analysis plan.",
                "Process the required data according to the analysis plan.",
                "The 'top_n' is set to 3 and 'rank_order' to 'desc' as requested for '상위 3개'.",
            ],
            "retrieval_jobs": [
                {"dataset_key": "wip_today", "source_alias": "wip_data", "params": {"DATE": "20260620"}, "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2"]}]},
                {"dataset_key": "production_today", "source_alias": "production_data", "params": {"DATE": "20260620"}, "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2"]}]},
            ],
            "step_plan": [
                {"step_id": "rank_top_wip_products", "operation": "rank_top_n", "source_alias": "wip_data", "group_by": ["TECH", "DEN", "MODE"], "metric": "WIP", "top_n": 3, "rank_order": "desc"},
                {"step_id": "join_production", "operation": "left_join", "left_step": "rank_top_wip_products", "right_step": "production_summary", "join_keys": ["TECH", "DEN", "MODE"]},
            ],
        },
        "analysis": {"status": "ok", "safety_passed": True, "executed": True, "row_count": 1, "columns": ["RANK_GROUP", "MODE", "WIP", "PRODUCTION"]},
    }

    message = answer_message_adapter.build_playground_message(payload)

    assert message.count("분석 계획에 따라 필요한 데이터를 처리합니다.") == 0
    assert "The 'top_n' is set" not in message
    assert "요청 처리에 필요한 데이터셋" in message
    assert "조회 기준일은" in message
    assert "`wip_data` 데이터는 `OPER_GROUP=DA` 범위로 해석된 조건을 적용합니다." in message
    assert "`wip_data`에서" in message
    assert "상위 3개" in message


def test_answer_response_strips_llm_embedded_result_table_before_adapter_table() -> None:
    answer_builder = load_component("langflow_components/data_analysis_flow/19_answer_response_builder.py")
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/20_answer_message_adapter.py")
    payload = {
        "request": {"session_id": "test-session", "question": "DA 생산량 top 5와 장비 대수 알려줘"},
        "intent_plan": {"intent_type": "multi_step_analysis", "analysis_kind": "rank_top_n"},
        "source_results": [
            {"dataset_key": "production", "source_alias": "production_data", "applied_filters": [], "applied_params": {}}
        ],
        "analysis": {
            "status": "ok",
            "safety_passed": True,
            "executed": True,
            "columns": ["TECH", "DEN", "MODE", "PRODUCTION", "EQP_COUNT"],
            "rows": [
                {"TECH": "POP", "DEN": "128G", "MODE": "MCP", "PRODUCTION": 8340, "EQP_COUNT": 3},
                {"TECH": "WB", "DEN": "1024G", "MODE": "DDR5", "PRODUCTION": 7905, "EQP_COUNT": 3},
            ],
            "row_count": 2,
            "errors": [],
        },
    }
    llm_response = {
        "answer_message": "\n".join(
            [
                "DA공정의 생산량 상위 제품과 각 제품별 할당 장비 대수입니다.",
                "적용 조건: DA공정 필터링 및 생산량 기준 상위 제품 선정.",
                "TECH\tDEN\tMODE\t생산량\t할당 장비 대수",
                "POP\t128G\tMCP\t8340\t3",
                "WB\t1024G\tDDR5\t7905\t3",
            ]
        )
    }

    payload = answer_builder.build_answer_response_payload(payload, json.dumps(llm_response, ensure_ascii=False))
    message = answer_message_adapter.build_playground_message(payload)

    assert "POP\t128G\tMCP\t8340\t3" not in payload["answer_message"]
    assert "TECH\tDEN\tMODE" not in payload["answer_message"]
    assert payload["answer_message"].startswith("DA공정의 생산량 상위 제품")
    assert message.count("### 결과 테이블") == 1
    assert message.count("POP") == 1
    assert message.count("WB") == 1


def test_answer_prompt_tells_llm_not_to_render_result_tables() -> None:
    answer_prompt_builder = load_component("langflow_components/data_analysis_flow/18_answer_prompt_builder.py")
    payload = {
        "request": {"question": "DA 생산량 top 5 알려줘"},
        "intent_plan": {"intent_type": "multi_step_analysis", "analysis_kind": "rank_top_n"},
        "analysis": {
            "columns": ["MODE", "PRODUCTION"],
            "rows": [{"MODE": "HBM3E", "PRODUCTION": 100}],
            "row_count": 1,
        },
    }

    prompt = answer_prompt_builder.build_answer_prompt_payload(payload)["prompt"]

    assert "Do not include Markdown tables" in prompt
    assert "answer_message must be narrative text only" in prompt


def load_seed_metadata_payload(module: Any, payload: dict[str, Any], monkeypatch: Any) -> dict[str, Any]:
    install_fake_pymongo(monkeypatch, seed_metadata_docs())
    return module.load_metadata_payload(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        domain_collection_name="agent_v3_domain_items",
        table_catalog_collection_name="agent_v3_table_catalog_items",
        main_flow_filter_collection_name="agent_v3_main_flow_filters",
    )


def seed_metadata_docs() -> dict[str, list[dict[str, Any]]]:
    domain = read_metadata_json("domain_items.json")
    table_catalog = read_metadata_json("table_catalog.json")
    filters = read_metadata_json("main_flow_filters.json")
    domain_docs: list[dict[str, Any]] = []
    for section, value in domain.items():
        if section == "product_key_columns":
            domain_docs.append({"section": section, "key": section, "columns": value})
        elif isinstance(value, dict):
            for key, payload in value.items():
                domain_docs.append({"section": section, "key": key, "payload": payload})
    table_docs = [
        {"dataset_key": key, "payload": payload}
        for key, payload in (table_catalog.get("datasets") or {}).items()
    ]
    filter_docs = [{"filter_key": key, "payload": payload} for key, payload in filters.items()]
    return {
        "agent_v3_domain_items": domain_docs,
        "agent_v3_table_catalog_items": table_docs,
        "agent_v3_main_flow_filters": filter_docs,
    }


def read_metadata_json(filename: str) -> dict[str, Any]:
    return json.loads((ROOT / "metadata" / filename).read_text(encoding="utf-8"))


def _filter_values(job: dict[str, Any], field: str) -> list[Any]:
    values: list[Any] = []
    for item in job.get("filters", []):
        if not isinstance(item, dict) or item.get("field") != field:
            continue
        if "value" in item:
            values.append(item["value"])
        if isinstance(item.get("values"), list):
            values.extend(item["values"])
    return values


class FakeCursor(list):
    def limit(self, value: int) -> "FakeCursor":
        return FakeCursor(self[:value])


class FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor(self.docs)


class FakeDatabase:
    def __init__(self, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
        self.docs_by_collection = docs_by_collection

    def __getitem__(self, collection_name: str) -> FakeCollection:
        return FakeCollection(self.docs_by_collection.get(collection_name, []))


class FakeClient:
    def __init__(self, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
        self.docs_by_collection = docs_by_collection

    def __getitem__(self, database_name: str) -> FakeDatabase:
        return FakeDatabase(self.docs_by_collection)

    def close(self) -> None:
        return None


def install_fake_pymongo(monkeypatch: Any, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return FakeClient(docs_by_collection)

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))
