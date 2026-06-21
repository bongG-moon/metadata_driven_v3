from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from web_app.langflow_client import build_split_flow_tweaks, normalize_route_response


ROOT = Path(__file__).resolve().parents[1]


def load_component(path: str):
    component_path = ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_split_flow_folders_have_expected_numbered_files() -> None:
    expected = {
        "router_flow": [
            "00_router_request_loader.py",
            "01_metadata_context_loader.py",
            "02_route_candidate_builder.py",
            "03_route_classifier_prompt_builder.py",
            "04_route_classifier_normalizer.py",
            "05_orchestrator_response_builder.py",
            "06_run_flow_handoff_builder.py",
            "07_selected_run_flow_response_merger.py",
        ],
        "metadata_qa_flow": [
            "00_metadata_qa_request_loader.py",
            "01_metadata_context_loader.py",
            "02_metadata_qa_response_builder.py",
            "03_metadata_qa_message_adapter.py",
            "04_metadata_qa_api_response_builder.py",
        ],
        "data_analysis_flow": [
            "00_analysis_request_loader.py",
            "01_metadata_context_loader.py",
            "02_intent_prompt_builder.py",
            "03_intent_plan_normalizer.py",
            "04_previous_result_restore_router.py",
            "05_mongodb_data_loader.py",
            "06_previous_result_restore_merger.py",
            "07_dummy_data_retriever.py",
            "08_oracle_query_retriever.py",
            "09_h_api_retriever.py",
            "10_datalake_retriever.py",
            "11_goodocs_retriever.py",
            "12_source_retrieval_merger.py",
            "13_retrieval_payload_adapter.py",
            "14_pandas_prompt_builder.py",
            "15_pandas_code_executor.py",
            "16a_pandas_repair_payload_builder.py",
            "16b_pandas_repair_prompt_builder.py",
            "17_mongodb_data_store.py",
            "18_answer_prompt_builder.py",
            "19_answer_response_builder.py",
            "20_answer_message_adapter.py",
            "21_api_response_builder.py",
        ],
        "report_generation_flow": [
            "00_report_request_loader.py",
            "01_report_outline_builder.py",
            "02_report_data_selector.py",
            "03_report_response_builder.py",
        ],
        "operations_diagnosis_flow": [
            "00_diagnosis_request_loader.py",
            "01_diagnosis_signal_collector.py",
            "02_diagnosis_rule_evaluator.py",
            "03_diagnosis_response_builder.py",
        ],
        "session_state_flow": [
            "00_mongodb_session_state_loader.py",
            "01_mongodb_session_state_writer.py",
        ],
    }
    for folder, files in expected.items():
        actual = [path.name for path in sorted((ROOT / "langflow_components" / folder).glob("*.py"))]
        assert actual == files


def test_router_flow_maps_routes_to_selected_subflows() -> None:
    normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    orchestrator = load_component("langflow_components/router_flow/05_orchestrator_response_builder.py")
    payload = {
        "request": {"question": "make an operations diagnosis", "session_id": "s1"},
        "state": {"current_data": {"columns": ["WIP"], "rows": [{"WIP": 10}], "row_count": 1}},
        "metadata_route": {"route": "data_analysis", "route_llm_required": True},
    }

    for route, selected_flow in {
        "metadata_qa": "metadata_qa_flow",
        "data_analysis": "data_analysis_flow",
        "report_generation": "report_generation_flow",
        "operations_diagnosis": "operations_diagnosis_flow",
    }.items():
        classified = normalizer.normalize_route_classifier_payload(
            payload,
            json.dumps({"route": route, "metadata_action": "catalog_list" if route == "metadata_qa" else "", "confidence": "high"}),
        )
        response = orchestrator.build_orchestrator_response(classified)
        assert response["selected_flow"] == selected_flow
        assert response["flow_inputs"]["question"] == "make an operations diagnosis"
        assert response["flow_inputs"]["state"]["current_data"]["row_count"] == 1


def test_metadata_qa_loader_accepts_router_route_payload() -> None:
    loader = load_component("langflow_components/metadata_qa_flow/00_metadata_qa_request_loader.py")
    route_payload = {
        "selected_flow": "metadata_qa_flow",
        "flow_inputs": {
            "session_id": "s1",
            "metadata_route": {"route": "metadata_qa", "metadata_action": "dataset_query", "target_dataset": "production_today"},
            "metadata": {"table_catalog": {"datasets": {"production_today": {"display_name": "Production Today"}}}},
        },
    }

    result = loader.build_metadata_qa_request(
        "show production query",
        "s1",
        state={"current_data": {"row_count": 2}},
        router_payload=route_payload,
    )

    assert result["metadata_route"]["metadata_action"] == "dataset_query"
    assert result["metadata_route"]["target_dataset"] == "production_today"
    assert result["metadata"]["table_catalog"]["datasets"]["production_today"]["display_name"] == "Production Today"
    assert result["request"]["session_id"] == "s1"
    assert result["state"]["current_data"]["row_count"] == 2


