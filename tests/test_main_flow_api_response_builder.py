from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_component(path: str):
    component_path = ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_main_flow_api_response_builder_projects_current_payload() -> None:
    builder = load_component("langflow_components/data_analysis_flow/21_api_response_builder.py")
    payload = {
        "status": "ok",
        "answer_message": "오늘 전체 재공은 30입니다.",
        "data": {
            "columns": ["PRODUCT", "WIP"],
            "rows": [{"PRODUCT": "A", "WIP": 30}],
            "row_count": 10,
            "data_ref": {"store": "mongodb", "collection_name": "agent_v3_result_store", "ref_id": "result-1"},
            "data_is_preview": True,
        },
        "applied_scope": {
            "intent_type": "single_source_analysis",
            "analysis_kind": "aggregate_wip_total",
            "datasets": ["wip_today"],
            "source_aliases": ["wip_total"],
        },
        "intent_plan": {
            "route": "single_retrieval",
            "intent_type": "single_source_analysis",
            "analysis_kind": "aggregate_wip_total",
            "step_plan": [{"step_id": "aggregate"}],
        },
        "analysis": {
            "status": "ok",
            "safety_passed": True,
            "executed": True,
            "row_count": 10,
            "columns": ["PRODUCT", "WIP"],
            "analysis_code": "result_df = df.groupby('PRODUCT').sum()",
            "errors": [],
        },
        "state": {"current_data": {"data_ref": {"ref_id": "result-1", "collection_name": "agent_v3_result_store"}}},
        "runtime_sources": {"wip_total": [{"PRODUCT": "A", "WIP": 30}]},
    }

    result = builder.build_main_flow_api_response(payload)
    api_response = result["api_response"]

    assert api_response["answer_message"] == "오늘 전체 재공은 30입니다."
    assert api_response["data"]["row_count"] == 10
    assert api_response["data"]["rows"] == [{"PRODUCT": "A", "WIP": 30}]
    assert api_response["intent"]["datasets"] == ["wip_today"]
    assert api_response["analysis"]["analysis_code"].startswith("result_df")
    assert api_response["data_refs"][0]["ref_id"] == "result-1"
    assert api_response["developer"]["analysis_code"].startswith("result_df")
    assert "debug" not in api_response
    assert "runtime_sources" not in json.dumps(api_response, ensure_ascii=False)


def test_main_flow_api_response_builder_normalizes_memory_data_ref() -> None:
    builder = load_component("langflow_components/data_analysis_flow/21_api_response_builder.py")

    result = builder.build_main_flow_api_response(
        {
            "answer_message": "ok",
            "data": {"rows": [], "columns": [], "row_count": 0, "data_ref": "memory://session/current_data"},
            "analysis": {},
        }
    )["api_response"]

    assert result["data"]["data_ref"] == {"store": "memory", "ref_id": "memory://session/current_data"}


