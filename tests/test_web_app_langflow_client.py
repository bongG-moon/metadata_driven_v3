from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import requests

from web_app.langflow_client import (
    LangflowApiClient,
    LangflowSettings,
    build_authoring_node_input_settings,
    normalize_authoring_response,
    normalize_query_response,
    normalize_route_response,
)


ROOT = Path(__file__).resolve().parents[1]


def test_normalize_query_response_accepts_current_api_response_shape() -> None:
    raw = {
        "outputs": [
            {
                "results": {
                    "api_response": {
                        "data": {
                            "api_response": {
                                "status": "ok",
                                "answer_message": "현재 DA 재공 상위 제품입니다.",
                                "data": {
                                    "columns": ["PRODUCT", "WIP"],
                                    "rows": [{"PRODUCT": "A", "WIP": 50}],
                                    "row_count": 5,
                                    "data_ref": {"store": "mongodb", "ref_id": "result-1"},
                                },
                                "applied_scope": {"datasets": ["wip_today"]},
                                "intent": {"intent_type": "single_source_analysis"},
                                "analysis": {"analysis_code": "result_df = df.head()"},
                                "state": {"current_data": {"data_ref": {"ref_id": "result-1"}}},
                            }
                        }
                    }
                }
            }
        ]
    }

    result = normalize_query_response(raw)

    assert result["answer_message"] == "현재 DA 재공 상위 제품입니다."
    assert result["data"]["rows"][0]["PRODUCT"] == "A"
    assert result["data"]["row_count"] == 5
    assert result["applied_scope"]["datasets"] == ["wip_today"]
    assert result["analysis"]["analysis_code"] == "result_df = df.head()"
    assert result["state"]["current_data"]["data_ref"]["ref_id"] == "result-1"


def test_normalize_query_response_accepts_legacy_flat_api_response_shape() -> None:
    raw = {
        "api_response": {
            "response": "legacy answer",
            "data": [{"PRODUCT": "A", "WIP": 50}],
            "columns": ["PRODUCT", "WIP"],
            "row_count": 1,
            "data_ref": {"ref_id": "legacy-1"},
            "applied_scope": {"datasets": ["wip_today"]},
            "debug": {"analysis_code": "legacy_code()"},
        }
    }

    result = normalize_query_response(raw)

    assert result["answer_message"] == "legacy answer"
    assert result["data"]["rows"] == [{"PRODUCT": "A", "WIP": 50}]
    assert result["data"]["data_ref"]["ref_id"] == "legacy-1"
    assert result["analysis"]["analysis_code"] == "legacy_code()"


def test_normalize_query_response_collects_router_side_developer_payload() -> None:
    raw = {
        "api_response": {
            "status": "ok",
            "answer_message": "analysis answer",
            "data": {
                "columns": ["PRODUCT", "WIP"],
                "rows": [{"PRODUCT": "A", "WIP": 50}],
                "row_count": 1,
            },
        },
        "debug": {
            "data_preparation_code": "sources = normalize_sources(raw_sources)",
            "failed_analysis_code": "result_df = broken",
            "analysis_code": "result_df = fixed",
            "prepared_dataframe": {
                "columns": ["PRODUCT", "WIP"],
                "row_count": 1,
                "preview_rows": [{"PRODUCT": "A", "WIP": 50}],
            },
            "pandas_execution_status": {"status": "ok"},
            "source_summaries": [{"source_alias": "wip_data", "row_count": 10}],
            "data_refs": [{"ref_id": "source-ref", "collection_name": "agent_v3_result_store"}],
        },
    }

    result = normalize_query_response(raw)

    assert result["answer_message"] == "analysis answer"
    assert result["developer"]["data_preparation_code"] == "sources = normalize_sources(raw_sources)"
    assert result["developer"]["failed_analysis_code"] == "result_df = broken"
    assert result["developer"]["analysis_code"] == "result_df = fixed"
    assert result["developer"]["prepared_dataframe"]["preview_rows"][0]["PRODUCT"] == "A"
    assert result["analysis"]["analysis_code"] == "result_df = fixed"
    assert result["data_refs"][0]["ref_id"] == "source-ref"


def test_normalize_query_response_collects_state_followup_refs() -> None:
    result = normalize_query_response(
        {
            "api_response": {
                "answer_message": "ok",
                "data": {"rows": [], "columns": [], "row_count": 0, "data_ref": {}},
                "state": {
                    "followup_source_results": [
                        {
                            "source_alias": "wip_data",
                            "data_ref": {
                                "store": "mongodb",
                                "ref_id": "source-ref",
                                "collection_name": "agent_v3_result_store",
                            },
                        }
                    ]
                },
            }
        }
    )

    assert result["data_refs"][0]["ref_id"] == "source-ref"


