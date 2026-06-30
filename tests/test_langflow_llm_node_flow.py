from __future__ import annotations

import importlib.util
import json
import sys
import types
from copy import deepcopy
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


def _retrieval_jobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    return jobs


def test_langflow_llm_node_style_flow_contract(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_prompt_builder = load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    dummy_retriever = load_component("langflow_components/data_analysis_flow/07_dummy_data_retriever.py")
    retrieval_adapter = load_component("langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py")
    data_store = load_component("langflow_components/data_analysis_flow/18_mongodb_data_store.py")
    data_loader = load_component("langflow_components/data_analysis_flow/05_mongodb_data_loader.py")
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    answer_prompt_builder = load_component("langflow_components/data_analysis_flow/19_answer_prompt_builder.py")
    answer_builder = load_component("langflow_components/data_analysis_flow/20_answer_response_builder.py")
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/21_answer_message_adapter.py")

    payload = request_loader.build_request_payload("오늘 전체 재공 수량 알려줘", "test-session")
    payload = data_loader.load_payload_from_mongodb(payload, enabled="false")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)

    intent_prompt = intent_prompt_builder.build_intent_prompt_payload(payload)["prompt"]
    assert "Langflow Gemini/LLM 노드" in intent_prompt
    assert "필수 JSON schema" in intent_prompt
    assert "step_plan[].source_alias와 step_plan[].source_aliases는 retrieval_jobs[].source_alias 값과 정확히 일치" in intent_prompt
    assert "filtered scope의 total 질문" in intent_prompt
    assert "filter scope column은 result_scope_columns 또는 final output의 label" in intent_prompt
    assert "input_text='UFBGA qdp'" in intent_prompt
    assert "qdp처럼 마지막 token 하나만 남기지 마세요" in intent_prompt

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
    assert "retrieval_jobs" not in payload
    assert _retrieval_jobs(payload)[0]["source_type"] == "oracle"

    retrieval_payload = dummy_retriever.retrieve_dummy_data(payload)
    payload = retrieval_adapter.adapt_retrieval_payload(payload, retrieval_payload)
    assert payload["runtime_sources"]["wip_total"]
    assert payload["source_results"][0]["preview_rows"]

    pandas_prompt = pandas_prompt_builder.build_pandas_prompt_payload(payload)["prompt"]
    assert "result_df" in pandas_prompt
    assert "aggregate_wip_total" in pandas_prompt
    assert ".to_frame()을 사용하지 마세요" in pandas_prompt

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
    assert "한국어로 답변하세요" in answer_prompt
    assert "wip_today" in answer_prompt

    answer_llm_json = {"answer_message": "오늘 전체 재공 수량은 계산 결과 기준으로 확인되었습니다."}
    payload = answer_builder.build_answer_response_payload(payload, json.dumps(answer_llm_json, ensure_ascii=False))
    assert payload["answer_message"] == answer_llm_json["answer_message"]
    assert payload["data"]["row_count"] == 1
    assert payload["data"]["rows"][0]["WIP"] > 0
    assert "rows" not in payload["analysis"]
    assert payload["analysis"]["rows_moved_to_data"] is True
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
    metadata_json = prompt.split("메타데이터 요약:\n", 1)[1].split("\n\n이전 state 요약:", 1)[0]
    summary = json.loads(metadata_json)

    production = summary["datasets"]["production_today"]
    target = summary["datasets"]["target"]
    assert production["required_param_mappings"] == {"DATE": ["WORK_DATE"]}
    assert production["date_format"] == "YYYYMMDD"
    assert production["date_param_value_for_current_request"] == "20260612"
    assert target["date_format"] == "YYYY-MM-DD"
    assert target["date_param_value_for_current_request"] == "2026-06-12"
    assert "이 dataset에 2026-06-12를 출력하지 마세요" in prompt
    assert "한 dataset의 date format을 다른 dataset에 복사하지 마세요" in prompt


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
    add_test_analysis_recipes(payload, "production_wip_target_rate")
    prompt = intent_prompt_builder.build_intent_prompt_payload(payload)["prompt"]
    metadata_json = prompt.split("메타데이터 요약:\n", 1)[1].split("\n\n이전 state 요약:", 1)[0]
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
    jobs = {job["dataset_key"]: job for job in _retrieval_jobs(payload)}

    assert jobs["production_today"]["params"]["DATE"] == "20260617"
    assert jobs["wip_today"]["params"]["DATE"] == "20260617"
    assert "DATE" not in jobs["target"]["params"]
    assert _filter_values(jobs["production_today"], "DATE") == ["20260617"]
    assert _filter_values(jobs["wip_today"], "DATE") == ["20260617"]
    assert _filter_values(jobs["target"], "DATE") == ["2026-06-17"]