def test_request_loaders_inherit_session_id_from_state_or_router_payload() -> None:
    router_loader = load_component("langflow_components/router_flow/00_router_request_loader.py")
    analysis_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/metadata_qa_flow/00_metadata_qa_request_loader.py")
    report_loader = load_component("langflow_components/report_generation_flow/00_report_request_loader.py")
    diagnosis_loader = load_component("langflow_components/operations_diagnosis_flow/00_diagnosis_request_loader.py")
    session_loader = load_component("langflow_components/session_state_flow/00_mongodb_session_state_loader.py")
    orchestrator = load_component("langflow_components/router_flow/05_orchestrator_response_builder.py")

    state = {"session_id": "conversation-123", "current_data": {"row_count": 1}}

    router_payload = router_loader.build_request_payload("질문", "", state)
    assert router_payload["request"]["session_id"] == "conversation-123"

    route_response = orchestrator.build_orchestrator_response(
        {
            "request": {"question": "질문"},
            "state": state,
            "metadata_route": {"route": "metadata_qa", "metadata_action": "catalog_list"},
        }
    )
    assert route_response["flow_inputs"]["session_id"] == "conversation-123"

    assert analysis_loader.build_request_payload("질문", "", state)["request"]["session_id"] == "conversation-123"
    assert (
        metadata_loader.build_metadata_qa_request("질문", "", router_payload=route_response)["request"]["session_id"]
        == "conversation-123"
    )
    assert report_loader.build_report_request("질문", "", router_payload=route_response)["request"]["session_id"] == "conversation-123"
    assert (
        diagnosis_loader.build_diagnosis_request("질문", "", router_payload=route_response)["request"]["session_id"]
        == "conversation-123"
    )
    assert (
        session_loader.load_session_state_payload("질문", "", state=state, enabled="false")["request"]["session_id"]
        == "conversation-123"
    )


def test_previous_result_restore_router_and_merger_skip_loader_for_summary_mode() -> None:
    router = load_component("langflow_components/data_analysis_flow/04_previous_result_restore_router.py")
    merger = load_component("langflow_components/data_analysis_flow/06_previous_result_restore_merger.py")
    payload = {
        "intent_plan": {"analysis_kind": "equipment_count"},
        "state": {
            "current_data": {
                "data_ref": {"store": "mongodb", "ref_id": "r1"},
                "columns": ["MODE"],
                "rows": [{"MODE": "A"}],
                "row_count": 100,
            }
        },
    }

    routed = router.route_previous_result_restore(payload)
    merged = merger.merge_previous_result_restore(routed["payload"])

    assert routed["restore_decision"]["required"] is False
    assert routed["restore_decision"]["branch"] == "skip_restore"
    assert merged["previous_result_restore"]["used_loader_payload"] is False
    assert merged["state"]["current_data"]["rows"] == [{"MODE": "A"}]


def test_previous_result_restore_router_and_merger_use_loader_for_full_mode() -> None:
    router = load_component("langflow_components/data_analysis_flow/04_previous_result_restore_router.py")
    merger = load_component("langflow_components/data_analysis_flow/06_previous_result_restore_merger.py")
    payload = {
        "intent_plan": {"requires_full_previous_result_restore": True},
        "state": {"current_data": {"data_ref": {"store": "mongodb", "ref_id": "r1"}, "rows": [{"MODE": "A"}], "row_count": 100}},
    }

    routed = router.route_previous_result_restore(payload)
    restored_payload = {
        **routed["restore_payload"],
        "state": {"current_data": {"data_ref": {"store": "mongodb", "ref_id": "r1"}, "rows": [{"MODE": "A"}, {"MODE": "B"}], "row_count": 2}},
    }
    merged = merger.merge_previous_result_restore(routed["payload"], restored_payload)

    assert routed["restore_decision"]["required"] is True
    assert routed["restore_payload"]["previous_result_restore_mode"] == "full"
    assert merged["previous_result_restore"]["used_loader_payload"] is True
    assert merged["state"]["current_data"]["rows"] == [{"MODE": "A"}, {"MODE": "B"}]


def test_previous_result_restore_router_uses_source_refs_without_current_data_ref() -> None:
    router = load_component("langflow_components/data_analysis_flow/04_previous_result_restore_router.py")
    payload = {
        "intent_plan": {"requires_full_previous_result_restore": True},
        "state": {
            "current_data": {"rows": [{"MODE": "A"}], "row_count": 1},
            "followup_source_results": [
                {
                    "source_alias": "wip_data",
                    "dataset_key": "wip_today",
                    "data_ref": {"store": "mongodb", "ref_id": "source-ref"},
                }
            ],
        },
    }

    routed = router.route_previous_result_restore(payload)

    assert routed["restore_decision"]["required"] is True
    assert routed["restore_decision"]["source_ref_count"] == 1
    assert routed["restore_decision"]["restore_ref_count"] == 1
    assert routed["restore_decision"]["data_ref"] == {}
    assert routed["restore_payload"]["previous_result_restore_mode"] == "full"