def test_normalize_query_response_preserves_metadata_qa_shape() -> None:
    result = normalize_query_response(
        {
            "api_response": {
                "status": "ok",
                "response_type": "metadata_qa",
                "direct_response_ready": True,
                "answer_message": "현재 등록된 조회 가능 데이터는 8개입니다.",
                "metadata_route": {"route": "metadata_qa", "metadata_action": "catalog_list"},
                "metadata_qa": {"handled": True, "metadata_action": "catalog_list"},
                "intent_plan": {"route": "metadata_qa", "analysis_kind": "catalog_list"},
                "applied_scope": {"intent_type": "metadata_lookup", "analysis_kind": "catalog_list", "datasets": ["production_today"]},
                "data": {"columns": ["DATASET_KEY"], "rows": [{"DATASET_KEY": "production_today"}], "row_count": 1, "data_ref": {}},
                "analysis": {"status": "ok", "executed": False},
            }
        }
    )

    assert result["response_type"] == "metadata_qa"
    assert result["direct_response_ready"] is True
    assert result["metadata_qa"]["metadata_action"] == "catalog_list"
    assert result["metadata_route"]["route"] == "metadata_qa"
    assert result["data"]["rows"][0]["DATASET_KEY"] == "production_today"


def test_normalize_query_response_accepts_chat_output_message_only() -> None:
    result = normalize_query_response(
        {
            "outputs": [
                {
                    "outputs": [
                        {
                            "results": {
                                "message": {
                                    "data": {
                                        "text": "현재 조회 가능한 데이터는 production_today와 wip_today입니다.",
                                    }
                                }
                            }
                        }
                    ]
                }
            ]
        }
    )

    assert result["answer_message"] == "현재 조회 가능한 데이터는 production_today와 wip_today입니다."
    assert result["message_only"] is True
    assert result["response_type"] == "message"


def test_normalize_authoring_response_accepts_current_trace_dict() -> None:
    result = normalize_authoring_response(
        {
            "api_response": {
                "status": "skipped",
                "message": "비슷한 기존 정보가 있습니다.",
                "metadata_type": "domain",
                "items": [{"section": "quantity_terms", "key": "lot_count"}],
                "existing_matches": [{"existing_key": "lot_count"}],
                "review": {"ready_to_save": False, "supplement_requests": []},
                "write_result": {"status": "skipped", "saved_count": 0},
                "trace": {
                    "raw_text": "Lot 수량",
                    "refined_text": "Lot 수량은 LOT_ID nunique",
                    "duplicate_decision": {"action": "ask", "requires_user_choice": True},
                },
            }
        }
    )

    assert result["metadata_type"] == "domain"
    assert result["ui_status"] == "duplicate_choice_required"
    assert result["trace"]["refined_text"] == "Lot 수량은 LOT_ID nunique"


def test_normalize_authoring_response_accepts_message_only() -> None:
    result = normalize_authoring_response(
        {
            "outputs": [
                {
                    "outputs": [
                        {
                            "results": {
                                "message": {
                                    "data": {
                                        "text": "메타데이터 등록 결과를 확인했습니다.",
                                    }
                                }
                            }
                        }
                    ]
                }
            ]
        }
    )

    assert result["message"] == "메타데이터 등록 결과를 확인했습니다."


def test_normalize_authoring_response_accepts_legacy_trace_list() -> None:
    result = normalize_authoring_response(
        {
            "api_response": {
                "flow_type": "table_catalog",
                "status": "saved",
                "items": [{"dataset_key": "wip_today"}],
                "review_result": {"ready_to_save": True, "supplement_requests": []},
                "write_result": {"success": True, "saved_count": 1},
                "trace": [
                    {"stage": "input", "raw_text": "wip_today"},
                    {"stage": "refinement", "refined_text": "wip_today dataset"},
                ],
            }
        }
    )

    assert result["metadata_type"] == "table_catalog"
    assert result["ui_status"] == "saved"
    assert result["trace"]["raw_text"] == "wip_today"
    assert result["trace"]["stages"][1]["refined_text"] == "wip_today dataset"