def test_intent_normalizer_builds_recipe_jobs_when_llm_omits_jobs(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    add_test_analysis_recipes(payload, "production_wip_target_rate")
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
    assert [job["source_alias"] for job in _retrieval_jobs(payload)] == [
        "production_data",
        "wip_data",
        "target_data",
    ]
    assert [job["source_type"] for job in _retrieval_jobs(payload)] == ["oracle", "oracle", "goodocs"]
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
    add_test_analysis_recipes(payload, "production_wip_target_rate")
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_wip_target_rate",
        "reasoning_steps": ["Need production, WIP, and target values."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_wip_target_rate"
    assert payload["intent_plan"]["analysis_kind"] == "production_wip_target_rate"
    assert [job["dataset_key"] for job in _retrieval_jobs(payload)] == ["production_today", "wip_today", "target"]
    assert payload["intent_plan"]["step_plan"][0]["recipe_key"] == "production_wip_target_rate"
    assert payload["intent_plan"]["route"] == "multi_retrieval"
    assert any("분석 recipe 'production_wip_target_rate'" in item for item in payload["info"])
    assert not any("분석 recipe 'production_wip_target_rate'" in item for item in payload["warnings"])


def test_intent_normalizer_uses_history_dataset_for_explicit_past_recipe_date(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    request_loader._runtime_reference_date = lambda: "20260629"
    intent_normalizer._runtime_reference_date = lambda: "20260629"

    payload = request_loader.build_request_payload("2026-06-12 생산달성율을 제품별로 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "production_achievement_rate_by_target_plan",
        "reasoning_steps": ["Need production and target values for an explicit past date."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    jobs = _retrieval_jobs(payload)
    assert payload["intent_plan"]["matched_analysis_recipe"] == "production_achievement_rate_by_target_plan"
    assert [job["dataset_key"] for job in jobs] == ["production", "target"]
    assert jobs[0]["params"]["DATE"] == "20260612"
    assert jobs[1]["filters"] == [{"field": "DATE", "op": "eq", "value": "2026-06-12"}]
    assert jobs[1]["primary_quantity_column"] == ["INPUT 계획", "OUT 계획"]
    assert payload["intent_plan"]["step_plan"][1]["metrics"] == ["INPUT 계획", "OUT 계획"]


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

    assert _retrieval_jobs(payload) == []
    assert payload["intent_plan"]["step_plan"] == []
    assert any("datasets도 없어 조회 작업을 보완할 수 없습니다" in item for item in payload["warnings"])


def test_intent_normalizer_recipe_grain_policy_uses_question_scope(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 전체 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    add_test_analysis_recipes(payload, "production_wip_target_rate")
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

    assert plan["result_scope_columns"] == [{"column": "OPER_GROUP", "value": "WB_PROCESS_GROUP", "source_field": "OPER_NAME"}]
    assert any(item.get("field") == "OPER_NAME" for item in _retrieval_jobs(payload)[0]["filters"])


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
    add_test_analysis_recipes(payload, "production_wip_target_rate")
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
    assert [job["dataset_key"] for job in _retrieval_jobs(payload)] == ["production_today", "wip_today", "target"]
    assert payload["intent_plan"]["step_plan"] == [
        {
            "step_id": "detail_rows",
            "operation": "detail_rows",
            "source_alias": "production_data",
            "source_aliases": ["production_data", "wip_data", "target_data"],
        }
    ]
    assert "group_by" not in payload["intent_plan"]["step_plan"][0]
    assert "OPER_NAME" in _retrieval_jobs(payload)[0]["required_columns"]
    assert "PRODUCTION" in _retrieval_jobs(payload)[0]["required_columns"]


def test_intent_normalizer_recipe_defaults_populate_plan(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 INPUT계획대비 D/A공정에서 생산량이 저조한 제품을 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    add_test_analysis_recipes(payload, "low_output_vs_target")
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
    add_test_analysis_recipes(payload, "lot_quantity_summary")
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
    assert [job["dataset_key"] for job in _retrieval_jobs(payload)] == ["lot_status"]
    assert {"LOT_ID", "WF_QTY", "SUB_PROD_QTY"}.issubset(set(_retrieval_jobs(payload)[0]["required_columns"]))


def test_intent_normalizer_removes_unrequested_optional_date_for_raw_lookup(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("lot status data 조회해줘", "test-session", request_date="20260625")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    lot_catalog = payload["metadata"]["table_catalog"]["datasets"]["lot_status"]
    lot_catalog["filter_mappings"]["DATE"] = ["WORK_DATE"]
    lot_catalog["date_format"] = "YYYYMMDD"
    lot_catalog["required_params"] = []
    lot_catalog["required_param_mappings"] = {}
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "detail_rows",
        "datasets": ["lot_status"],
        "retrieval_jobs": [
            {
                "dataset_key": "lot_status",
                "source_alias": "lot_status_data",
                "params": {"DATE": "20260625"},
                "filters": [{"field": "DATE", "op": "eq", "value": "20260625"}],
            }
        ],
        "step_plan": [{"step_id": "retrieve_lot_status", "operation": "detail_rows", "source_alias": "lot_status_data"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = _retrieval_jobs(payload)[0]

    assert "DATE" not in job["params"]
    assert "DATE" not in {item["field"] for item in job["filters"]}


def test_intent_normalizer_keeps_optional_date_filter_when_question_has_date_scope(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("today lot status data 조회해줘", "test-session", request_date="20260625")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    lot_catalog = payload["metadata"]["table_catalog"]["datasets"]["lot_status"]
    lot_catalog["filter_mappings"]["DATE"] = ["WORK_DATE"]
    lot_catalog["date_format"] = "YYYYMMDD"
    lot_catalog["required_params"] = []
    lot_catalog["required_param_mappings"] = {}
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "detail_rows",
        "datasets": ["lot_status"],
        "retrieval_jobs": [{"dataset_key": "lot_status", "source_alias": "lot_status_data"}],
        "step_plan": [{"step_id": "retrieve_lot_status", "operation": "detail_rows", "source_alias": "lot_status_data"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = _retrieval_jobs(payload)[0]

    assert "DATE" not in job["params"]
    assert _filter_values(job, "DATE") == ["20260625"]


def test_intent_normalizer_recipe_aligns_history_dataset_for_date_split(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("어제 생산량과 오늘 생산계획의 차이수량을 제품별로 알려줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    add_test_analysis_recipes(payload, "date_split_production_plan_gap")
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
    assert [job["dataset_key"] for job in _retrieval_jobs(payload)] == ["production", "target"]
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

    assert [job["source_alias"] for job in _retrieval_jobs(payload)] == ["wip_today"]
    assert _retrieval_jobs(payload)[0]["params"]["DATE"] == "20260612"
    assert _retrieval_jobs(payload)[0]["primary_quantity_column"] == "WIP"
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
    assert _filter_values(_retrieval_jobs(payload)[0], "OPER_NAME") == ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]
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
    assert "filter scope와 grouping grain을 분리" in prompt
    assert "group_by는 ranking 또는 aggregation 대상 entity" in prompt
    assert "rank_groups[].field" in prompt
    assert "final output_columns에 그 raw field를 포함하지 마세요" in prompt
    assert "product_grain, step_plan[].group_by, step_plan[].join_keys" in prompt
    assert "retrieval_jobs[].required_columns에는" in prompt
    assert "dataset physical/source column을 요청하세요" in prompt
    assert "standard_column_aliases" in prompt
    assert "total/summary quantity 요청" in prompt
    assert "명시적인 grouping, ranking, detail, raw 표현이 없는 metric/quantity 질문" in prompt
    assert "For 차수별/공정 차수별 questions, group by OPER_NUM" not in prompt

    specialized_prompt = (
        ROOT / "langflow_components" / "data_analysis_flow" / "prompts" / "02_SPECIALIZED_INTENT_PROMPT.md"
    ).read_text(encoding="utf-8")
    assert "rank_group_output_column/output_columns에 OPER_GROUP" in specialized_prompt
    assert "차수별/공정 차수별 질문은 OPER_NUM" in specialized_prompt


def test_intent_prompt_tells_llm_to_separate_comparison_scopes(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_prompt_builder = load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py")

    payload = request_loader.build_request_payload(
        "오늘 INPUT 공정 실적 대비해서 B/G1공정 실적이 얼마나 되는지 제품별로 알려줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)

    prompt = intent_prompt_builder.build_intent_prompt_payload(payload)["prompt"]

    assert "사용자가 여러 scope를 비교" in prompt
    assert "source-specific retrieval_jobs filters" in prompt
    assert "Do not put the B scope filter on the A source" not in prompt
    assert "all process" not in prompt
    assert "PRODUCT_GROUP" not in prompt

    specialized_prompt = (
        ROOT / "langflow_components" / "data_analysis_flow" / "prompts" / "02_SPECIALIZED_INTENT_PROMPT.md"
    ).read_text(encoding="utf-8")
    assert "전 공정/전체 공정/all process" in specialized_prompt
    assert "PRODUCT_GROUP" in specialized_prompt


def test_intent_normalizer_keeps_source_specific_process_filters(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 INPUT 공정 실적 대비해서 B/G1공정 실적이 얼마나 되는지 제품별로 알려줘",
        "test-session",
        request_date="20260623",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    product_keys = payload["metadata"]["domain_items"]["product_key_columns"]
    llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["production_today", "production_today"],
        "filters": [{"field": "OPER_NAME", "op": "in", "values": ["B/G1"]}],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "input_production",
                "filters": [{"field": "OPER_NAME", "op": "eq", "value": "INPUT"}],
            },
            {
                "dataset_key": "production_today",
                "source_alias": "bg1_production",
                "filters": [{"field": "OPER_NAME", "op": "eq", "value": "B/G1"}],
            },
        ],
        "step_plan": [
            {
                "step_id": "agg_input",
                "operation": "aggregate_sum",
                "source_alias": "input_production",
                "metric": "PRODUCTION",
                "group_by": product_keys,
                "output_column": "INPUT_PRODUCTION",
            },
            {
                "step_id": "agg_bg1",
                "operation": "aggregate_sum",
                "source_alias": "bg1_production",
                "metric": "PRODUCTION",
                "group_by": product_keys,
                "output_column": "BG1_PRODUCTION",
            },
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(llm_json, ensure_ascii=False))
    jobs = {job["source_alias"]: job for job in _retrieval_jobs(payload)}

    assert _filter_values(jobs["input_production"], "OPER_NAME") == ["INPUT"]
    assert _filter_values(jobs["bg1_production"], "OPER_NAME") == ["B/G1"]


def test_intent_normalizer_applies_process_scope_per_source_alias(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "어제 DP공정에서 생산량이 가장 많은 제품의 오늘 DA공정 재공을 차수별로 알려줘",
        "test-session",
        request_date="20260624",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    product_keys = payload["metadata"]["domain_items"]["product_key_columns"]
    process_groups = payload["metadata"]["domain_items"]["process_groups"]
    dp_processes = process_groups["DP_DP_PROCESS_GROUP"]["processes"]
    da_processes = process_groups["DA_PROCESS_GROUP"]["processes"]
    combined_processes = [*da_processes, *dp_processes]
    llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "rank_then_lookup",
        "datasets": ["production", "wip_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production",
                "source_alias": "prod_yesterday_dp",
                "params": {"DATE": "20260623"},
                "filters": [
                    {"field": "DATE", "op": "eq", "value": "20260623"},
                    {"field": "OPER_NAME", "op": "in", "values": combined_processes},
                ],
            },
            {
                "dataset_key": "wip_today",
                "source_alias": "wip_today_da",
                "params": {"DATE": "20260624"},
                "filters": [
                    {"field": "DATE", "op": "eq", "value": "20260624"},
                    {"field": "OPER_NAME", "op": "in", "values": combined_processes},
                ],
            },
        ],
        "step_plan": [
            {
                "step_id": "rank_top_product_in_dp",
                "operation": "rank_top_n",
                "source_alias": "prod_yesterday_dp",
                "group_by": product_keys,
                "metric": "PRODUCTION",
                "top_n": 1,
            },
            {
                "step_id": "wip_by_oper_num_for_top_product",
                "operation": "aggregate_sum",
                "source_alias": "wip_today_da",
                "group_by": ["OPER_NUM"],
                "metric": "WIP",
            },
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(llm_json, ensure_ascii=False))
    jobs = {job["source_alias"]: job for job in _retrieval_jobs(payload)}

    assert _filter_values(jobs["prod_yesterday_dp"], "OPER_NAME") == dp_processes
    assert _filter_values(jobs["wip_today_da"], "OPER_NAME") == da_processes


def test_intent_normalizer_labels_product_term_scope_without_raw_condition_column(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 HBM재공 수량을 세부 공정별로 알려줘",
        "test-session",
        request_date="20260623",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_wip_total",
        "datasets": ["wip_today"],
        "retrieval_jobs": [{"dataset_key": "wip_today", "source_alias": "wip_data"}],
        "step_plan": [
            {
                "step_id": "aggregate_wip_by_process",
                "operation": "aggregate_sum",
                "source_alias": "wip_data",
                "metric": "WIP",
                "group_by": ["OPER_NAME"],
                "output_columns": ["OPER_NAME", "WIP"],
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    hbm_filters = _retrieval_jobs(payload)[0].get("filters", [])
    assert any(
        item.get("field") == "TSV_DIE_TYP" and item.get("op") in {"exists", "not_empty"}
        for item in hbm_filters
        if isinstance(item, dict)
    )
    assert {"column": "PRODUCT_GROUP", "value": "HBM", "source_field": "TSV_DIE_TYP"} in plan["result_scope_columns"]
    assert not any(item.get("column") == "TSV_DIE_TYP" for item in plan["result_scope_columns"])


def test_intent_normalizer_clears_process_filter_for_all_process_source(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 제품별로 INPUT공정 실적과 현재 전 공정 재공 수량을 같이 보여줘",
        "test-session",
        request_date="20260623",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    product_keys = payload["metadata"]["domain_items"]["product_key_columns"]
    llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["production_today", "wip_today"],
        "filters": [{"field": "OPER_NAME", "op": "eq", "value": "INPUT"}],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "prod_input",
                "filters": [{"field": "OPER_NAME", "op": "eq", "value": "INPUT"}],
            },
            {"dataset_key": "wip_today", "source_alias": "wip_current_all_process", "filters": []},
        ],
        "step_plan": [
            {"step_id": "agg_input", "operation": "aggregate_sum", "source_alias": "prod_input", "metric": "PRODUCTION", "group_by": product_keys},
            {"step_id": "agg_wip", "operation": "aggregate_sum", "source_alias": "wip_current_all_process", "metric": "WIP", "group_by": product_keys},
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(llm_json, ensure_ascii=False))
    jobs = {job["source_alias"]: job for job in _retrieval_jobs(payload)}

    assert _filter_values(jobs["prod_input"], "OPER_NAME") == ["INPUT"]
    assert _filter_values(jobs["wip_current_all_process"], "OPER_NAME") == []


def test_intent_normalizer_uses_explicit_device_grain_for_rank(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 MOBILE제품 기준으로 생산량이 가장 많은 DEVICE 3개를 알려줘",
        "test-session",
        request_date="20260623",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    product_keys = payload["metadata"]["domain_items"]["product_key_columns"]
    llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["production_today"],
        "top_n": 3,
        "retrieval_jobs": [{"dataset_key": "production_today", "source_alias": "production_today"}],
        "step_plan": [
            {
                "step_id": "rank_mobile_products",
                "operation": "rank_top_n",
                "source_alias": "production_today",
                "metric": "PRODUCTION",
                "group_by": product_keys,
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["product_grain"] == ["DEVICE"]
    assert plan["step_plan"][0]["group_by"] == ["DEVICE"]
    assert plan["step_plan"][0]["top_n"] == 3
    mobile_filters = _retrieval_jobs(payload)[0].get("filters", [])
    assert any(
        item.get("field") == "MCP_NO" and item.get("op") == "empty"
        for item in mobile_filters
        if isinstance(item, dict)
    )


def test_intent_normalizer_uses_quantity_term_source_column_for_unique_count(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("DA EQP_COUNT", "test-session", request_date="20260623")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "detail_rows",
        "datasets": ["equipment_status"],
        "retrieval_jobs": [
            {
                "dataset_key": "equipment_status",
                "source_alias": "equipment_data",
                "required_columns": ["EQUIP_COUNT"],
            }
        ],
        "step_plan": [
            {
                "step_id": "equipment_count",
                "operation": "aggregate_total",
                "source_alias": "equipment_data",
                "metric": "EQUIP_COUNT",
                "output_columns": ["EQUIP_COUNT"],
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    job = _retrieval_jobs(payload)[0]

    assert plan["analysis_kind"] == "unique_count_by_group"
    assert plan["step_plan"][0]["operation"] == "unique_count_by_group"
    assert plan["step_plan"][0]["count_column"] == "EQPID"
    assert plan["step_plan"][0]["output_column"] == "EQP_COUNT"
    assert "EQPID" in job["required_columns"]
    assert "EQUIP_COUNT" not in job["required_columns"]


def test_pandas_prompt_tells_llm_to_handle_dates_without_datetime_imports() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    payload = {
        "request": {"question": "오늘 생산 데이터를 일자 형식에 맞춰 보여줘"},
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "retrieval_jobs": [
                {
                    "dataset_key": "production_today",
                    "source_alias": "production_data",
                    "params": {"DATE": "20260623"},
                    "date_format": "YYYYMMDD",
                }
            ],
        },
        "state": {},
        "runtime_sources": {"production_data": [{"DATE": "20260623", "PRODUCTION": 10}]},
    }

    prompt = pandas_prompt_builder.build_pandas_prompt_payload(payload)["prompt"]

    assert "date/date-format 처리는" in prompt
    assert "datetime/date/timedelta를 import하지 마세요" in prompt
    assert "pd.to_datetime(..., errors='coerce')" in prompt
    assert "string value를 직접 사용하는 것을 우선" in prompt
    assert "underscore로 시작하는 local variable name" in prompt
    assert "이름 안의 underscore는 허용" in prompt
    assert "plan['intent_plan'] 같은 중첩 key를 만들거나 참조하지 마세요" in prompt


def test_pandas_prompt_includes_manual_function_case_text() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    payload = {
        "request": {"question": "find products matching 2048G H-HBM16E"},
        "intent_plan": {"analysis_kind": "detail_rows", "retrieval_jobs": []},
        "runtime_sources": {},
        "state": {},
    }

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(
        payload,
        "When matching product tokens, define match_product_tokens and filter actual source rows.",
    )
    prompt = prompt_payload["prompt"]

    assert "Specialized Functions:" in prompt
    assert "manual_text_input" in prompt
    assert "match_product_tokens" in prompt
    assert prompt_payload["pandas_function_cases"][0]["source"] == "specialized_functions_text"


def test_pandas_prompt_recognizes_raw_specialized_function_definition_without_markdown_fence() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    product_case = {
        "display_name": "Component token product lookup",
        "function_name": "match_product_tokens",
        "use_when": "Use for product token lookup.",
    }
    payload = {
        "request": {"question": "오늘 512G G-777제품 생산량 알려줘"},
        "metadata": {"domain_items": {"pandas_function_cases": {"component_token_product_lookup": product_case}}},
        "intent_plan": {
            "analysis_kind": "aggregate_total",
            "pandas_function_case": {
                "key": "component_token_product_lookup",
                "function_name": "match_product_tokens",
                "input_text": "오늘 512G G-777제품 생산량 알려줘",
            },
            "retrieval_jobs": [{"dataset_key": "production_today", "source_alias": "production_data"}],
            "step_plan": [
                {
                    "operation": "apply_pandas_function_case",
                    "source_alias": "production_data",
                    "function_case_key": "component_token_product_lookup",
                    "function_name": "match_product_tokens",
                    "input_text": "오늘 512G G-777제품 생산량 알려줘",
                }
            ],
        },
        "runtime_sources": {"production_data": [{"DEN": "512G", "MCP_NO": "G-777A2I", "PRODUCTION": 3}]},
        "state": {},
    }
    helper_text = "\n".join(
        [
            "def match_product_tokens(input_text, source_df):",
            "    return source_df.copy()",
        ]
    )

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(payload, helper_text)
    runtime = prompt_payload["pandas_function_case_runtime"]

    assert runtime["manual_function_names"] == ["match_product_tokens"]
    assert runtime["missing_helpers"] == []
    assert "missing_helpers" in prompt_payload["prompt"]
    assert "match_product_tokens" in prompt_payload["prompt"]
    assert "match_product_tokens(input_text, source_df)" in prompt_payload["prompt"]
    assert "def match_product_tokens" in prompt_payload["prompt"]
    assert "return source_df.copy()" in prompt_payload["prompt"]


def test_pandas_prompt_uses_only_matching_specialized_function_block() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    product_case = {
        "display_name": "Component token product lookup",
        "function_name": "match_product_tokens",
        "use_when": "Use for product token lookup.",
    }
    payload = {
        "request": {"question": "오늘 da에서 UFBGA qdp제품 생산량 알려줘"},
        "metadata": {"domain_items": {"pandas_function_cases": {"component_token_product_lookup": product_case}}},
        "intent_plan": {
            "analysis_kind": "aggregate_total",
            "pandas_function_case": {
                "key": "component_token_product_lookup",
                "function_name": "match_product_tokens",
                "input_text": "UFBGA qdp",
            },
            "retrieval_jobs": [{"dataset_key": "production_today", "source_alias": "production_data"}],
            "step_plan": [
                {
                    "operation": "apply_pandas_function_case",
                    "source_alias": "production_data",
                    "function_case_key": "component_token_product_lookup",
                    "function_name": "match_product_tokens",
                    "input_text": "UFBGA qdp",
                }
            ],
        },
        "runtime_sources": {"production_data": [{"PKG_TYPE1": "UFBGA", "PKG_TYPE2": "QDP", "PRODUCTION": 3}]},
        "state": {},
    }
    helper_text = "\n".join(
        [
            "## function_name: match_product_tokens",
            "",
            "PRODUCT BLOCK ONLY: use all product tokens.",
            "",
            "```python",
            "def match_product_tokens(input_text, source_df):",
            "    return source_df.copy()",
            "```",
            "",
            "## function_name: match_lot_hold_conditions",
            "",
            "LOT BLOCK SHOULD NOT APPEAR: use hold status and IN_TAT.",
            "",
            "```python",
            "def match_lot_hold_conditions(input_text, source_df):",
            "    return source_df.copy()",
            "```",
        ]
    )

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(payload, helper_text)
    prompt = prompt_payload["prompt"]
    runtime = prompt_payload["pandas_function_case_runtime"]

    assert runtime["manual_function_names"] == ["match_lot_hold_conditions", "match_product_tokens"]
    assert runtime["selected_function_names"] == ["match_product_tokens"]
    assert "PRODUCT BLOCK ONLY" in prompt
    assert "LOT BLOCK SHOULD NOT APPEAR" not in prompt
    assert "match_product_tokens(input_text, source_df)" in prompt
    assert "match_lot_hold_conditions(input_text, source_df)" not in prompt


def test_intent_prompt_includes_specialized_prompt_text_input() -> None:
    intent_prompt_builder = load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py")
    payload = {
        "request": {"question": "오늘 DA 공정 생산량 알려줘", "request_date": "20260627"},
        "metadata": {"domain_items": {}, "table_catalog": {"datasets": {}}},
        "state": {},
    }
    specialized_prompt = "공정 질문에서는 공정 그룹 metadata를 먼저 확인하고 source별 scope를 분리한다."

    prompt_payload = intent_prompt_builder.build_intent_prompt_payload(payload, specialized_prompt)
    prompt = prompt_payload["prompt"]

    assert "추가 Specialized Prompt:" in prompt
    assert specialized_prompt in prompt
    assert prompt_payload["specialized_prompt"] == specialized_prompt


def test_pandas_prompt_selects_domain_function_case_for_product_token_lookup() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    function_code = [
        "def match_product_tokens(input_text, frame, token_columns=None, output_order=None):",
        "    return frame.copy()",
    ]
    product_case = {
        "display_name": "Component token product lookup",
        "aliases": ["product list lookup"],
        "function_name": "match_product_tokens",
        "function_code": function_code,
        "use_when": "Use when the user asks to find products from unregistered product attribute tokens.",
        "required_source_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
        "token_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
        "output_order": ["TECH", "DEN", "PKG_TYPE1", "LEAD", "PKG_TYPE2", "MODE", "MCP_NO"],
    }
    payload = {
        "request": {"question": "find product list for 2048G H-HBM16E"},
        "metadata": {"domain_items": {"pandas_function_cases": {"component_token_product_lookup": product_case}}},
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "product_grain": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
            "retrieval_jobs": [{"dataset_key": "product_catalog", "source_alias": "products"}],
        },
        "runtime_sources": {
            "products": [
                {
                    "TECH": "TSV",
                    "DEN": "2048G",
                    "MODE": "HBM3E",
                    "PKG_TYPE1": "HBM",
                    "PKG_TYPE2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                }
            ]
        },
        "state": {},
    }

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(payload)
    prompt = prompt_payload["prompt"]

    assert prompt_payload["pandas_function_cases"][0]["key"] == "component_token_product_lookup"
    assert "metadata.domain_items.pandas_function_cases" in prompt
    assert "match_product_tokens" in prompt
    assert "function_code" in prompt
    assert "Specialized Functions에 붙여넣은 code와 설명은 pandas code 작성을 위한 reference" in prompt
    assert "helper 함수를 generated code 안에 정의한 뒤 호출" in prompt


def test_pandas_prompt_selects_product_token_case_when_required_columns_are_too_strict() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    product_case = {
        "display_name": "제품 속성 토큰 검색",
        "aliases": ["제품 검색", "제품 찾아줘"],
        "function_name": "match_product_tokens",
        "use_when": "사용자가 제품의 여러 속성을 혼합하여 자유로운 형태로 제품을 검색할 때",
        "required_source_columns": ["TECH", "DEN", "MODE", "ORG", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "DEVICE"],
        "token_columns": [
            "TECH",
            "DEN",
            "DENSITY",
            "MODE",
            "ORG",
            "PKG_TYPE1",
            "PKG1",
            "PKG_TYPE2",
            "PKG2",
            "LEAD",
            "MCP_NO",
            "DEVICE_DESC",
        ],
        "pandas_code_instructions": [
            "match_product_tokens helper를 사용하여 입력 토큰과 제품 컬럼 값을 매칭합니다."
        ],
    }
    payload = {
        "request": {"question": "A-134 512M 제품 리스트 보여줘"},
        "metadata": {"domain_items": {"pandas_function_cases": {"component_token_product_lookup": product_case}}},
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "retrieval_jobs": [{"dataset_key": "product_catalog", "source_alias": "product_data"}],
        },
        "runtime_sources": {
            "product_data": [
                {
                    "TECH": "TSV",
                    "DEN": "2048G",
                    "MODE": "HBM3E",
                    "ORG": "A",
                    "PKG_TYPE1": "HBM",
                    "PKG_TYPE2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                    "DEVICE_DESC": "HBM3E 16Hi",
                }
            ]
        },
        "state": {},
    }

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(payload)
    prompt = prompt_payload["prompt"]

    assert prompt_payload["pandas_function_cases"][0]["key"] == "component_token_product_lookup"
    assert "match_product_tokens" in prompt
    assert "token filtering 없이 전체 product list를 반환하는 것은 잘못된 결과" in prompt


def test_pandas_prompt_selects_product_token_case_for_korean_product_list_question() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    product_case = {
        "display_name": "product token lookup",
        "function_name": "match_product_tokens",
        "required_source_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "DEVICE"],
        "token_columns": ["TECH", "DEN", "DENSITY", "MODE", "PKG_TYPE1", "PKG1", "PKG_TYPE2", "PKG2", "LEAD", "MCP_NO", "DEVICE_DESC"],
    }
    payload = {
        "request": {"question": "A-134 512M \uc81c\ud488 \ub9ac\uc2a4\ud2b8 \ubcf4\uc5ec\uc918"},
        "metadata": {"domain_items": {"pandas_function_cases": {"component_token_product_lookup": product_case}}},
        "intent_plan": {"analysis_kind": "detail_rows", "retrieval_jobs": []},
        "runtime_sources": {
            "product_data": [
                {
                    "TECH": "TSV",
                    "DEN": "2048G",
                    "MODE": "HBM3E",
                    "PKG_TYPE1": "HBM",
                    "PKG_TYPE2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                    "DEVICE_DESC": "HBM3E 16Hi",
                }
            ]
        },
        "state": {},
    }

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(payload)

    assert prompt_payload["pandas_function_cases"][0]["key"] == "component_token_product_lookup"


def test_pandas_executor_loads_function_case_helper_from_metadata() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    function_code = [
        "def match_product_tokens(input_text, frame, token_columns=None, output_order=None):",
        "    columns = token_columns or ['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO']",
        "    result = frame.copy()",
        "    for token in str(input_text or '').split():",
        "        normalized_token = str(token).strip().upper()",
        "        if not normalized_token:",
        "            continue",
        "        for column in columns:",
        "            if column not in result.columns:",
        "                continue",
        "            values = result[column].dropna().map(lambda value: str(value).strip().upper()).unique()",
        "            if normalized_token in set(values):",
        "                result = result[result[column].map(lambda value: str(value).strip().upper()) == normalized_token]",
        "                break",
        "    return result.reset_index(drop=True)",
    ]
    payload = {
        "metadata": {
            "domain_items": {
                "pandas_function_cases": {
                    "component_token_product_lookup": {
                        "function_name": "match_product_tokens",
                        "function_code": function_code,
                    }
                }
            }
        },
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "product_grain": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
        },
        "runtime_sources": {
            "products": [
                {"TECH": "TSV", "DEN": "2048G", "MODE": "HBM3E", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM16E"},
                {"TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "POP", "LEAD": "LF", "MCP_NO": "L-269P1Q"},
            ]
        },
        "state": {},
    }
    pandas_llm_json = {
        "code": "result_df = match_product_tokens('2048G H-HBM16E', sources['products'])",
        "output_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
        "reasoning_steps": ["Use registered product token helper."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["DEN"] == "2048G"
    assert result["analysis"]["rows"][0]["MCP_NO"] == "H-HBM16E"


def test_pandas_executor_allows_inline_selected_function_case_helper() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "metadata": {
            "domain_items": {
                "pandas_function_cases": {
                    "custom_inline_lookup": {
                        "function_name": "match_custom_rows",
                        "use_when": "Use for a custom inline row lookup.",
                    }
                }
            }
        },
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "pandas_function_case": {
                "key": "custom_inline_lookup",
                "function_name": "match_custom_rows",
                "input_text": "A001",
            },
            "step_plan": [
                {
                    "step_id": "custom_inline_lookup",
                    "operation": "apply_pandas_function_case",
                    "source_alias": "custom_data",
                    "function_case_key": "custom_inline_lookup",
                    "function_name": "match_custom_rows",
                    "input_text": "A001",
                }
            ],
        },
        "runtime_sources": {"custom_data": [{"ITEM_ID": "A001", "VALUE": 7}]},
        "state": {},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "def match_custom_rows(input_text, frame):",
                "    return frame[frame['ITEM_ID'] == input_text].copy()",
                "result_df = match_custom_rows(plan['pandas_function_case']['input_text'], sources['custom_data'])",
            ]
        ),
        "output_columns": ["ITEM_ID", "VALUE"],
        "reasoning_steps": ["Define the specialized helper inline and call it."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["executed"] is True
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["ITEM_ID"] == "A001"


def test_pandas_executor_loads_function_case_helper_from_prompt_payload_text() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_case = {
        "display_name": "Component token product lookup",
        "function_name": "match_product_tokens",
        "use_when": "Use for product token lookup.",
        "token_columns": ["DEN", "MCP_NO"],
    }
    payload = {
        "request": {"question": "2048G H-HBM16E product list"},
        "metadata": {"domain_items": {"pandas_function_cases": {"component_token_product_lookup": product_case}}},
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "pandas_function_case": {
                "key": "component_token_product_lookup",
                "function_name": "match_product_tokens",
                "input_text": "2048G H-HBM16E product list",
            },
            "step_plan": [
                {
                    "step_id": "component_token_product_lookup",
                    "operation": "apply_pandas_function_case",
                    "source_alias": "products",
                    "function_case_key": "component_token_product_lookup",
                    "function_name": "match_product_tokens",
                    "input_text": "2048G H-HBM16E product list",
                }
            ],
        },
        "runtime_sources": {
            "products": [
                {"DEN": "2048G", "MCP_NO": "H-HBM16E"},
                {"DEN": "64G", "MCP_NO": "L-269P1Q"},
            ]
        },
        "state": {},
    }
    helper_text = "\n".join(
        [
            "```python",
            "def match_product_tokens(input_text, frame):",
            "    result = frame.copy()",
            "    for token in str(input_text or '').split():",
            "        normalized = token.upper()",
            "        for column in ['DEN', 'MCP_NO']:",
            "            if column in result.columns and normalized in set(result[column].astype(str).str.upper()):",
            "                result = result[result[column].astype(str).str.upper() == normalized]",
            "                break",
            "    return result.reset_index(drop=True)",
            "",
            "result_df = match_product_tokens('example', sources[list(sources.keys())[0]])",
            "```",
        ]
    )
    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(payload, helper_text)
    pandas_llm_json = {
        "code": "result_df = match_product_tokens(plan['pandas_function_case']['input_text'], sources['products'])",
        "output_columns": ["DEN", "MCP_NO"],
        "reasoning_steps": ["Call the specialized helper from the prompt payload."],
    }

    result = pandas_executor.execute_pandas_from_llm(prompt_payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["MCP_NO"] == "H-HBM16E"


def test_pandas_executor_loads_function_case_helper_from_direct_specialized_functions_input() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_case = {
        "display_name": "Component token product lookup",
        "function_name": "match_product_tokens",
        "use_when": "Use for product token lookup.",
        "token_columns": ["DEN", "MCP_NO"],
    }
    payload = {
        "request": {"question": "2048G H-HBM16E product list"},
        "metadata": {"domain_items": {"pandas_function_cases": {"component_token_product_lookup": product_case}}},
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "pandas_function_case": {
                "key": "component_token_product_lookup",
                "function_name": "match_product_tokens",
                "input_text": "2048G H-HBM16E product list",
            },
            "step_plan": [
                {
                    "step_id": "component_token_product_lookup",
                    "operation": "apply_pandas_function_case",
                    "source_alias": "products",
                    "function_case_key": "component_token_product_lookup",
                    "function_name": "match_product_tokens",
                    "input_text": "2048G H-HBM16E product list",
                }
            ],
        },
        "runtime_sources": {
            "products": [
                {"DEN": "2048G", "MCP_NO": "H-HBM16E"},
                {"DEN": "64G", "MCP_NO": "L-269P1Q"},
            ]
        },
        "state": {},
    }
    helper_text = "\n".join(
        [
            "```python",
            "def match_product_tokens(input_text, frame):",
            "    result = frame.copy()",
            "    for token in str(input_text or '').split():",
            "        normalized = token.upper()",
            "        for column in ['DEN', 'MCP_NO']:",
            "            if column in result.columns and normalized in set(result[column].astype(str).str.upper()):",
            "                result = result[result[column].astype(str).str.upper() == normalized]",
            "                break",
            "    return result.reset_index(drop=True)",
            "```",
        ]
    )
    pandas_llm_json = {
        "code": "result_df = match_product_tokens(plan['pandas_function_case']['input_text'], sources['products'])",
        "output_columns": ["DEN", "MCP_NO"],
        "reasoning_steps": ["Call the helper loaded from the executor input."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False), helper_text)

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["MCP_NO"] == "H-HBM16E"


def test_pandas_executor_loads_function_case_helper_from_text_input_message_object() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")

    class TextInputMessage:
        def __init__(self, text: str) -> None:
            self.text = text

    payload = {
        "metadata": {
            "domain_items": {
                "pandas_function_cases": {
                    "component_token_product_lookup": {"function_name": "match_product_tokens"}
                }
            }
        },
        "intent_plan": {
            "analysis_kind": "aggregate_total",
            "pandas_function_case": {
                "key": "component_token_product_lookup",
                "function_name": "match_product_tokens",
                "input_text": "512G G-777",
            },
            "step_plan": [
                {
                    "operation": "apply_pandas_function_case",
                    "function_case_key": "component_token_product_lookup",
                    "function_name": "match_product_tokens",
                    "source_alias": "production_data",
                    "input_text": "512G G-777",
                }
            ],
        },
        "runtime_sources": {
            "production_data": [
                {"DEN": "512G", "MCP_NO": "G-777A2I", "PRODUCTION": 3},
                {"DEN": "512G", "MCP_NO": "G-888", "PRODUCTION": 10},
            ]
        },
        "state": {},
    }
    helper_text = "\n".join(
        [
            "```python",
            "def match_product_tokens(input_text, source_df):",
            "    result = source_df.copy()",
            "    result = result[result['MCP_NO'].astype(str).str.startswith('G-777')].reset_index(drop=True)",
            "    result.attrs['matched_conditions'] = [",
            "        {'token': '512G', 'column': 'DEN', 'match_type': 'eq', 'value': '512G'},",
            "        {'token': 'G-777', 'column': 'MCP_NO', 'match_type': 'startswith', 'value': 'G-777'},",
            "    ]",
            "    return result",
            "```",
        ]
    )
    pandas_llm_json = {
        "code": "\n".join(
            [
                "match_product_df = match_product_tokens('512G G-777', sources['production_data'])",
                "total_production = match_product_df['PRODUCTION'].sum()",
                "result_df = pd.DataFrame([{'PRODUCTION': total_production}])",
            ]
        ),
        "output_columns": ["PRODUCTION"],
    }

    result = pandas_executor.execute_pandas_from_llm(
        payload,
        json.dumps(pandas_llm_json, ensure_ascii=False),
        TextInputMessage(helper_text),
    )

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"] == [{"PRODUCTION": 3}]
    assert result["analysis"]["function_case_trace"]["dataframe_attrs"]["match_product_df"]["matched_conditions"] == [
        {"token": "512G", "column": "DEN", "match_type": "eq", "value": "512G"},
        {"token": "G-777", "column": "MCP_NO", "match_type": "startswith", "value": "G-777"},
    ]


def test_intent_normalizer_routes_unregistered_product_tokens_to_function_case(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")

    question = "생산 데이터에서 64G L-269P1Q 제품 찾아줘"
    payload = request_loader.build_request_payload(question, "test-session", request_date="20260626")
    payload["state"] = {
        "current_data": {
            "data_ref": {"store": "mongodb", "ref_id": "previous-products"},
            "columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
            "rows": [{"TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "POP", "LEAD": "LF", "MCP_NO": "L-269P1Q"}],
            "row_count": 1,
        }
    }
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "followup_transform",
        "analysis_kind": "detail_rows",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "product_data",
                "purpose": "filter product data",
                "params": {"DATE": "20260626"},
                "filters": [
                    {"field": "DEN", "op": "eq", "value": "64G"},
                    {"field": "MCP_NO", "op": "eq", "value": "L-269P1Q"},
                    {"field": "DATE", "op": "eq", "value": "20260626"},
                    {"field": "PRODUCT_GRAIN", "op": "from_state"},
                ],
            }
        ],
        "step_plan": [{"step_id": "filter_product_data", "operation": "filter_data", "source_alias": "product_data"}],
        "requires_full_previous_result_restore": True,
        "previous_result_restore_mode": "full",
        "reasoning_steps": ["Use product tokens to find matching product rows."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    job = _retrieval_jobs(payload)[0]
    fields = {item.get("field") for item in job.get("filters", [])}

    assert plan["intent_type"] == "detail_lookup"
    assert plan["analysis_kind"] == "detail_rows"
    assert plan["pandas_function_case"]["key"] == "component_token_product_lookup"
    assert plan["pandas_function_case"]["function_name"] == "match_product_tokens"
    assert plan["pandas_function_case"]["input_text"] == "64G L-269P1Q"
    assert plan["step_plan"][0]["operation"] == "apply_pandas_function_case"
    assert plan["step_plan"][0]["function_name"] == "match_product_tokens"
    assert "DEN" not in fields
    assert "MCP_NO" not in fields
    assert "PRODUCT_GRAIN" not in fields
    assert any(ref.get("section") == "pandas_function_cases" for ref in payload["metadata_context"]["domain_refs"])

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(
        {
            **payload,
            "runtime_sources": {
                "product_data": [
                    {"TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "POP", "LEAD": "LF", "MCP_NO": "L-269P1Q"}
                ]
            },
        },
        "제품 토큰 lookup은 match_product_tokens helper 형태로 result_df를 만든다.",
    )

    assert prompt_payload["pandas_function_cases"][-1]["key"] == "component_token_product_lookup"
    assert "선택된 pandas function case를 helper match_product_tokens" in prompt_payload["prompt"]
    assert "downstream step의 group_by/metric/output_columns에 필요한 column이 helper output에 모두 있으면" in prompt_payload["prompt"]
    assert "helper output을 key table로만 사용하고" in prompt_payload["prompt"]
    assert "반드시 매칭되어야 하는 조건 token이 source data 어느 컬럼에도 매칭되지 않으면" in prompt_payload["prompt"]


def test_intent_normalizer_rejects_ambiguous_product_token_dataset_guess(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    question = "64G L-269 ASSY 제품 찾아줘"
    payload = request_loader.build_request_payload(question, "test-session", request_date="20260628")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "detail_lookup",
        "analysis_kind": "detail_rows",
        "datasets": ["wip_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "wip_today",
                "source_alias": "wip_data",
                "purpose": "Guess WIP data for product lookup.",
                "params": {"DATE": "20260628"},
                "filters": [
                    {"field": "DEN", "op": "eq", "value": "64G"},
                    {"field": "MCP_NO", "op": "eq", "value": "L-269"},
                    {"field": "ORG", "op": "eq", "value": "ASSY"},
                ],
            }
        ],
        "step_plan": [{"step_id": "filter_wip", "operation": "filter_data", "source_alias": "wip_data"}],
        "reasoning_steps": ["Incorrectly guess wip_today for product lookup."],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert plan["pandas_function_case"]["key"] == "component_token_product_lookup"
    assert plan["pandas_function_case"]["function_name"] == "match_product_tokens"
    assert plan["requires_dataset_selection"] is True
    assert plan["datasets"] == []
    assert _retrieval_jobs(payload) == []
    assert plan["step_plan"] == []
    assert any("제품 token만으로는 조회 dataset을 확정할 수 없습니다" in item for item in plan["normalizer_errors"])


def test_intent_normalizer_routes_product_token_metric_filters_to_function_case(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")

    question = "오늘 lpddr4 lc 64g 제품 생산량 알려줘"
    payload = request_loader.build_request_payload(question, "test-session", request_date="20260627")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_total",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "purpose": "Retrieve today's production quantity for LPDDR4 LC 64G product.",
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
        "reasoning_steps": [
            "Map lpddr4 to MODE='LPDDR4'.",
            "Map 64g to DEN='64G'.",
            "Map lc to PKG_TYPE1='LC'.",
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    job = _retrieval_jobs(payload)[0]
    fields = {item.get("field") for item in job.get("filters", [])}

    assert plan["intent_type"] == "single_retrieval_analysis"
    assert plan["analysis_kind"] == "aggregate_total"
    assert plan["pandas_function_case"]["key"] == "component_token_product_lookup"
    assert plan["pandas_function_case"]["function_name"] == "match_product_tokens"
    assert plan["step_plan"][0]["operation"] == "apply_pandas_function_case"
    assert plan["step_plan"][0]["source_alias"] == "production_data"
    assert plan["step_plan"][1]["operation"] == "aggregate_data"
    assert plan["step_plan"][1]["input_step_id"] == "component_token_product_lookup"
    assert "MODE" not in fields
    assert "DEN" not in fields
    assert "PKG_TYPE1" not in fields
    assert "DATE" in fields

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(
        {
            **payload,
            "runtime_sources": {
                "production_data": [
                    {"DATE": "20260627", "MODE": "LPDDR4", "DEN": "64G", "PKG_TYPE1": "LC", "PRODUCTION": 10}
                ]
            },
        },
        "```python\ndef match_product_tokens(input_text, frame):\n    return frame.copy()\n```",
    )

    assert "먼저 선택된 pandas function case를 적용하세요" in prompt_payload["prompt"]
    assert "remaining step_plan step" in prompt_payload["prompt"]


def test_intent_normalizer_uses_function_case_metadata_token_columns(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    question = "오늘 AAA 제품 생산량 알려줘"
    payload = request_loader.build_request_payload(question, "test-session", request_date="20260627")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    payload["metadata"]["domain_items"]["pandas_function_cases"]["component_token_product_lookup"]["token_columns"] = [
        "CUSTOM_CODE"
    ]
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_total",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "params": {"DATE": "20260627"},
                "filters": [
                    {"field": "CUSTOM_CODE", "op": "eq", "value": "AAA"},
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
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    fields = {item.get("field") for item in _retrieval_jobs(payload)[0].get("filters", [])}

    assert plan["pandas_function_case"]["key"] == "component_token_product_lookup"
    assert plan["pandas_function_case"]["token_columns"] == ["CUSTOM_CODE"]
    assert "CUSTOM_CODE" not in fields
    assert "DATE" in fields


def test_intent_normalizer_routes_wip_product_attribute_filters_to_function_case(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    question = "오늘 WB공정에서 CP 48G LPDDR5 제품 재공 알려줘"
    payload = request_loader.build_request_payload(question, "test-session", request_date="20260630")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_wip_total",
        "datasets": ["wip_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "wip_today",
                "source_alias": "wb_wip_today",
                "params": {"DATE": "20260630"},
                "filters": [
                    {"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2", "W/B3", "W/B4", "W/B5", "W/B6"]},
                    {"field": "MODE", "op": "starts_with", "value": "LPDDR5"},
                    {"field": "DEN", "op": "eq", "value": "48G"},
                    {"field": "DATE", "op": "eq", "value": "20260630"},
                ],
            }
        ],
        "step_plan": [
            {
                "step_id": "aggregate_wb_wip_total",
                "operation": "aggregate_by_group",
                "source_alias": "wb_wip_today",
                "metric": "WIP",
                "group_by": [],
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    fields = {item.get("field") for item in _retrieval_jobs(payload)[0].get("filters", [])}

    assert plan["pandas_function_case"]["key"] == "component_token_product_lookup"
    assert plan["pandas_function_case"]["input_text"] == "CP 48G LPDDR5"
    assert plan["step_plan"][0]["operation"] == "apply_pandas_function_case"
    assert plan["step_plan"][1]["input_step_id"] == "component_token_product_lookup"
    assert "OPER_NAME" in fields
    assert "DATE" in fields
    assert "MODE" not in fields
    assert "DEN" not in fields


def test_intent_normalizer_prunes_wip_job_for_production_only_question(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    question = "오늘 WB에서 제품별 생산량 알려줘"
    payload = request_loader.build_request_payload(question, "test-session", request_date="20260630")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "multi_step_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["production_today", "wip_today"],
        "product_grain": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "params": {"DATE": "20260630"},
                "filters": [{"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]}],
            },
            {
                "dataset_key": "wip_today",
                "source_alias": "wip_data",
                "params": {"DATE": "20260630"},
                "filters": [{"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]}],
            },
        ],
        "step_plan": [
            {"step_id": "aggregate_production", "operation": "aggregate_by_group", "source_alias": "production_data", "metric": "PRODUCTION"},
            {"step_id": "aggregate_wip", "operation": "aggregate_by_group", "source_alias": "wip_data", "metric": "WIP"},
            {"step_id": "join_production_wip", "operation": "left_join", "left_step": "aggregate_production", "right_step": "aggregate_wip"},
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]

    assert [job["dataset_key"] for job in _retrieval_jobs(payload)] == ["production_today"]
    assert plan["intent_type"] == "single_retrieval_analysis"
    assert plan["metric"] == "PRODUCTION"
    assert all(step.get("source_alias") != "wip_data" for step in plan["step_plan"])


def test_intent_normalizer_keeps_registered_product_terms_out_of_function_case(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    question = "오늘 POP 제품 생산량 알려줘"
    payload = request_loader.build_request_payload(question, "test-session", request_date="20260627")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
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

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = payload["intent_plan"]
    job = _retrieval_jobs(payload)[0]

    assert "pandas_function_case" not in plan
    assert plan["step_plan"][0]["operation"] == "aggregate_data"
    assert _filter_values(job, "MODE") == ["LP"]
    assert _filter_values(job, "PKG_TYP1") == ["LFBGA", "TFBGA", "UFBGA", "VFBGA", "WFBGA"]
    assert not any(item.get("section") == "pandas_function_cases" for item in payload["metadata_context"]["domain_refs"])


def test_intent_normalizer_augments_existing_jobs_from_metadata(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    add_test_analysis_recipes(payload, "production_wip_target_rate")
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
    jobs = {job["dataset_key"]: job for job in _retrieval_jobs(payload)}

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
    assert {"WORK_DATE", "OPER_NAME", "PRODUCTION"}.issubset(set(jobs["production_today"]["required_columns"]))
    assert "PKG_TYPE1" not in jobs["production_today"]["required_columns"]
    assert jobs["production_today"]["filter_mappings"]["PKG_TYPE1"] == ["PKG_TYP1"]
    assert jobs["production_today"]["standard_column_aliases"]["PKG_TYPE1"] == ["PKG_TYP1"]
    assert {"DATE", "OUT계획", "INPUT계획"}.issubset(set(jobs["target"]["required_columns"]))
    assert "PKG_TYPE1" not in jobs["target"]["required_columns"]
    assert "PKG_TYPE2" not in jobs["target"]["required_columns"]
    assert any("params/filters를 보완" in item for item in payload["info"])
    assert not any("params/filters를 보완" in item for item in payload["warnings"])


def test_intent_normalizer_uses_product_terms_for_existing_jobs(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("오늘 LPDDR5 W/B 공정 재공과 생산량을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    payload["metadata"]["domain_items"].setdefault("product_terms", {})["LPDDR5_PRODUCT"] = {
        "display_name": "LPDDR5 제품",
        "aliases": ["LPDDR5", "LPDDR5 제품"],
        "condition": {"MODE": {"value": "LPDDR5"}},
    }
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
    job = _retrieval_jobs(payload)[0]

    assert _filter_values(job, "MODE") == ["LPDDR5"]
    assert _filter_values(job, "OPER_NAME") == ["W/B1", "W/B2", "W/B3", "W/B4", "W/B5", "W/B6"]


def test_intent_normalizer_does_not_hardcode_product_wip_production_join(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 da에서 재공과 생산량을 제품별로 알려줘",
        "test-session",
        request_date="20260622",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    wrong_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["wip_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "wip_today",
                "source_alias": "wip_today_rank",
                "required_columns": ["DATE", "OPER_NAME", "WIP"],
                "filters": [],
                "params": {},
            }
        ],
        "step_plan": [
            {
                "step_id": "rank_wip_products",
                "operation": "rank_top_n",
                "source_alias": "wip_today_rank",
                "metric": "WIP",
                "top_n": 3,
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(wrong_llm_json, ensure_ascii=False))
    jobs = {job["dataset_key"]: job for job in _retrieval_jobs(payload)}

    assert payload["intent_plan"]["intent_type"] == "single_retrieval_analysis"
    assert payload["intent_plan"]["analysis_kind"] == "rank_top_n"
    assert payload["intent_plan"]["datasets"] == ["wip_today"]
    assert [step["operation"] for step in payload["intent_plan"]["step_plan"]] == ["rank_top_n"]
    assert set(jobs) == {"wip_today"}
    assert "production_today" not in jobs


def test_intent_normalizer_does_not_hardcode_yesterday_product_wip_production_join(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "어제 da에서 재공과 생산량을 제품별로 알려줘",
        "test-session",
        request_date="20260622",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    wrong_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "datasets": ["wip_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "wip_today",
                "source_alias": "wip_today_rank",
                "required_columns": ["DATE", "OPER_NAME", "WIP"],
                "filters": [],
                "params": {},
            }
        ],
        "step_plan": [{"step_id": "rank_wip_products", "operation": "rank_top_n", "source_alias": "wip_today_rank"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(wrong_llm_json, ensure_ascii=False))
    jobs = {job["dataset_key"]: job for job in _retrieval_jobs(payload)}

    assert payload["intent_plan"]["analysis_kind"] == "rank_top_n"
    assert payload["intent_plan"]["datasets"] == ["wip_today"]
    assert set(jobs) == {"wip_today"}
    assert "production" not in jobs
    assert jobs["wip_today"]["params"]["DATE"] == "20260622"


def test_intent_normalizer_replaces_wrong_product_alias_filter_with_metadata_condition(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("HBM 제품의 생산량을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_total",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "filters": [{"field": "TECH", "op": "eq", "value": "HBM"}],
                "params": {},
            }
        ],
        "step_plan": [{"step_id": "aggregate_production", "operation": "aggregate_total"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = _retrieval_jobs(payload)[0]

    assert any(item.get("field") == "TSV_DIE_TYP" and item.get("op") == "not_empty" for item in job["filters"])
    assert _filter_values(job, "TECH") == []


def test_intent_normalizer_converts_rich_product_conditions_to_filters(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload("POP 제품 생산량을 보여줘", "test-session")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_total",
        "datasets": ["production_today"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "filters": [],
                "params": {},
            }
        ],
        "step_plan": [{"step_id": "aggregate_production", "operation": "aggregate_total"}],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    filters = _retrieval_jobs(payload)[0]["filters"]

    assert {"field": "MODE", "op": "starts_with", "value": "LP"} in filters
    assert {"field": "PKG_TYP1", "op": "in", "values": ["LFBGA", "TFBGA", "UFBGA", "VFBGA", "WFBGA"]} in filters
    assert {"field": "MCP_NO", "op": "not_empty"} in filters


def test_intent_normalizer_treats_non_catalog_metric_name_as_output_label(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")

    payload = request_loader.build_request_payload("today package out by product", "test-session", request_date="20260625")
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    product_grain = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    intent_llm_json = {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["production_today"],
        "analysis_output_columns": [*product_grain, "PKG_OUT_QTY"],
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "prod_today_pkg",
                "params": {"DATE": "20260625"},
                "filters": [{"field": "OPER_NAME", "op": "eq", "value": "SHIP PKT"}],
                "required_columns": ["DATE", "OPER_NAME", *product_grain, "PKG_OUT_QTY"],
            }
        ],
        "step_plan": [
            {
                "step_id": "aggregate_pkg_out_by_product",
                "operation": "aggregate",
                "source_alias": "prod_today_pkg",
                "group_by": product_grain,
                "metric": "PKG_OUT_QTY",
                "output_columns": [*product_grain, "PKG_OUT_QTY"],
            }
        ],
    }

    payload = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    required_columns = _retrieval_jobs(payload)[0]["required_columns"]

    assert "PKG_OUT_QTY" not in required_columns
    assert "PRODUCTION" in required_columns

    payload["runtime_sources"] = {
        "prod_today_pkg": [
            {
                "WORK_DATE": "20260625",
                "OPER_NAME": "SHIP PKT",
                "TECH": "TSV",
                "DEN": "2048G",
                "MODE": "HBM3E",
                "PKG_TYP1": "HBM",
                "PKG_TYP2": "HBM",
                "LEAD": "LF",
                "MCP_NO": "H-HBM16E",
                "PRODUCTION": 10,
            }
        ]
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "prod_df = sources['prod_today_pkg']",
                "prod_df = prod_df[(prod_df['OPER_NAME'] == 'SHIP PKT') & (prod_df['DATE'] == '20260625')]",
                "result_df = prod_df.groupby(['TECH', 'DEN', 'MODE', 'PKG_TYPE1', 'PKG_TYPE2', 'LEAD', 'MCP_NO'], dropna=False)['PRODUCTION'].sum().reset_index()",
                "result_df = result_df.rename(columns={'PRODUCTION': 'PKG_OUT_QTY'})",
            ]
        ),
        "output_columns": [*product_grain, "PKG_OUT_QTY"],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"][0]["PKG_OUT_QTY"] == 10


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

    assert plan["analysis_kind"] == "equipment_by_model"
    assert plan["state_product_keys"] == [
        {"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "MCP_NO": "EMPTY"}
    ]
    assert any(item.get("field") == "PRODUCT_GRAIN" for item in _retrieval_jobs(payload)[0]["filters"])


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

    assert plan["analysis_kind"] == "equipment_by_model"
    assert plan["state_product_keys"] == [{"MODE": "LPDDR5"}, {"MODE": "HBM"}]
    assert any(item.get("field") == "PRODUCT_GRAIN" for item in _retrieval_jobs(payload)[0]["filters"])


def test_intent_normalizer_does_not_hardcode_followup_equipment_count_plan(monkeypatch: Any) -> None:
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

    assert plan["analysis_kind"] == "equipment_by_model"
    assert plan["datasets"] == ["equipment_status", "lot_status"]
    assert [job["dataset_key"] for job in _retrieval_jobs(payload)] == ["equipment_status", "lot_status"]
    assert any(
        condition.get("field") == "PRODUCT_GRAIN"
        for job in _retrieval_jobs(payload)
        for condition in job.get("filters", [])
    )
    assert plan["step_plan"][0]["operation"] == "count"
    assert plan["state_product_keys"] == [
        {
            "TECH": "FC",
            "DEN": "128G",
            "MODE": "LPDDR5",
            "PKG_TYPE1": "UFBGA",
            "PKG_TYPE2": "MOBILE",
            "LEAD": "LF",
            "MCP_NO": "EMPTY",
        }
    ]
    assert plan["previous_result_restore_mode"] == "summary"


def test_retrieval_adapter_preserves_raw_source_columns_for_pandas_stage(monkeypatch: Any) -> None:
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

    assert row == {"EQPID": "EQP1", "PKG1": "UFBGA", "PKG2": "MOBILE", "MCPSALENO": "EMPTY", "MODE": "LPDDR5"}
    assert "PKG_TYPE1" not in row
    assert "PKG_TYPE2" not in row
    assert "MCP_NO" not in row
    assert adapted["source_results"][0]["columns"] == ["EQPID", "PKG1", "PKG2", "MCPSALENO", "MODE"]


def test_intent_normalizer_keeps_cross_source_join_keys_as_standard_columns() -> None:
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    mapped_catalog = {
        "dataset_family": "production",
        "source_type": "oracle",
        "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": "SELECT * FROM T WHERE WORK_DT = {DATE}"},
        "required_params": ["DATE"],
        "columns": ["TECH", "DENSITY", "MODE", "PKG1", "PKG2", "LEAD", "MCPSALENO", "PRODUCTION"],
        "filter_mappings": {
            "DATE": ["WORK_DT"],
            "TECH": ["TECH"],
            "DEN": ["DENSITY"],
            "MODE": ["MODE"],
            "PKG_TYPE1": ["PKG1"],
            "PKG_TYPE2": ["PKG2"],
            "LEAD": ["LEAD"],
            "MCP_NO": ["MCPSALENO"],
        },
        "standard_column_aliases": {
            "DEN": ["DENSITY"],
            "PKG_TYPE1": ["PKG1"],
            "PKG_TYPE2": ["PKG2"],
            "MCP_NO": ["MCPSALENO"],
        },
        "primary_quantity_column": "PRODUCTION",
    }
    payload = {
        "request": {"question": "join production and wip by product", "request_date": "20260612"},
        "state": {},
        "metadata": {
            "domain_items": {"product_key_columns": product_keys},
            "table_catalog": {
                "datasets": {
                    "production": mapped_catalog,
                    "wip": {**mapped_catalog, "dataset_family": "wip", "primary_quantity_column": "WIP"},
                }
            },
        },
    }
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["production", "wip"],
        "product_grain": product_keys,
        "retrieval_jobs": [
            {"dataset_key": "production", "source_alias": "production_data", "params": {}, "filters": []},
            {"dataset_key": "wip", "source_alias": "wip_data", "params": {}, "filters": []},
        ],
        "step_plan": [
            {
                "step_id": "join_result",
                "operation": "left_join",
                "source_alias": "production_data",
                "join_keys": product_keys,
            }
        ],
    }

    normalized = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))

    assert normalized["intent_plan"]["step_plan"][0]["join_keys"] == product_keys
    assert _retrieval_jobs(normalized)[0]["filter_mappings"]["DEN"] == ["DENSITY"]


def test_intent_normalizer_repairs_metric_detail_rows_to_total_aggregate() -> None:
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    payload = _wafer_metric_payload("오늘 WB 공정의 WAFER 기준 실적 수량 알려줘", product_keys)
    intent_llm_json = _wafer_detail_intent_json()

    normalized = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    plan = normalized["intent_plan"]
    job = _retrieval_jobs(normalized)[0]

    assert plan["analysis_kind"] == "generic_aggregate_recipe"
    assert plan["product_grain"] == []
    assert plan["analysis_output_columns"] == ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"]
    assert plan["step_plan"][0]["operation"] == "aggregate_sum_by_group"
    assert plan["step_plan"][0]["group_by"] == []
    assert plan["step_plan"][0]["metrics"] == ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"]
    assert "PRODUCTION" in job["required_columns"]
    assert "NETDIE_300_CNT" in job["required_columns"]
    assert _filter_values(job, "OPER_NAME") == ["W/B1", "W/B2", "W/B3", "W/B4", "W/B5", "W/B6"]
    assert any("metric detail_rows 계획을 요청 grain 기준 집계" in item for item in normalized["info"])


def test_intent_normalizer_uses_requested_grain_for_metric_aggregate() -> None:
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]

    product_payload = _wafer_metric_payload("오늘 WB 공정 WAFER 기준 실적 수량 제품별로 알려줘", product_keys)
    product_result = intent_normalizer.normalize_intent_payload(
        product_payload,
        json.dumps(_wafer_detail_intent_json(), ensure_ascii=False),
    )
    assert product_result["intent_plan"]["step_plan"][0]["group_by"] == product_keys
    assert product_result["intent_plan"]["analysis_output_columns"] == [*product_keys, "WAFER_OUT_QTY", "FAIL_UNIT_QTY"]

    oper_num_payload = _wafer_metric_payload("오늘 WB 공정 WAFER 기준 실적 수량 공정 차수별로 알려줘", product_keys)
    oper_num_result = intent_normalizer.normalize_intent_payload(
        oper_num_payload,
        json.dumps(_wafer_detail_intent_json(), ensure_ascii=False),
    )
    assert oper_num_result["intent_plan"]["step_plan"][0]["group_by"] == ["OPER_NUM"]
    assert "OPER_NUM" in _retrieval_jobs(oper_num_result)[0]["required_columns"]


def test_intent_normalizer_keeps_explicit_metric_raw_data_request_as_detail_rows() -> None:
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    payload = _wafer_metric_payload("오늘 WB 공정 WAFER 기준 실적 원본 데이터를 보여줘", product_keys)

    normalized = intent_normalizer.normalize_intent_payload(payload, json.dumps(_wafer_detail_intent_json(), ensure_ascii=False))

    assert normalized["intent_plan"]["analysis_kind"] == "detail_rows"
    assert normalized["intent_plan"]["detail_rows_requested"] is True


def test_intent_normalizer_maps_standard_required_columns_to_physical_source_columns() -> None:
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    mapped_catalog = {
        "dataset_family": "production",
        "source_type": "oracle",
        "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": "SELECT * FROM T WHERE WORK_DATE = {DATE}"},
        "required_params": ["DATE"],
        "columns": ["WORK_DATE", "TECH", "DENSITY", "MODE", "PKG1", "PKG2", "LEAD", "ORG", "MCP_NO", "OPER", "PRODUCTION"],
        "filter_mappings": {
            "DATE": ["WORK_DATE"],
            "TECH": ["TECH"],
            "DEN": ["DENSITY"],
            "MODE": ["MODE"],
            "PKG_TYPE1": ["PKG1"],
            "PKG_TYPE2": ["PKG2"],
            "LEAD": ["LEAD"],
            "MCP_NO": ["MCP_NO"],
            "OPER_NUM": ["OPER"],
        },
        "standard_column_aliases": {
            "DATE": ["WORK_DATE"],
            "DEN": ["DENSITY"],
            "PKG_TYPE1": ["PKG1"],
            "PKG_TYPE2": ["PKG2"],
            "OPER_NUM": ["OPER"],
        },
        "primary_quantity_column": "PRODUCTION",
    }
    payload = {
        "request": {"question": "어제 DA공정 제품별 실적과 재공 조인", "request_date": "20260621"},
        "state": {},
        "metadata": {
            "domain_items": {"product_key_columns": product_keys},
            "main_flow_filters": {
                "MCP_NO": {"column_candidates": ["MCP_NO", "MCP NO", "MCP number"]},
            },
            "table_catalog": {"datasets": {"production": mapped_catalog}},
        },
    }
    intent_llm_json = {
        "intent_type": "multi_source_analysis",
        "analysis_kind": "aggregate_join",
        "datasets": ["production"],
        "product_grain": product_keys,
        "retrieval_jobs": [
            {
                "dataset_key": "production",
                "source_alias": "production_data",
                "required_columns": [
                    "TECH",
                    "DEN",
                    "MODE",
                    "PKG_TYPE1",
                    "PKG_TYPE2",
                    "LEAD",
                    "ORG",
                    "MCP NO",
                    "MCP number",
                    "PRODUCTION",
                ],
                "filter_mappings": {"DATE": ["WORK_DT"]},
                "filters": [],
                "params": {},
            }
        ],
        "step_plan": [
            {
                "step_id": "join_result",
                "operation": "left_join",
                "source_alias": "production_data",
                "join_keys": product_keys,
            }
        ],
    }

    normalized = intent_normalizer.normalize_intent_payload(payload, json.dumps(intent_llm_json, ensure_ascii=False))
    job = _retrieval_jobs(normalized)[0]

    assert normalized["intent_plan"]["step_plan"][0]["join_keys"] == product_keys
    assert {"TECH", "DENSITY", "MODE", "PKG1", "PKG2", "LEAD", "MCP_NO", "PRODUCTION"}.issubset(
        set(job["required_columns"])
    )
    assert "ORG" in job["required_columns"]
    assert "PKG_TYPE1" not in job["required_columns"]
    assert "PKG_TYPE2" not in job["required_columns"]
    assert "DEN" not in job["required_columns"]
    assert "MCP NO" not in job["required_columns"]
    assert "MCP number" not in job["required_columns"]
    assert job["filter_mappings"]["DATE"] == ["WORK_DATE"]
    assert job["filter_mappings"]["PKG_TYPE1"] == ["PKG1"]
    assert job["standard_column_aliases"]["PKG_TYPE1"] == ["PKG1"]
    assert job["pandas_preprocessing"]["standardize_columns"] is True
    assert normalized["intent_plan"]["pandas_preprocessing"]["standardize_columns"] is True


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
    assert _retrieval_jobs(payload) == []
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
    job = _retrieval_jobs(payload)[0]

    assert "OPER_SHORT_DESC" in job["required_columns"]
    assert "LOT_ID" in job["required_columns"]
    assert "WF_QTY" in job["required_columns"]
    assert payload["intent_plan"]["step_plan"][0]["group_by"] == ["OPER_NAME"]


def test_intent_normalizer_keeps_lot_count_as_generic_step_plan(monkeypatch: Any) -> None:
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

    assert payload["intent_plan"]["analysis_kind"] == "unique_count_by_group"
    assert payload["intent_plan"]["step_plan"][0]["operation"] == "unique_count_by_group"
    assert payload["intent_plan"]["step_plan"][0]["group_by"] == ["OPER_NAME"]
    assert _retrieval_jobs(payload)[0]["dataset_key"] == "lot_status"
    assert "OPER_SHORT_DESC" in _retrieval_jobs(payload)[0]["required_columns"]
    assert not any("LOT_ID unique count" in item for item in payload["info"])


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
    add_test_analysis_recipes(payload, "top_wip_process_hold_lot_in_tat")
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
    jobs = {job["dataset_key"]: job for job in _retrieval_jobs(payload)}

    assert plan["analysis_kind"] == "top_wip_process_hold_lot_in_tat"
    assert plan["matched_analysis_recipe"] == "top_wip_process_hold_lot_in_tat"
    assert plan["route"] == "multi_retrieval"
    assert plan["datasets"] == ["wip_today", "lot_status"]
    assert plan["top_n"] == 3
    assert plan["recipe_grain_policy"] == "recipe_step_grain"
    assert plan["analysis_output_columns"] == ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]
    assert [step["operation"] for step in plan["step_plan"]] == ["rank_top_n", "aggregate_by_group", "left_join"]
    assert plan["step_plan"][0]["top_n"] == 3
    assert jobs["wip_today"]["source_alias"] == "wip_data"
    assert jobs["lot_status"]["source_alias"] == "lot_status_data"
    assert "WIP" in jobs["wip_today"]["required_columns"]
    assert "IN_TAT" in jobs["lot_status"]["required_columns"]
    assert "LOT_HOLD_STAT_CD" not in {item["field"] for item in jobs["lot_status"]["filters"]}
    assert any("분석 recipe 'top_wip_process_hold_lot_in_tat'" in item for item in payload["info"])

    prompt = pandas_prompt_builder.build_pandas_prompt_payload({**payload, "runtime_sources": {"wip_data": [], "lot_status_data": []}})["prompt"]
    assert "모든 step을 순서대로 구현" in prompt
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
    add_test_analysis_recipes(payload, "top_wip_process_hold_lot_in_tat")
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
    assert [job["dataset_key"] for job in _retrieval_jobs(payload)] == ["lot_status"]


def test_intent_normalizer_does_not_apply_wip_lot_recipe_to_production_equipment_question(monkeypatch: Any) -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")

    payload = request_loader.build_request_payload(
        "오늘 DA공정에서 생산량 상위 5개 제품과 각 제품별 할당 장비 대수를 보여줘",
        "test-session",
    )
    payload = load_seed_metadata_payload(metadata_loader, payload, monkeypatch)
    add_test_analysis_recipes(payload, "top_production_products_equipment_count")
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
    jobs = {job["dataset_key"]: job for job in _retrieval_jobs(payload)}

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
    add_test_analysis_recipes(payload, "top_wip_product_oldest_lot")
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
    jobs = {job["dataset_key"]: job for job in _retrieval_jobs(payload)}

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

    assert _retrieval_jobs(payload)[0]["required_columns"] == ["EQP_MODEL", "PKG1", "EQPID"]


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
    assert set(result["analysis"]["columns"]) == {"RANK_GROUP", "rank", "MODE", "WIP", "PRODUCTION"}
    assert result["analysis"]["rows"][0]["rank"] == 1
    assert result["analysis"]["rows"][0]["PRODUCTION"] == 7


def test_pandas_executor_joins_physical_source_columns_with_standard_aliases() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    payload = {
        "intent_plan": {
            "analysis_kind": "aggregate_join",
            "product_grain": product_keys,
            "retrieval_jobs": [
                {
                    "dataset_key": "production",
                    "source_alias": "production_data",
                    "filter_mappings": {
                        "DEN": ["DENSITY"],
                        "PKG_TYPE1": ["PKG1"],
                        "PKG_TYPE2": ["PKG2"],
                        "MCP_NO": ["MCPSALENO"],
                    },
                    "standard_column_aliases": {
                        "DEN": ["DENSITY"],
                        "PKG_TYPE1": ["PKG1"],
                        "PKG_TYPE2": ["PKG2"],
                        "MCP_NO": ["MCPSALENO"],
                    },
                },
                {"dataset_key": "wip", "source_alias": "wip_data"},
            ],
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {
                    "TECH": "TSV",
                    "DENSITY": "2048G",
                    "MODE": "HBM3E",
                    "PKG1": "HBM",
                    "PKG2": "HBM",
                    "LEAD": "LF",
                    "MCPSALENO": "H-HBM16E",
                    "PRODUCTION": 100,
                }
            ],
            "wip_data": [
                {
                    "TECH": "TSV",
                    "DEN": "2048G",
                    "MODE": "HBM3E",
                    "PKG_TYPE1": "HBM",
                    "PKG_TYPE2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                    "WIP": 40,
                }
            ],
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "prod_source_columns = list(sources['production_data'].columns)",
                "product_keys = plan['product_grain']",
                "prod = sources['production_data'].groupby(product_keys, as_index=False)['PRODUCTION'].sum()",
                "wip = sources['wip_data'].groupby(product_keys, as_index=False)['WIP'].sum()",
                "result_df = prod.merge(wip, on=product_keys, how='inner')",
                "result_df['HAS_PKG1'] = 'PKG1' in prod_source_columns",
                "result_df['HAS_PKG_TYPE1'] = 'PKG_TYPE1' in prod_source_columns",
            ]
        ),
        "output_columns": [*product_keys, "PRODUCTION", "WIP", "HAS_PKG1", "HAS_PKG_TYPE1"],
        "reasoning_steps": ["Join sources by standard product keys."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["DEN"] == "2048G"
    assert result["analysis"]["rows"][0]["PKG_TYPE1"] == "HBM"
    assert result["analysis"]["rows"][0]["MCP_NO"] == "H-HBM16E"
    assert result["analysis"]["rows"][0]["PRODUCTION"] == 100
    assert result["analysis"]["rows"][0]["WIP"] == 40
    assert result["analysis"]["rows"][0]["HAS_PKG1"] is False
    assert result["analysis"]["rows"][0]["HAS_PKG_TYPE1"] is True


def test_pandas_executor_joins_actual_today_production_wip_physical_columns_by_standard_keys() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    production_mappings = {
        "DATE": ["WORK_DATE"],
        "PKG_TYPE1": ["PKG_TYP1"],
        "PKG_TYPE2": ["PKG_TYP2"],
        "OPER_NUM": ["OPER"],
    }
    wip_mappings = {
        "DATE": ["WORK_DATE"],
        "DEN": ["DENSITY"],
        "PKG_TYPE1": ["PKG1"],
        "PKG_TYPE2": ["PKG2"],
        "OPER_NUM": ["OPER"],
    }
    payload = {
        "intent_plan": {
            "analysis_kind": "aggregate_join",
            "product_grain": product_keys,
            "retrieval_jobs": [
                {
                    "dataset_key": "production_today",
                    "source_alias": "production_data",
                    "filter_mappings": production_mappings,
                    "required_param_mappings": {"DATE": ["WORK_DATE"]},
                    "standard_column_aliases": production_mappings,
                    "filters": [
                        {"field": "DATE", "op": "eq", "value": "20260621"},
                        {"field": "OPER_NUM", "op": "eq", "value": "DA10"},
                    ],
                },
                {
                    "dataset_key": "wip_today",
                    "source_alias": "wip_data",
                    "filter_mappings": wip_mappings,
                    "required_param_mappings": {"DATE": ["WORK_DATE"]},
                    "standard_column_aliases": wip_mappings,
                    "filters": [
                        {"field": "DATE", "op": "eq", "value": "20260621"},
                        {"field": "OPER_NUM", "op": "eq", "value": "DA10"},
                    ],
                },
            ],
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {
                    "WORK_DATE": "20260621",
                    "OPER": "DA10",
                    "TECH": "TSV",
                    "DEN": "2048G",
                    "MODE": "HBM3E",
                    "PKG_TYP1": "HBM",
                    "PKG_TYP2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                    "PRODUCTION": 100,
                },
                {
                    "WORK_DATE": "20260621",
                    "OPER": "DA20",
                    "TECH": "TSV",
                    "DEN": "2048G",
                    "MODE": "HBM3E",
                    "PKG_TYP1": "HBM",
                    "PKG_TYP2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                    "PRODUCTION": 999,
                },
            ],
            "wip_data": [
                {
                    "WORK_DATE": "20260621",
                    "OPER": "DA10",
                    "TECH": "TSV",
                    "DENSITY": "2048G",
                    "MODE": "HBM3E",
                    "PKG1": "HBM",
                    "PKG2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                    "WIP": 40,
                }
            ],
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "product_keys = plan['product_grain']",
                "prod_source = sources['production_data']",
                "prod_source = prod_source[(prod_source['DATE'] == '20260621') & (prod_source['OPER_NUM'] == 'DA10')]",
                "wip_source = sources['wip_data']",
                "wip_source = wip_source[(wip_source['DATE'] == '20260621') & (wip_source['OPER_NUM'] == 'DA10')]",
                "prod = prod_source.groupby(product_keys, as_index=False)['PRODUCTION'].sum()",
                "wip = wip_source.groupby(product_keys, as_index=False)['WIP'].sum()",
                "result_df = prod.merge(wip, on=product_keys, how='inner')",
            ]
        ),
        "output_columns": [*product_keys, "PRODUCTION", "WIP"],
        "reasoning_steps": ["Join actual source columns after standardization."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["DEN"] == "2048G"
    assert result["analysis"]["rows"][0]["PKG_TYPE1"] == "HBM"
    assert result["analysis"]["rows"][0]["PRODUCTION"] == 100
    assert result["analysis"]["rows"][0]["WIP"] == 40


def test_pandas_executor_joins_actual_history_production_wip_physical_columns_by_standard_keys() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    production_mappings = {
        "DATE": ["WORK_DATE"],
        "DEN": ["DENSITY"],
        "PKG_TYPE1": ["PKG1"],
        "PKG_TYPE2": ["PKG2"],
        "OPER_NUM": ["OPER"],
    }
    wip_mappings = {
        "DATE": ["WORK_DATE"],
        "DEN": ["DENSITY"],
        "PKG_TYPE1": ["PKG_TYP1"],
        "PKG_TYPE2": ["PKG_TYP2"],
        "OPER_NUM": ["OPER"],
    }
    payload = {
        "intent_plan": {
            "analysis_kind": "aggregate_join",
            "product_grain": product_keys,
            "retrieval_jobs": [
                {
                    "dataset_key": "production",
                    "source_alias": "production_data",
                    "filter_mappings": production_mappings,
                    "required_param_mappings": {"DATE": ["WORK_DATE"]},
                    "standard_column_aliases": production_mappings,
                },
                {
                    "dataset_key": "wip",
                    "source_alias": "wip_data",
                    "filter_mappings": wip_mappings,
                    "required_param_mappings": {"DATE": ["WORK_DATE"]},
                    "standard_column_aliases": wip_mappings,
                },
            ],
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {
                    "WORK_DATE": "20260621",
                    "OPER": "WB10",
                    "TECH": "TSV",
                    "DENSITY": "2048G",
                    "MODE": "HBM3E",
                    "PKG1": "HBM",
                    "PKG2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                    "PRODUCTION": 88,
                }
            ],
            "wip_data": [
                {
                    "WORK_DATE": "20260621",
                    "OPER": "WB10",
                    "TECH": "TSV",
                    "DENSITY": "2048G",
                    "MODE": "HBM3E",
                    "PKG_TYP1": "HBM",
                    "PKG_TYP2": "HBM",
                    "LEAD": "LF",
                    "MCP_NO": "H-HBM16E",
                    "WIP": 33,
                }
            ],
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "product_keys = plan['product_grain']",
                "prod = sources['production_data'].groupby(product_keys, as_index=False)['PRODUCTION'].sum()",
                "wip = sources['wip_data'].groupby(product_keys, as_index=False)['WIP'].sum()",
                "result_df = prod.merge(wip, on=product_keys, how='inner')",
            ]
        ),
        "output_columns": [*product_keys, "PRODUCTION", "WIP"],
        "reasoning_steps": ["Join history source columns after standardization."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["DEN"] == "2048G"
    assert result["analysis"]["rows"][0]["PKG_TYPE1"] == "HBM"
    assert result["analysis"]["rows"][0]["PRODUCTION"] == 88
    assert result["analysis"]["rows"][0]["WIP"] == 33


def test_pandas_prompt_uses_standardized_source_columns_for_pandas_view() -> None:
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    product_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    payload = {
        "request": {"question": "production and wip join by product"},
        "intent_plan": {
            "analysis_kind": "aggregate_join",
            "product_grain": product_keys,
            "retrieval_jobs": [
                {
                    "dataset_key": "production",
                    "source_alias": "production_data",
                    "filter_mappings": {
                        "DEN": ["DENSITY"],
                        "PKG_TYPE1": ["PKG1"],
                        "PKG_TYPE2": ["PKG2"],
                        "MCP_NO": ["MCPSALENO"],
                    },
                    "standard_column_aliases": {
                        "DEN": ["DENSITY"],
                        "PKG_TYPE1": ["PKG1"],
                        "PKG_TYPE2": ["PKG2"],
                        "MCP_NO": ["MCPSALENO"],
                    },
                }
            ],
        },
        "runtime_sources": {
            "production_data": [
                {
                    "TECH": "TSV",
                    "DENSITY": "2048G",
                    "MODE": "HBM3E",
                    "PKG1": "HBM",
                    "PKG2": "HBM",
                    "LEAD": "LF",
                    "MCPSALENO": "H-HBM16E",
                    "PRODUCTION": 100,
                }
            ]
        },
    }

    prompt_payload = pandas_prompt_builder.build_pandas_prompt_payload(payload)
    summary = prompt_payload["source_summary"]["production_data"]

    assert "DENSITY" not in summary["columns"]
    assert "PKG1" not in summary["columns"]
    assert "PKG2" not in summary["columns"]
    assert "MCPSALENO" not in summary["columns"]
    assert "DEN" in summary["columns"]
    assert "PKG_TYPE1" in summary["columns"]
    assert "PKG_TYPE2" in summary["columns"]
    assert "MCP_NO" in summary["columns"]
    assert summary["preview_rows"][0]["DEN"] == "2048G"
    assert summary["preview_rows"][0]["PKG_TYPE1"] == "HBM"
    assert summary["preview_rows"][0]["MCP_NO"] == "H-HBM16E"


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

    assert "raw source/filter condition column이 rank_groups" in prompt
    assert "plan의 standard analysis column name" in prompt
    assert "step_outputs라는 local dict" in prompt
    assert "rank metric을 먼저 aggregate" in prompt
    assert "각 group label 안에서 따로 rank" in prompt
    assert "step_outputs의 ranked entity key" in prompt
    assert "derived row-level output column을 먼저 계산" in prompt
    assert "empty group_by가 있는 aggregate step은 one total row" in prompt
    assert "groupby(..., as_index=False)를 사용했다면 뒤에 reset_index()를 다시 붙이지 마세요" in prompt
    assert "source별 DATE params/filters가 서로 다르면" in prompt
    assert "analysis_kind 이름만 보고 별도 로직을 만들지 말고" in prompt
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

    assert "step_plan" in prompt
    assert "analysis_kind 이름만 보고 별도 로직을 만들지 말고" in prompt
    assert "IN_TAT" in prompt
    assert "Return an empty DataFrame with no rows" not in prompt


def test_pandas_executor_keeps_successful_empty_contract_for_wip_lot_sequence() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    product_grain = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    payload = {
        "intent_plan": {
            "analysis_kind": "custom_wip_lot_sequence",
            "product_grain": product_grain,
            "analysis_output_columns": [*product_grain, "WIP", "LOT_ID", "IN_TAT"],
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
    assert result["analysis"]["row_count"] == 0
    assert result["analysis"]["columns"] == [*product_grain, "WIP", "LOT_ID", "IN_TAT"]
    assert result["analysis"]["rows"] == []
    assert result["analysis"]["used_executor_fallback"] is False
    assert "executor_fallback" not in result["analysis"]["analysis_code"]


def test_pandas_executor_keeps_successful_empty_contract_for_production_equipment_count() -> None:
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
    assert result["analysis"]["row_count"] == 0
    assert result["analysis"]["columns"] == [*product_grain, "PRODUCTION", "EQP_COUNT"]
    assert result["analysis"]["rows"] == []
    assert result["analysis"]["used_executor_fallback"] is False
    assert "executor_fallback" not in result["analysis"]["analysis_code"]


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

    assert result["analysis"]["status"] == "error"
    assert result["analysis"]["rows"] == []
    assert result["analysis"]["used_executor_fallback"] is False
    assert "Generated pandas code failed" in result["analysis"]["errors"][0]


def test_pandas_repair_builder_repairs_generated_code_error_payload() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    repair_payload_builder = load_component("langflow_components/data_analysis_flow/16a_pandas_repair_payload_builder.py")
    repair_prompt_builder = load_component("langflow_components/data_analysis_flow/16b_pandas_repair_prompt_builder.py")
    payload = {
        "request": {"question": "생산량을 MODE별로 알려줘"},
        "intent_plan": {
            "analysis_kind": "rank_top_n",
            "product_grain": ["MODE"],
            "analysis_output_columns": ["MODE", "PRODUCTION"],
            "retrieval_jobs": [{"dataset_key": "production_today", "source_alias": "production_data"}],
            "step_plan": [
                {
                    "step_id": "rank_items",
                    "operation": "rank_top_n",
                    "source_alias": "production_data",
                    "group_by": ["MODE"],
                    "metric": "PRODUCTION",
                    "top_n": 2,
                    "rank_order": "desc",
                    "output_columns": ["MODE", "PRODUCTION"],
                }
            ],
        },
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
        "code": "result_df = sources['production_data'].missing_method()",
        "output_columns": ["MODE", "PRODUCTION"],
        "reasoning_steps": ["Broken pandas call."],
    }

    failed_execution = pandas_executor.execute_pandas_from_llm(payload, json.dumps(bad_pandas_json, ensure_ascii=False))
    repair_payload = repair_payload_builder.build_pandas_repair_payload(failed_execution)
    prompt_payload = repair_prompt_builder.build_pandas_repair_prompt_payload(repair_payload)

    assert failed_execution["analysis"]["status"] == "error"
    assert failed_execution["analysis"]["used_executor_fallback"] is False
    assert "missing_method" in failed_execution["analysis"]["repairable_errors"][0]
    assert repair_payload["pandas_repair"]["required"] is True
    assert repair_payload["pandas_execution_branch"]["route"] == "repair"
    assert "missing_method" in prompt_payload["prompt"]


def test_pandas_repair_builder_builds_payload_and_prompt_on_failure() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    repair_executor = load_component("langflow_components/data_analysis_flow/17_pandas_repair_code_executor.py")
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
    assert "실패 실행 context" in prompt_payload["prompt"]
    assert "missing_alias" in prompt_payload["prompt"]
    assert "date/date-format repair에서는" in prompt_payload["prompt"]
    assert "datetime/date/timedelta를 import하지 마세요" in prompt_payload["prompt"]
    assert "pd.to_datetime(..., errors='coerce')" in prompt_payload["prompt"]
    assert "_prod_df 또는 _filtered_df처럼 underscore로 시작하는 local variable name" in prompt_payload["prompt"]
    assert "prod_df, wip_today_df, WAFER_OUT_QTY처럼 이름 안의 underscore" in prompt_payload["prompt"]

    retry_exceeded = repair_payload_builder.build_pandas_repair_payload({**failed, "pandas_retry_attempt": 1})
    retry_exceeded_prompt = repair_prompt_builder.build_pandas_repair_prompt_payload(retry_exceeded)
    retry_exceeded_passthrough = repair_executor.execute_repair_pandas_from_llm(
        retry_exceeded,
        json.dumps({"code": "result_df = pd.DataFrame([])", "output_columns": []}, ensure_ascii=False),
    )
    assert retry_exceeded["pandas_repair"]["required"] is False
    assert retry_exceeded["pandas_repair"]["route"] == "failed"
    assert retry_exceeded["pandas_execution_branch"]["route"] == "failed"
    assert retry_exceeded_prompt["prompt_type"] == "pandas_repair_skip"
    assert "result_df = pd.DataFrame([])" not in retry_exceeded_prompt["prompt"]
    assert retry_exceeded_passthrough["analysis"]["status"] == "error"
    assert retry_exceeded_passthrough["analysis"]["analysis_code"] == failed["analysis"]["analysis_code"]


def test_pandas_repair_prompt_preserves_selected_function_case_helper_call() -> None:
    repair_payload_builder = load_component("langflow_components/data_analysis_flow/16a_pandas_repair_payload_builder.py")
    repair_prompt_builder = load_component("langflow_components/data_analysis_flow/16b_pandas_repair_prompt_builder.py")
    failed = {
        "request": {"question": "오늘 512G G-777제품 생산량 알려줘"},
        "intent_plan": {
            "analysis_kind": "aggregate_total",
            "pandas_function_case": {
                "key": "component_token_product_lookup",
                "function_name": "match_product_tokens",
                "input_text": "오늘 512G G-777제품 생산량 알려줘",
            },
            "retrieval_jobs": [{"dataset_key": "production_today", "source_alias": "today_production"}],
            "step_plan": [
                {
                    "step_id": "component_token_product_lookup",
                    "operation": "apply_pandas_function_case",
                    "source_alias": "today_production",
                    "function_case_key": "component_token_product_lookup",
                    "function_name": "match_product_tokens",
                    "input_text": "오늘 512G G-777제품 생산량 알려줘",
                },
                {
                    "step_id": "aggregate_production",
                    "operation": "aggregate_sum",
                    "source_alias": "today_production",
                    "input_step_id": "component_token_product_lookup",
                    "metric": "PRODUCTION",
                },
            ],
        },
        "runtime_sources": {"today_production": [{"DEN": "512G", "MCP_NO": "G-777A2I", "PRODUCTION": 10}]},
        "analysis": {
            "status": "error",
            "analysis_code": "result_df = sources['today_production'][sources['today_production']['DEN'] == '512G']",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "errors": [
                "pandas_function_cases.component_token_product_lookup.match_product_tokens was selected but generated pandas code did not call it."
            ],
            "pandas_code_json": {
                "code": "result_df = sources['today_production'][sources['today_production']['DEN'] == '512G']",
                "output_columns": [],
            },
        },
    }

    repair_payload = repair_payload_builder.build_pandas_repair_payload(failed)
    prompt_payload = repair_prompt_builder.build_pandas_repair_prompt_payload(repair_payload)
    prompt = prompt_payload["prompt"]

    assert "함수 케이스 복구 규칙" in prompt
    assert "Specialized Functions의 의도와 helper 형태" in prompt
    assert "function_name(input_text, sources[source_alias])" in prompt
    assert "helper를 inline 정의" in prompt
    assert "plan['intent_plan'] 같은 중첩 key" in prompt
    assert "plan['intent_plan']은 존재하지 않습니다" in prompt
    assert "선택된 function case를 단순 filter로 우회하지 마세요" in prompt
    assert "downstream step의 group_by/metric/output_columns에 필요한 column이 helper output에 모두 있으면" in prompt
    assert "helper output을 key table로만 쓰고" in prompt
    assert "helper output에 없는 column으로 groupby" in prompt
    assert "반드시 매칭되어야 하는 조건 token이 source data 어느 컬럼에도 매칭되지 않으면" in prompt
    assert "groupby(..., as_index=False)를 사용했다면 뒤에 reset_index()를 다시 붙이지 마세요" in prompt
    assert "source별 DATE params/filters가 서로 다르면" in prompt
    assert "match_product_tokens" in prompt
    assert "component_token_product_lookup" in prompt


def test_pandas_repair_prompt_distinguishes_mapped_and_physical_only_columns() -> None:
    repair_payload_builder = load_component("langflow_components/data_analysis_flow/16a_pandas_repair_payload_builder.py")
    repair_prompt_builder = load_component("langflow_components/data_analysis_flow/16b_pandas_repair_prompt_builder.py")
    failed = {
        "request": {"question": "오늘 A조 DA공정에서 실적 알려줘"},
        "intent_plan": {
            "analysis_kind": "aggregate_join",
            "retrieval_jobs": [
                {
                    "dataset_key": "production_today",
                    "source_alias": "production_data",
                    "filter_mappings": {
                        "DATE": ["WORK_DATE"],
                        "PKG_TYPE1": ["PKG_TYP1"],
                    },
                    "required_param_mappings": {"DATE": ["WORK_DATE"]},
                }
            ],
        },
        "source_results": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_data",
                "columns": ["WORK_DATE", "SHIFT", "PKG_TYP1", "PRODUCTION"],
                "rows": [{"WORK_DATE": "20260622", "SHIFT": "DAY", "PKG_TYP1": "HBM", "PRODUCTION": 10}],
            }
        ],
        "analysis": {
            "status": "error",
            "analysis_code": "result_df = sources['production_data'][sources['production_data']['WORK_DATE'] == '20260622']",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "errors": ["Generated pandas code failed: 'WORK_DATE'"],
            "pandas_code_json": {
                "code": "result_df = sources['production_data'][sources['production_data']['WORK_DATE'] == '20260622']",
                "output_columns": [],
            },
        },
    }

    repair_payload = repair_payload_builder.build_pandas_repair_payload(failed)
    prompt_payload = repair_prompt_builder.build_pandas_repair_prompt_payload(repair_payload)
    prompt = prompt_payload["prompt"]

    assert "column_contract_summary" in prompt
    assert "use_standard_names_for_mapped_columns" in prompt
    assert '"DATE": [' in prompt
    assert '"WORK_DATE"' in prompt
    assert '"PKG_TYPE1": [' in prompt
    assert '"PKG_TYP1"' in prompt
    assert "physical_only_columns_allowed_by_name" in prompt
    assert '"SHIFT"' in prompt
    assert '"PRODUCTION"' in prompt
    assert "physical source column name은 standard mapping이 없고" in prompt


def test_pandas_repair_builder_detects_analysis_only_error_payload() -> None:
    repair_payload_builder = load_component("langflow_components/data_analysis_flow/16a_pandas_repair_payload_builder.py")
    repair_prompt_builder = load_component("langflow_components/data_analysis_flow/16b_pandas_repair_prompt_builder.py")
    analysis_only = {
        "status": "error",
        "analysis_code": "result_df = broken_df.to_frame().T",
        "columns": [],
        "rows": [],
        "row_count": 0,
        "errors": ["Generated pandas code failed: 'DataFrame' object has no attribute 'to_frame'"],
    }

    repair_payload = repair_payload_builder.build_pandas_repair_payload(analysis_only)
    prompt_payload = repair_prompt_builder.build_pandas_repair_prompt_payload(repair_payload)

    assert repair_payload["pandas_repair"]["required"] is True
    assert repair_payload["pandas_execution_branch"]["route"] == "repair"
    assert repair_payload["pandas_repair"]["context"]["executed_code"] == "result_df = broken_df.to_frame().T"
    assert prompt_payload["repair_required"] is True
    assert prompt_payload["prompt_type"] == "pandas_code_repair"
    assert "to_frame" in prompt_payload["prompt"]
    assert "수정 코드에서 .to_frame()을 사용하지 마세요" in prompt_payload["prompt"]


def test_pandas_repair_executor_passes_successful_payload_through_repair_branch() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    repair_executor = load_component("langflow_components/data_analysis_flow/17_pandas_repair_code_executor.py")
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
    repair_prompt_builder = load_component("langflow_components/data_analysis_flow/16b_pandas_repair_prompt_builder.py")
    skip_prompt = repair_prompt_builder.build_pandas_repair_prompt_payload(repair_payload)
    passed_through = repair_executor.execute_repair_pandas_from_llm(repair_payload, "{}")

    assert successful["analysis"]["status"] == "ok"
    assert repair_payload["pandas_repair"]["required"] is False
    assert repair_payload["pandas_execution_branch"]["route"] == "success"
    assert "result_df = pd.DataFrame([])" not in skip_prompt["prompt"]
    assert passed_through["analysis"]["rows"] == successful["analysis"]["rows"]


def test_pandas_repair_executor_can_execute_repaired_code_after_failure() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    repair_executor = load_component("langflow_components/data_analysis_flow/17_pandas_repair_code_executor.py")
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
    repaired = repair_executor.execute_repair_pandas_from_llm(
        repair_payload,
        json.dumps(fixed_pandas_json, ensure_ascii=False),
    )

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
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/21_answer_message_adapter.py")
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
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/21_answer_message_adapter.py")
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


def test_answer_message_adapter_does_not_truncate_pandas_code_block() -> None:
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/21_answer_message_adapter.py")
    long_code = "\n".join(
        [
            "step_outputs = {}",
            *[f"intermediate_{index} = {index}" for index in range(500)],
            "result_df = pd.DataFrame([{'SENTINEL_FULL_CODE_TAIL': 'kept'}])",
        ]
    )
    payload = {
        "answer_message": "Pandas 코드 확인용입니다.",
        "analysis": {
            "status": "ok",
            "safety_passed": True,
            "executed": True,
            "row_count": 1,
            "analysis_code": long_code,
        },
    }

    message = answer_message_adapter.build_playground_message(payload)

    assert "... truncated ..." not in message
    assert "SENTINEL_FULL_CODE_TAIL" in message
    assert "intermediate_499 = 499" in message


def test_answer_message_adapter_rebuilds_generic_repeated_intent_reasoning() -> None:
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/21_answer_message_adapter.py")
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
    answer_builder = load_component("langflow_components/data_analysis_flow/20_answer_response_builder.py")
    answer_message_adapter = load_component("langflow_components/data_analysis_flow/21_answer_message_adapter.py")
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
    answer_prompt_builder = load_component("langflow_components/data_analysis_flow/19_answer_prompt_builder.py")
    payload = {
        "request": {"question": "DA 생산량 top 5 알려줘"},
        "intent_plan": {"intent_type": "multi_step_analysis", "analysis_kind": "rank_top_n"},
        "analysis": {
            "columns": ["MODE", "PRODUCTION"],
            "rows": [{"MODE": "HBM3E", "PRODUCTION": 100}],
            "row_count": 1,
        },
        "runtime_sources": {"production_data": [{"MODE": "HBM3E", "PRODUCTION": 100}]},
        "state": {"current_data": {"rows": [{"MODE": "OLD"}], "row_count": 1}},
    }

    prompt_payload = answer_prompt_builder.build_answer_prompt_payload(payload)
    prompt = prompt_payload["prompt"]

    assert "Markdown table, tab-separated table" in prompt
    assert "answer_message는 narrative text만 포함" in prompt
    assert "runtime_sources" not in prompt_payload["payload"]
    assert "state" not in prompt_payload["payload"]
    assert "rows" not in prompt_payload["payload"]["analysis"]


def test_answer_prompt_treats_mapped_physical_columns_as_normalized_contract() -> None:
    answer_prompt_builder = load_component("langflow_components/data_analysis_flow/19_answer_prompt_builder.py")
    payload = {
        "request": {"question": "제품별 생산량과 재공 조인"},
        "intent_plan": {
            "intent_type": "multi_source_analysis",
            "analysis_kind": "aggregate_join",
            "product_grain": ["PKG_TYPE1", "PKG_TYPE2", "MCP_NO"],
            "retrieval_jobs": [
                {
                    "dataset_key": "production",
                    "source_alias": "production_data",
                    "filter_mappings": {"PKG_TYPE1": ["PKG1"], "PKG_TYPE2": ["PKG2"], "MCP_NO": ["MCPSALENO"]},
                    "standard_column_aliases": {"PKG_TYPE1": ["PKG1"], "PKG_TYPE2": ["PKG2"], "MCP_NO": ["MCPSALENO"]},
                }
            ],
        },
        "analysis": {
            "columns": ["PKG_TYPE1", "PKG_TYPE2", "MCP_NO", "PRODUCTION", "WIP"],
            "rows": [],
            "row_count": 0,
            "errors": ["pandas join returned no rows"],
        },
    }

    prompt_payload = answer_prompt_builder.build_answer_prompt_payload(payload)
    prompt = prompt_payload["prompt"]

    assert "컬럼명 규칙" in prompt
    assert "source가 physical name을 썼다는 이유만으로 사용자에게 metadata 수정을 요청하지 마세요" in prompt
    assert prompt_payload["answer_context"]["column_standardization"][0]["mappings"]["PKG_TYPE1"] == ["PKG1"]


def _wafer_metric_payload(question: str, product_keys: list[str]) -> dict[str, Any]:
    return {
        "request": {"question": question, "request_date": "20260622"},
        "state": {},
        "metadata": {
            "domain_items": {
                "product_key_columns": product_keys,
                "process_groups": {
                    "WB": {
                        "display_name": "WB 공정",
                        "aliases": ["WB", "W/B", "WB공정"],
                        "processes": ["W/B1", "W/B2", "W/B3", "W/B4", "W/B5", "W/B6"],
                    }
                },
                "metric_terms": {
                    "wafer_based_performance": {
                        "display_name": "Wafer 기준 실적",
                        "aliases": ["Wafer기준 실적", "Wafer기반 실적", "Wafer Out 수량", "WAFER 기준 실적"],
                        "dataset_family": "production",
                        "required_dataset_families": ["production"],
                        "required_quantity_terms": ["production"],
                        "source_columns": ["PRODUCTION", "NETDIE_300_CNT"],
                        "output_columns": ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
                        "formula": "WAFER_OUT_QTY = PRODUCTION / NETDIE_300_CNT; FAIL_UNIT_QTY = PRODUCTION when NETDIE_300_CNT <= 0",
                        "calculation_rule": "row_level_then_sum_by_requested_grain",
                        "pandas_code_instructions": (
                            "Create WAFER_OUT_QTY only where NETDIE_300_CNT > 0. "
                            "Create FAIL_UNIT_QTY from PRODUCTION where NETDIE_300_CNT is zero/null. "
                            "Then sum both output columns by the requested group_by or total."
                        ),
                    }
                },
            },
            "table_catalog": {
                "datasets": {
                    "production_today": {
                        "dataset_family": "production",
                        "source_type": "oracle",
                        "source_config": {"source_type": "oracle", "query_template": "SELECT * FROM PROD WHERE WORK_DT = {DATE}"},
                        "required_params": ["DATE"],
                        "date_format": "YYYYMMDD",
                        "date_scope": "current_day",
                        "columns": [
                            "WORK_DT",
                            "OPER_NAME",
                            "OPER_NUM",
                            *product_keys,
                            "PRODUCTION",
                            "NETDIE_300_CNT",
                        ],
                        "filter_mappings": {
                            "DATE": ["WORK_DT"],
                            "OPER_NAME": ["OPER_NAME"],
                            "OPER_NUM": ["OPER_NUM"],
                            **{column: [column] for column in product_keys},
                        },
                        "primary_quantity_column": "PRODUCTION",
                    }
                }
            },
            "main_flow_filters": {"DATE": {"field": "DATE"}, "OPER_NAME": {"field": "OPER_NAME"}},
        },
    }


def _wafer_detail_intent_json() -> dict[str, Any]:
    return {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "detail_rows",
        "datasets": ["production_today"],
        "params_by_dataset": {"production_today": {"DATE": "20260622"}},
        "retrieval_jobs": [
            {
                "dataset_key": "production_today",
                "source_alias": "production_today",
                "purpose": "retrieve production rows to calculate wafer based performance",
                "params": {"DATE": "20260622"},
                "filters": [],
                "required_columns": ["PRODUCTION"],
            }
        ],
        "step_plan": [
            {
                "step_id": "calc_wafer_out_quantity",
                "operation": "detail_rows",
                "source_alias": "production_today",
                "metric": "WAFER_OUT_QTY",
                "output_columns": ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
            }
        ],
        "reasoning_steps": ["Return the summed wafer-based production quantity (detail rows) as the result."],
    }


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


def add_test_analysis_recipes(payload: dict[str, Any], *recipe_keys: str) -> dict[str, Any]:
    recipes = payload["metadata"]["domain_items"].setdefault("analysis_recipes", {})
    for recipe_key in recipe_keys:
        recipes[recipe_key] = deepcopy(TEST_ANALYSIS_RECIPES[recipe_key])
    return payload


TEST_PRODUCT_KEYS = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]


TEST_ANALYSIS_RECIPES: dict[str, dict[str, Any]] = {
    "production_wip_target_rate": {
        "display_name": "생산 재공 목표 달성률",
        "aliases": ["생산달성율", "생산달성률", "생산량과 목표", "재공, 생산량과 목표"],
        "default_analysis_kind": "production_wip_target_rate",
        "required_dataset_families": ["production", "wip", "target"],
        "source_aliases_by_family": {
            "production": "production_data",
            "wip": "wip_data",
            "target": "target_data",
        },
        "grain_policy": "question_or_product_grain",
    },
    "low_output_vs_target": {
        "display_name": "목표 대비 생산 저조",
        "aliases": ["생산량이 부족", "목표대비 저조", "INPUT계획대비"],
        "default_analysis_kind": "low_output_vs_target",
        "required_dataset_families": ["production", "target"],
        "source_aliases_by_family": {"production": "production_data", "target": "target_data"},
        "grain_policy": "question_or_product_grain",
        "defaults": {"production_column": "PRODUCTION", "target_column": "OUT_PLAN", "input_target_column": "INPUT_PLAN", "threshold": 1.0},
    },
    "lot_quantity_summary": {
        "display_name": "LOT 수량 요약",
        "aliases": ["lot은 몇개", "wafer가 몇개", "die수량"],
        "default_analysis_kind": "lot_quantity_summary",
        "required_dataset_families": ["lot"],
        "source_aliases_by_family": {"lot": "lot_data"},
        "grain_policy": "aggregate_total",
        "required_columns_by_family": {"lot": ["LOT_ID", "WF_QTY", "SUB_PROD_QTY"]},
        "override_analysis_kinds": ["aggregate_join", "aggregate"],
    },
    "date_split_production_plan_gap": {
        "display_name": "일자 분리 생산 계획 차이",
        "aliases": ["어제 생산량과 오늘 생산계획", "차이수량"],
        "default_analysis_kind": "date_split_production_plan_gap",
        "required_dataset_families": ["production", "target"],
        "source_aliases_by_family": {"production": "production_data", "target": "target_data"},
        "grain_policy": "question_or_product_grain",
    },
    "top_wip_process_hold_lot_in_tat": {
        "display_name": "재공 상위 공정 HOLD LOT 평균 In TAT",
        "aliases": ["hold LOT", "in tat", "재공이 많은 세부공정"],
        "required_question_cues": [["hold", "HOLD"], ["tat", "TAT"]],
        "default_analysis_kind": "top_wip_process_hold_lot_in_tat",
        "required_dataset_families": ["wip", "lot"],
        "source_aliases_by_family": {"wip": "wip_data", "lot": "lot_status_data"},
        "replace_retrieval_jobs": True,
        "replace_datasets": True,
        "grain_policy": "recipe_step_grain",
        "override_analysis_kinds": ["lot_count_by_process"],
        "override_step_plan": True,
        "top_n_policy": "question_or_default",
        "defaults": {"top_n": 3},
        "blocked_filter_fields": ["LOT_HOLD_STAT_CD"],
        "output_columns": ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"],
        "required_columns_by_family": {
            "wip": ["OPER_NAME", "WIP"],
            "lot": ["OPER_SHORT_DESC", "LOT_ID", "LOT_HOLD_STAT_CD", "IN_TAT"],
        },
        "step_plan_template": [
            {
                "step_id": "rank_top_wip_process",
                "operation": "rank_top_n",
                "source_family": "wip",
                "group_by": ["OPER_NAME"],
                "metric": "WIP",
                "top_n": "$top_n",
                "rank_order": "desc",
                "output_columns": ["OPER_NAME", "WIP"],
            },
            {
                "step_id": "lot_metrics_by_process",
                "operation": "aggregate_by_group",
                "source_family": "lot",
                "filter_from_step": "rank_top_wip_process",
                "join_keys": [{"left": "OPER_SHORT_DESC", "right": "OPER_NAME"}],
                "group_by": ["OPER_SHORT_DESC"],
                "filters": [{"field": "LOT_HOLD_STAT_CD", "op": "in", "values": ["HOLD", "ONHOLD"]}],
                "metrics": [
                    {"quantity_column": "LOT_ID", "aggregation": "nunique", "output_column": "HOLD_LOT_COUNT"},
                    {"quantity_column": "IN_TAT", "aggregation": "mean", "output_column": "AVG_IN_TAT"},
                ],
                "output_columns": ["OPER_SHORT_DESC", "HOLD_LOT_COUNT", "AVG_IN_TAT"],
            },
            {
                "step_id": "join_wip_and_lot_metrics",
                "operation": "left_join",
                "left_step_id": "rank_top_wip_process",
                "right_step_id": "lot_metrics_by_process",
                "join_keys": [{"left": "OPER_NAME", "right": "OPER_SHORT_DESC"}],
                "output_columns": ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"],
            },
        ],
    },
    "top_production_products_equipment_count": {
        "display_name": "생산 상위 제품별 장비 수",
        "aliases": ["할당 장비", "장비 대수", "생산 상위"],
        "question_cues": ["생산량", "상위", "장비"],
        "default_analysis_kind": "top_production_products_equipment_count",
        "required_dataset_families": ["production", "equipment"],
        "source_aliases_by_family": {"production": "production_data", "equipment": "equipment_data"},
        "replace_datasets": True,
        "grain_policy": "question_or_product_grain",
        "override_step_plan": True,
        "top_n_policy": "question_or_default",
        "override_analysis_kinds": ["rank_top_n"],
        "required_columns_by_family": {
            "production": [*TEST_PRODUCT_KEYS, "PRODUCTION"],
            "equipment": [*TEST_PRODUCT_KEYS, "EQPID"],
        },
        "step_plan_template": [
            {
                "step_id": "rank_top_production_products",
                "operation": "rank_top_n",
                "source_family": "production",
                "group_by": TEST_PRODUCT_KEYS,
                "metric": "PRODUCTION",
                "top_n": "$top_n",
                "rank_order": "desc",
            },
            {
                "step_id": "count_equipment_for_top_products",
                "operation": "equipment_count_by_product",
                "source_family": "equipment",
                "filter_from_step": "rank_top_production_products",
                "group_by": TEST_PRODUCT_KEYS,
                "count_column": "EQPID",
            },
            {
                "step_id": "join_top_products_and_equipment",
                "operation": "left_join",
                "left_step_id": "rank_top_production_products",
                "right_step_id": "count_equipment_for_top_products",
                "join_keys": TEST_PRODUCT_KEYS,
            },
        ],
    },
    "top_wip_product_oldest_lot": {
        "display_name": "재공 최다 제품 기준 최장 In TAT LOT",
        "aliases": ["재공이 가장 많은 제품", "IN TAT가 가장 오래된 LOT"],
        "default_analysis_kind": "top_wip_product_oldest_lot",
        "required_dataset_families": ["wip", "lot"],
        "source_aliases_by_family": {"wip": "wip_data", "lot": "lot_data"},
        "replace_datasets": True,
        "grain_policy": "question_or_product_grain",
        "override_step_plan": True,
        "output_columns": [*TEST_PRODUCT_KEYS, "WIP", "LOT_ID", "IN_TAT"],
        "required_columns_by_family": {
            "wip": [*TEST_PRODUCT_KEYS, "WIP"],
            "lot": [*TEST_PRODUCT_KEYS, "LOT_ID", "IN_TAT"],
        },
        "step_plan_template": [
            {
                "step_id": "rank_top_wip_product",
                "operation": "rank_top_n",
                "source_family": "wip",
                "group_by": TEST_PRODUCT_KEYS,
                "metric": "WIP",
                "top_n": 1,
                "rank_order": "desc",
            },
            {
                "step_id": "find_oldest_lot_for_top_product",
                "operation": "rank_top_n",
                "source_family": "lot",
                "filter_from_step": "rank_top_wip_product",
                "group_by": TEST_PRODUCT_KEYS,
                "metric": "IN_TAT",
                "top_n": 1,
                "rank_order": "desc",
            },
            {
                "step_id": "join_top_product_and_oldest_lot",
                "operation": "left_join",
                "left_step_id": "rank_top_wip_product",
                "right_step_id": "find_oldest_lot_for_top_product",
                "join_keys": TEST_PRODUCT_KEYS,
                "output_columns": [*TEST_PRODUCT_KEYS, "WIP", "LOT_ID", "IN_TAT"],
            },
        ],
    },
}


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