def test_web_client_normalizes_route_response_and_builds_subflow_tweaks() -> None:
    raw = {
        "outputs": [
            {
                "results": {
                    "route_response": {
                        "data": {
                            "response_type": "route_decision",
                            "route": "metadata_qa",
                            "selected_flow": "metadata_qa_flow",
                            "metadata_route": {"route": "metadata_qa", "metadata_action": "catalog_list"},
                            "flow_inputs": {"state": {"current_data": {"row_count": 3}}},
                        }
                    }
                }
            }
        ]
    }

    route_payload = normalize_route_response(raw)
    tweaks = build_split_flow_tweaks("metadata_qa_flow", route_payload, state={}, session_id="s1")

    assert route_payload["selected_flow"] == "metadata_qa_flow"
    assert tweaks["00 Metadata QA Request Loader"]["metadata_route"]["metadata_action"] == "catalog_list"
    assert tweaks["00 Metadata QA Request Loader"]["state"]["current_data"]["row_count"] == 3


def test_run_flow_handoff_builder_creates_single_router_payload_branch() -> None:
    handoff = load_component("langflow_components/router_flow/06_run_flow_handoff_builder.py")
    report_loader = load_component("langflow_components/report_generation_flow/00_report_request_loader.py")
    route_response = {
        "selected_flow": "report_generation_flow",
        "flow_inputs": {
            "question": "방금 결과로 리포트 만들어줘",
            "session_id": "session-1",
            "state": {"current_data": {"row_count": 5}},
        },
    }

    report_payload = handoff.build_handoff_payload(route_response, "report_generation_flow")
    data_payload = handoff.build_handoff_payload(route_response, "data_analysis_flow")

    assert report_payload["selected"] is True
    assert report_payload["question"] == "방금 결과로 리포트 만들어줘"
    assert report_payload["session_id"] == "session-1"
    assert report_payload["flow_inputs"]["state"]["current_data"]["row_count"] == 5
    assert report_loader.build_report_request("", "", router_payload=report_payload)["request"]["question"] == "방금 결과로 리포트 만들어줘"
    assert data_payload["selected"] is False
    assert "flow_tweak_data" not in report_payload


def test_subflow_request_loaders_accept_single_router_payload() -> None:
    analysis_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/metadata_qa_flow/00_metadata_qa_request_loader.py")
    report_loader = load_component("langflow_components/report_generation_flow/00_report_request_loader.py")
    diagnosis_loader = load_component("langflow_components/operations_diagnosis_flow/00_diagnosis_request_loader.py")
    route_response = {
        "selected_flow": "metadata_qa_flow",
        "metadata_route": {"route": "metadata_qa", "metadata_action": "catalog_list"},
        "flow_inputs": {
            "question": "사용 가능한 데이터셋 알려줘",
            "session_id": "session-router-only",
            "state": {"current_data": {"row_count": 2}},
            "metadata_route": {"route": "metadata_qa", "metadata_action": "catalog_list"},
        },
    }

    assert analysis_loader.build_request_payload("", "", router_payload=route_response)["request"]["session_id"] == "session-router-only"
    assert (
        metadata_loader.build_metadata_qa_request("", "", router_payload=route_response)["request"]["question"]
        == "사용 가능한 데이터셋 알려줘"
    )
    assert report_loader.build_report_request("", "", router_payload=route_response)["state"]["current_data"]["row_count"] == 2
    assert diagnosis_loader.build_diagnosis_request("", "", router_payload=route_response)["request"]["session_id"] == "session-router-only"


def test_request_loaders_extract_text_and_session_from_chat_message() -> None:
    router_loader = load_component("langflow_components/router_flow/00_router_request_loader.py")
    analysis_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/metadata_qa_flow/00_metadata_qa_request_loader.py")
    report_loader = load_component("langflow_components/report_generation_flow/00_report_request_loader.py")
    diagnosis_loader = load_component("langflow_components/operations_diagnosis_flow/00_diagnosis_request_loader.py")
    session_loader = load_component("langflow_components/session_state_flow/00_mongodb_session_state_loader.py")

    message = SimpleNamespace(text="오늘 WB공정 생산량 알려줘", session_id="chat-session-777")

    assert router_loader.build_request_payload(message)["request"] == {
        "session_id": "chat-session-777",
        "question": "오늘 WB공정 생산량 알려줘",
        "timezone": "Asia/Seoul",
    }
    assert analysis_loader.build_request_payload(message)["request"]["session_id"] == "chat-session-777"
    assert metadata_loader.build_metadata_qa_request(message)["request"]["question"] == "오늘 WB공정 생산량 알려줘"
    assert report_loader.build_report_request(message)["request"]["session_id"] == "chat-session-777"
    assert diagnosis_loader.build_diagnosis_request(message)["request"]["session_id"] == "chat-session-777"
    loaded = session_loader.load_session_state_payload(message, enabled="false")
    assert loaded["request"]["session_id"] == "chat-session-777"
    assert loaded["request"]["question"] == "오늘 WB공정 생산량 알려줘"