def test_env_example_contains_langflow_web_api_settings() -> None:
    keys = {
        line.split("=", 1)[0].strip()
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }

    assert {
        "LANGFLOW_BASE_URL",
        "LANGFLOW_API_KEY",
        "LANGFLOW_INPUT_TYPE",
        "LANGFLOW_OUTPUT_TYPE",
        "LANGFLOW_TIMEOUT_SECONDS",
        "LANGFLOW_ROUTER_FLOW_ID",
        "LANGFLOW_ROUTER_API_URL",
        "LANGFLOW_METADATA_QA_FLOW_ID",
        "LANGFLOW_METADATA_QA_API_URL",
        "LANGFLOW_DATA_ANALYSIS_FLOW_ID",
        "LANGFLOW_DATA_ANALYSIS_API_URL",
        "LANGFLOW_REPORT_GENERATION_FLOW_ID",
        "LANGFLOW_REPORT_GENERATION_API_URL",
        "LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID",
        "LANGFLOW_OPERATIONS_DIAGNOSIS_API_URL",
        "LANGFLOW_DOMAIN_AUTHORING_FLOW_ID",
        "LANGFLOW_DOMAIN_AUTHORING_API_URL",
        "LANGFLOW_TABLE_CATALOG_AUTHORING_FLOW_ID",
        "LANGFLOW_TABLE_CATALOG_AUTHORING_API_URL",
        "LANGFLOW_MAIN_FILTER_AUTHORING_FLOW_ID",
        "LANGFLOW_MAIN_FILTER_AUTHORING_API_URL",
        "RUN_LANGFLOW_API_VALIDATION",
    } <= keys


def test_langflow_settings_builds_urls_from_base_url_and_flow_ids(tmp_path, monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("LANGFLOW_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANGFLOW_BASE_URL", "http://127.0.0.1:7860")
    monkeypatch.setenv("LANGFLOW_ROUTER_FLOW_ID", "router-id")
    monkeypatch.setenv("LANGFLOW_METADATA_QA_FLOW_ID", "metadata-id")
    monkeypatch.setenv("LANGFLOW_DATA_ANALYSIS_FLOW_ID", "analysis-id")
    monkeypatch.setenv("LANGFLOW_REPORT_GENERATION_FLOW_ID", "report-id")
    monkeypatch.setenv("LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID", "diagnosis-id")
    monkeypatch.setenv("LANGFLOW_DOMAIN_AUTHORING_FLOW_ID", "domain-id")
    monkeypatch.setenv("LANGFLOW_TABLE_CATALOG_AUTHORING_FLOW_ID", "table-id")
    monkeypatch.setenv("LANGFLOW_MAIN_FILTER_AUTHORING_FLOW_ID", "filter-id")

    settings = LangflowSettings.from_env()

    assert settings.router_api_url == "http://127.0.0.1:7860/api/v1/run/router-id"
    assert settings.metadata_qa_api_url == "http://127.0.0.1:7860/api/v1/run/metadata-id"
    assert settings.data_analysis_api_url == "http://127.0.0.1:7860/api/v1/run/analysis-id"
    assert settings.report_generation_api_url == "http://127.0.0.1:7860/api/v1/run/report-id"
    assert settings.operations_diagnosis_api_url == "http://127.0.0.1:7860/api/v1/run/diagnosis-id"
    assert settings.domain_authoring_api_url == "http://127.0.0.1:7860/api/v1/run/domain-id"
    assert settings.table_catalog_authoring_api_url == "http://127.0.0.1:7860/api/v1/run/table-id"
    assert settings.main_flow_filter_authoring_api_url == "http://127.0.0.1:7860/api/v1/run/filter-id"


def test_langflow_settings_loads_local_env_file(tmp_path, monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("LANGFLOW_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LANGFLOW_BASE_URL=http://127.0.0.1:7860",
                "LANGFLOW_ROUTER_FLOW_ID=router-from-env-file",
                "LANGFLOW_METADATA_QA_API_URL='http://127.0.0.1:7860/api/v1/run/metadata-from-env-file'",
            ]
        ),
        encoding="utf-8",
    )

    settings = LangflowSettings.from_env()

    assert settings.router_api_url == "http://127.0.0.1:7860/api/v1/run/router-from-env-file"
    assert settings.metadata_qa_api_url == "http://127.0.0.1:7860/api/v1/run/metadata-from-env-file"