def test_main_flow_api_response_builder_prefers_analysis_rows_over_stale_data() -> None:
    builder = load_component("langflow_components/data_analysis_flow/21_api_response_builder.py")

    result = builder.build_main_flow_api_response(
        {
            "answer_message": "ok",
            "data": {
                "columns": ["OPER_NAME", "PRODUCTION"],
                "rows": [{"OPER_NAME": "W/B1", "PRODUCTION": 100}],
                "row_count": 1,
                "data_ref": {"store": "mongodb", "ref_id": "source-ref", "collection_name": "agent_v3_result_store"},
            },
            "analysis": {
                "status": "ok",
                "columns": ["OPER_GROUP", "WIP", "TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "PRODUCTION"],
                "rows": [
                    {
                        "OPER_GROUP": "DA",
                        "WIP": 40,
                        "TECH": "TSV",
                        "DEN": "2048G",
                        "MODE": "HBM3E",
                        "PKG_TYPE1": "HBM",
                        "PKG_TYPE2": "HBM",
                        "LEAD": "LF",
                        "MCP_NO": "H-HBM16E",
                        "PRODUCTION": 100,
                    }
                ],
                "row_count": 1,
                "data_ref": {"store": "mongodb", "ref_id": "result-ref", "collection_name": "agent_v3_result_store"},
            },
        }
    )["api_response"]

    assert result["data"]["columns"][0:2] == ["OPER_GROUP", "WIP"]
    assert result["data"]["rows"][0]["WIP"] == 40
    assert result["data"]["data_ref"]["ref_id"] == "result-ref"


def test_main_flow_api_response_builder_does_not_show_source_rows_as_analysis_rows() -> None:
    builder = load_component("langflow_components/data_analysis_flow/21_api_response_builder.py")

    result = builder.build_main_flow_api_response(
        {
            "answer_message": "ok",
            "data": {
                "columns": ["OPER_NAME", "PRODUCTION"],
                "rows": [{"OPER_NAME": "W/B1", "PRODUCTION": 100}],
                "row_count": 1,
            },
            "analysis": {
                "status": "ok",
                "safety_passed": True,
                "executed": True,
                "analysis_code": "result_df = pd.DataFrame([{'OPER_GROUP': 'WB', 'WIP': 100000.0}])",
            },
        }
    )["api_response"]

    assert result["data"]["columns"] == ["OPER_NAME", "PRODUCTION"]
    assert result["analysis"]["analysis_code"].startswith("result_df")
    assert "columns" not in result["analysis"]
    assert "rows" not in result["analysis"]
    assert "row_count" not in result["analysis"]


def test_main_flow_api_response_builder_collects_state_followup_source_refs() -> None:
    builder = load_component("langflow_components/data_analysis_flow/21_api_response_builder.py")
    source_ref = {
        "store": "mongodb",
        "ref_id": "source-ref",
        "collection_name": "agent_v3_result_store",
    }

    result = builder.build_main_flow_api_response(
        {
            "answer_message": "ok",
            "data": {"rows": [], "columns": [], "row_count": 0, "data_ref": {}},
            "analysis": {},
            "state": {
                "followup_source_results": [
                    {
                        "source_alias": "wip_data",
                        "dataset_key": "wip_today",
                        "data_ref": source_ref,
                    }
                ],
                "runtime_source_refs": {"wip_data": source_ref},
            },
        }
    )["api_response"]

    assert [ref["ref_id"] for ref in result["data_refs"]] == ["source-ref"]
    assert result["data_refs"][0]["source_alias"] == "wip_data"
    assert result["data_refs"][0]["dataset_key"] == "wip_today"


def test_main_flow_api_response_builder_preserves_metadata_qa_contract() -> None:
    builder = load_component("langflow_components/data_analysis_flow/21_api_response_builder.py")

    result = builder.build_main_flow_api_response(
        {
            "status": "ok",
            "direct_response_ready": True,
            "answer_message": "현재 등록된 조회 가능 데이터는 8개입니다.",
            "metadata_route": {"route": "metadata_qa", "metadata_action": "catalog_list", "confidence": "high"},
            "metadata_qa": {"handled": True, "route": "metadata_qa", "metadata_action": "catalog_list"},
            "intent_plan": {"route": "metadata_qa", "intent_type": "metadata_lookup", "analysis_kind": "catalog_list", "metadata_action": "catalog_list"},
            "applied_scope": {"intent_type": "metadata_lookup", "analysis_kind": "catalog_list", "datasets": ["production_today"]},
            "data": {"columns": ["DATASET_KEY"], "rows": [{"DATASET_KEY": "production_today"}], "row_count": 1, "data_ref": {}},
            "analysis": {"status": "ok", "executed": False, "row_count": 1, "columns": ["DATASET_KEY"], "rows": [{"DATASET_KEY": "production_today"}]},
        }
    )["api_response"]

    assert result["response_type"] == "metadata_qa"
    assert result["direct_response_ready"] is True
    assert result["metadata_qa"]["metadata_action"] == "catalog_list"
    assert result["metadata_route"]["confidence"] == "high"
    assert result["intent"]["metadata_action"] == "catalog_list"