def test_langflow_client_uses_router_executed_result_without_second_api_call(monkeypatch) -> None:
    calls: list[str] = []

    def fake_call_langflow_api(*args, **kwargs) -> dict:
        calls.append(args[0])
        return {
            "outputs": [
                {
                    "outputs": [
                        {
                            "results": {
                                "api_response": {
                                    "data": {
                                        "status": "ok",
                                        "selected_flow": "metadata_qa_flow",
                                        "message": "metadata answer",
                                        "raw_response": {
                                            "api_response": {
                                                "status": "ok",
                                                "response_type": "metadata_qa",
                                                "direct_response_ready": True,
                                                "answer_message": "metadata answer",
                                                "metadata_qa": {"handled": True},
                                                "data": {"columns": [], "rows": [], "row_count": 0, "data_ref": {}},
                                                "state": {"current_data": {"row_count": 0}},
                                            }
                                        },
                                    }
                                }
                            }
                        }
                    ]
                }
            ]
        }

    monkeypatch.setattr("web_app.langflow_client.call_langflow_api", fake_call_langflow_api)
    client = LangflowApiClient(
        LangflowSettings(
            router_api_url="http://fake-router",
            metadata_qa_api_url="http://fake-metadata-qa",
        )
    )

    result = client.run_orchestrated_query("등록된 데이터 알려줘", "s1", {})

    assert calls == ["http://fake-router"]
    assert result["api_mode"] == "langflow_router_only"
    assert result["answer_message"] == "metadata answer"
    assert result["selected_flow"] == "metadata_qa_flow"
    assert result["route_decision"]["route"] == "metadata_qa"


def test_orchestrated_metadata_qa_message_only_is_marked_direct_response(monkeypatch) -> None:
    calls: list[str] = []

    def fake_call_langflow_api(*args, **kwargs) -> dict:
        calls.append(args[0])
        return {
            "status": "ok",
            "selected_flow": "metadata_qa_flow",
            "message": "등록된 데이터 목록을 안내합니다.",
            "raw_response": {
                "outputs": [
                    {
                        "outputs": [
                            {
                                "results": {
                                    "message": {
                                        "data": {
                                            "text": "등록된 데이터 목록을 안내합니다.",
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            },
        }

    monkeypatch.setattr("web_app.langflow_client.call_langflow_api", fake_call_langflow_api)
    client = LangflowApiClient(
        LangflowSettings(
            router_api_url="http://fake-router",
            metadata_qa_api_url="http://fake-metadata-qa",
        )
    )

    result = client.run_orchestrated_query("등록된 데이터 알려줘", "s1", {})

    assert calls == ["http://fake-router"]
    assert result["answer_message"] == "등록된 데이터 목록을 안내합니다."
    assert result["message_only"] is True
    assert result["response_type"] == "metadata_qa"
    assert result["direct_response_ready"] is True


def test_langflow_client_explains_router_timeout(monkeypatch) -> None:
    def fake_call_langflow_api(*args, **kwargs) -> dict:
        raise requests.exceptions.ReadTimeout("read timed out")

    monkeypatch.setattr("web_app.langflow_client.call_langflow_api", fake_call_langflow_api)
    client = LangflowApiClient(LangflowSettings(router_api_url="http://fake-router"))

    with pytest.raises(TimeoutError) as error:
        client.run_orchestrated_query("질문", "s1", {})

    assert "calls only the router flow" in str(error.value)
    assert "Selected Flow API Runner" in str(error.value)


def test_normalize_route_response_infers_route_from_selected_flow() -> None:
    result = normalize_route_response({"status": "ok", "selected_flow": "operations_diagnosis_flow"})

    assert result["route"] == "operations_diagnosis"
    assert result["selected_flow"] == "operations_diagnosis_flow"


def test_authoring_settings_do_not_override_flow_duplicate_action(monkeypatch) -> None:
    monkeypatch.delenv("MONGODB_DOMAIN_COLLECTION", raising=False)
    monkeypatch.delenv("MONGODB_TABLE_CATALOG_COLLECTION", raising=False)
    monkeypatch.delenv("MONGODB_MAIN_FLOW_FILTER_COLLECTION", raising=False)

    expected = {
        "domain": (
            "00 Domain Authoring Request Loader",
            "05 Domain Similarity Checker",
            "07 Domain Review Writer",
            "agent_v3_domain_items",
        ),
        "table_catalog": (
            "00 Table Catalog Authoring Request Loader",
            "05 Table Catalog Similarity Checker",
            "07 Table Catalog Review Writer",
            "agent_v3_table_catalog_items",
        ),
        "main_flow_filter": (
            "00 Main Flow Filter Authoring Request Loader",
            "05 Main Flow Filter Similarity Checker",
            "07 Main Flow Filter Review Writer",
            "agent_v3_main_flow_filters",
        ),
    }

    for metadata_type, (request_loader, similarity_checker, writer, collection_name) in expected.items():
        settings = build_authoring_node_input_settings(metadata_type)

        assert "duplicate_action" not in settings.get(request_loader, {})
        assert "duplicate_action" not in settings.get(similarity_checker, {})
        assert settings[writer] == {"collection_name": collection_name}
