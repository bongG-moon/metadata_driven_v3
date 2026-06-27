from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from web_app.langflow_client import build_split_flow_node_input_settings, normalize_route_response


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
            "03a_route_prompt_context_builder.py",
            "04_route_classifier_normalizer.py",
            "05_orchestrator_response_builder.py",
            "06_selected_flow_api_runner.py",
        ],
        "metadata_qa_flow": [
            "00_metadata_qa_request_loader.py",
            "01_metadata_context_loader.py",
            "02_metadata_qa_prompt_builder.py",
            "03_metadata_qa_response_builder.py",
            "04_metadata_qa_message_adapter.py",
            "05_metadata_qa_api_response_builder.py",
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
            "04_diagnosis_message_adapter.py",
            "05_diagnosis_api_response_builder.py",
        ],
        "session_state_flow": [
            "00_mongodb_session_state_loader.py",
            "01_mongodb_session_state_writer.py",
        ],
    }
    for folder, files in expected.items():
        actual = [path.name for path in sorted((ROOT / "langflow_components" / folder).glob("*.py"))]
        assert actual == files


def test_route_prompt_template_uses_only_one_langflow_variable() -> None:
    template_paths = [
        ROOT / "langflow_components" / "router_flow" / "ROUTE_CLASSIFIER_PROMPT_TEMPLATE.md",
        ROOT / "langflow_components" / "router_flow" / "ROUTE_CLASSIFIER_PROMPT_TEMPLATE_KO.md",
    ]

    for template_path in template_paths:
        template = template_path.read_text(encoding="utf-8")
        variables = set(re.findall(r"(?<!\{)\{([^{}]+)\}(?!\})", template))

        assert variables == {"route_prompt_context"}
        assert '"route":' not in template


def test_route_prompt_context_builder_exposes_one_output() -> None:
    prompt_context_builder = load_component("langflow_components/router_flow/03a_route_prompt_context_builder.py")

    assert [item.name for item in prompt_context_builder.RoutePromptContextBuilder.outputs] == ["route_prompt_context"]


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
        assert response["request"]["question"] == "make an operations diagnosis"
        assert response["subflow_call"]["selected_flow"] == selected_flow
        assert response["subflow_call"]["input_value"] == "make an operations diagnosis"
        assert response["subflow_call"]["session_id"] == "s1"


def test_router_flow_can_take_api_url_from_prompt_template_response() -> None:
    normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    orchestrator = load_component("langflow_components/router_flow/05_orchestrator_response_builder.py")
    payload = {
        "request": {"question": "현재 조회 가능한 데이터 알려줘", "session_id": "s1"},
        "metadata_route": {"route": "metadata_qa", "route_llm_required": True},
    }

    classified = normalizer.normalize_route_classifier_payload(
        payload,
        json.dumps(
            {
                "route": "metadata_qa",
                "selected_flow": "metadata_qa_flow",
                "api_url": "http://localhost:7860/api/v1/run/metadata-flow",
                "metadata_action": "catalog_list",
                "confidence": "high",
                "reason": "Catalog question.",
            }
        ),
    )
    response = orchestrator.build_orchestrator_response(classified)

    assert classified["metadata_route"]["api_url"] == "http://localhost:7860/api/v1/run/metadata-flow"
    assert response["selected_flow"] == "metadata_qa_flow"
    assert response["subflow_call"]["api_url"] == "http://localhost:7860/api/v1/run/metadata-flow"


def test_orchestrator_response_builds_subflow_call_from_env(monkeypatch: Any) -> None:
    orchestrator = load_component("langflow_components/router_flow/05_orchestrator_response_builder.py")
    monkeypatch.delenv("LANGFLOW_SUBFLOW_INPUT_TYPE", raising=False)
    monkeypatch.delenv("LANGFLOW_INPUT_TYPE", raising=False)
    monkeypatch.delenv("LANGFLOW_SUBFLOW_OUTPUT_TYPE", raising=False)
    monkeypatch.delenv("LANGFLOW_OUTPUT_TYPE", raising=False)
    monkeypatch.setenv("LANGFLOW_BASE_URL", "http://localhost:7860")
    monkeypatch.setenv("LANGFLOW_METADATA_QA_FLOW_ID", "metadata-flow-id")

    response = orchestrator.build_orchestrator_response(
        {
            "request": {"question": "공정 그룹관련해서 등록된 도메인정보들 알려줘", "session_id": "s1"},
            "metadata_route": {"route": "metadata_qa", "confidence": "high"},
        }
    )

    assert response["api_url"] == "http://localhost:7860/api/v1/run/metadata-flow-id"
    assert response["subflow_call"] == {
        "selected_flow": "metadata_qa_flow",
        "api_url": "http://localhost:7860/api/v1/run/metadata-flow-id",
        "api_url_env": "LANGFLOW_METADATA_QA_API_URL",
        "flow_id_env": "LANGFLOW_METADATA_QA_FLOW_ID",
        "prompt": "공정 그룹관련해서 등록된 도메인정보들 알려줘",
        "input_value": "공정 그룹관련해서 등록된 도메인정보들 알려줘",
        "input_type": "chat",
        "output_type": "chat",
        "session_id": "s1",
    }


def test_selected_flow_api_runner_calls_only_selected_flow() -> None:
    runner = load_component("langflow_components/router_flow/06_selected_flow_api_runner.py")
    route_response = {
        "selected_flow": "metadata_qa_flow",
        "request": {"question": "공정 그룹관련해서 등록된 도메인정보들 알려줘", "session_id": "s1"},
        "subflow_call": {
            "selected_flow": "metadata_qa_flow",
            "api_url": "http://127.0.0.1:7860/api/v1/run/metadata-flow",
            "input_value": "공정 그룹관련해서 등록된 도메인정보들 알려줘",
            "input_type": "chat",
            "output_type": "chat",
            "session_id": "s1",
        },
    }
    calls: list[dict[str, Any]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"api_response": {"answer_message": "metadata answer"}}

    def fake_post(url: str, json: dict[str, Any], headers: dict[str, str], timeout: int) -> FakeResponse:
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()

    result = runner.run_selected_flow_api(
        route_response,
        timeout_seconds="33",
        post_func=fake_post,
    )

    assert result["status"] == "ok"
    assert result["selected_flow"] == "metadata_qa_flow"
    assert result["message"] == "metadata answer"
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/metadata-flow")
    assert calls[0]["json"] == {
        "input_value": "공정 그룹관련해서 등록된 도메인정보들 알려줘",
        "input_type": "chat",
        "output_type": "chat",
        "session_id": "s1",
    }
    assert calls[0]["timeout"] == 33


def test_selected_flow_api_runner_builds_url_from_base_and_flow_id(monkeypatch: Any) -> None:
    runner = load_component("langflow_components/router_flow/06_selected_flow_api_runner.py")
    monkeypatch.setenv("LANGFLOW_BASE_URL", "http://localhost:7860/")
    monkeypatch.setenv("LANGFLOW_METADATA_QA_FLOW_ID", "metadata-flow-id")
    route_response = {
        "selected_flow": "metadata_qa_flow",
        "flow_id_env": "LANGFLOW_METADATA_QA_FLOW_ID",
        "request": {"question": "등록된 데이터 알려줘", "session_id": "s1"},
    }

    call = runner.build_selected_flow_api_call(route_response)

    assert call["api_url"] == "http://localhost:7860/api/v1/run/metadata-flow-id"
    assert call["request"]["input_value"] == "등록된 데이터 알려줘"


def test_selected_flow_api_runner_prefers_subflow_call() -> None:
    runner = load_component("langflow_components/router_flow/06_selected_flow_api_runner.py")
    route_response = {
        "selected_flow": "data_analysis_flow",
        "request": {"question": "fallback question", "session_id": "fallback-session"},
        "subflow_call": {
            "selected_flow": "metadata_qa_flow",
            "api_url": "http://localhost:7860/api/v1/run/metadata-flow",
            "input_value": "등록된 메타데이터 알려줘",
            "input_type": "chat",
            "output_type": "chat",
            "session_id": "s1",
        },
    }
    calls: list[dict[str, Any]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"message": "metadata answer"}

    def fake_post(url: str, json: dict[str, Any], headers: dict[str, str], timeout: int) -> FakeResponse:
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()

    result = runner.run_selected_flow_api(route_response, post_func=fake_post)

    assert result["status"] == "ok"
    assert result["selected_flow"] == "metadata_qa_flow"
    assert result["message"] == "metadata answer"
    assert calls == [
        {
            "url": "http://localhost:7860/api/v1/run/metadata-flow",
            "json": {
                "input_value": "등록된 메타데이터 알려줘",
                "input_type": "chat",
                "output_type": "chat",
                "session_id": "s1",
            },
            "headers": {"Content-Type": "application/json"},
            "timeout": 180,
        }
    ]


def test_selected_flow_api_runner_extracts_nested_langflow_message() -> None:
    runner = load_component("langflow_components/router_flow/06_selected_flow_api_runner.py")
    route_response = {
        "selected_flow": "metadata_qa_flow",
        "request": {"question": "등록된 데이터 알려줘", "session_id": "s1"},
        "subflow_call": {
            "selected_flow": "metadata_qa_flow",
            "api_url": "http://localhost:7860/api/v1/run/metadata-flow",
            "input_value": "등록된 데이터 알려줘",
            "input_type": "chat",
            "output_type": "chat",
            "session_id": "s1",
        },
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "outputs": [
                    {
                        "outputs": [
                            {
                                "results": {
                                    "message": {
                                        "data": {
                                            "text": "metadata nested answer",
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            }

    result = runner.run_selected_flow_api(route_response, post_func=lambda *args, **kwargs: FakeResponse())

    assert result["status"] == "ok"
    assert result["message"] == "metadata nested answer"


def test_selected_flow_api_runner_accepts_flow_id_from_route_response_api_url(monkeypatch: Any) -> None:
    runner = load_component("langflow_components/router_flow/06_selected_flow_api_runner.py")
    monkeypatch.setenv("LANGFLOW_BASE_URL", "http://localhost:7860")
    route_response = {
        "selected_flow": "metadata_qa_flow",
        "api_url": "a4ea11e1-18d2-44e4-9f7a-d149cfeb0c54",
        "request": {"question": "등록된 데이터 알려줘", "session_id": "s1"},
    }

    call = runner.build_selected_flow_api_call(route_response)

    assert call["api_url"] == "http://localhost:7860/api/v1/run/a4ea11e1-18d2-44e4-9f7a-d149cfeb0c54"


def test_selected_flow_api_runner_exposes_no_api_url_inputs() -> None:
    runner = load_component("langflow_components/router_flow/06_selected_flow_api_runner.py")

    assert [item.name for item in runner.SelectedFlowApiRunner.inputs] == ["route_response", "api_key", "timeout_seconds"]


def test_api_response_builders_expose_only_data_output() -> None:
    analysis_api_builder = load_component("langflow_components/data_analysis_flow/21_api_response_builder.py")
    metadata_api_builder = load_component("langflow_components/metadata_qa_flow/05_metadata_qa_api_response_builder.py")

    assert [item.name for item in analysis_api_builder.MainFlowApiResponseBuilder.outputs] == ["api_response"]
    assert [item.name for item in metadata_api_builder.MainFlowApiResponseBuilder.outputs] == ["api_response"]


def test_diagnosis_response_flow_splits_payload_message_and_api_outputs() -> None:
    diagnosis_builder = load_component("langflow_components/operations_diagnosis_flow/03_diagnosis_response_builder.py")
    message_adapter = load_component("langflow_components/operations_diagnosis_flow/04_diagnosis_message_adapter.py")
    api_builder = load_component("langflow_components/operations_diagnosis_flow/05_diagnosis_api_response_builder.py")

    assert [item.name for item in diagnosis_builder.DiagnosisResponseBuilder.outputs] == ["payload_out"]
    assert [item.name for item in message_adapter.DiagnosisMessageAdapter.outputs] == ["message"]
    assert [item.name for item in api_builder.DiagnosisApiResponseBuilder.outputs] == ["api_response"]

    payload = diagnosis_builder.build_diagnosis_response(
        {
            "diagnosis": {
                "findings": [
                    {"signal": "wip_accumulation", "severity": "warning", "recommendation": "WB 공정 병목 여부를 확인하세요."},
                    {
                        "signal": "previous_result_available",
                        "severity": "info",
                        "recommendation": "이전 분석 결과를 조건으로 삼아 필요한 추가 source만 조회합니다.",
                    },
                ]
            },
            "state": {"current_data": {"row_count": 5}},
        }
    )
    message = message_adapter.build_diagnosis_playground_message(payload)
    api_response = api_builder.build_diagnosis_api_response(payload)["api_response"]

    assert "### 운영 진단 리포트" in message
    assert "#### 요약" in message
    assert "#### 관찰 신호" in message
    assert "#### 권장 확인 순서" in message
    assert "[주의] 재공 증가 가능성" in message
    assert "[참고] 이전 분석 결과 활용 가능" in message
    assert "previous_result_available" not in message
    assert "| signal |" not in message
    assert api_response["response_type"] == "operations_diagnosis"
    assert api_response["row_count"] == 2


def test_request_loaders_inherit_session_id_from_state() -> None:
    router_loader = load_component("langflow_components/router_flow/00_router_request_loader.py")
    analysis_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/metadata_qa_flow/00_metadata_qa_request_loader.py")
    report_loader = load_component("langflow_components/report_generation_flow/00_report_request_loader.py")
    diagnosis_loader = load_component("langflow_components/operations_diagnosis_flow/00_diagnosis_request_loader.py")
    session_loader = load_component("langflow_components/session_state_flow/00_mongodb_session_state_loader.py")

    state = {"session_id": "conversation-123", "current_data": {"row_count": 1}}

    router_request = router_loader.build_request_payload("질문", "", state)
    assert router_request["request"]["session_id"] == "conversation-123"

    assert analysis_loader.build_request_payload("질문", "", state)["request"]["session_id"] == "conversation-123"
    assert metadata_loader.build_metadata_qa_request("질문", "", state=state)["request"]["session_id"] == "conversation-123"
    assert report_loader.build_report_request("질문", "", state=state)["request"]["session_id"] == "conversation-123"
    assert diagnosis_loader.build_diagnosis_request("질문", "", state=state)["request"]["session_id"] == "conversation-123"
    assert session_loader.load_session_state_payload("질문", state=state, enabled="false")["request"]["session_id"] == "conversation-123"


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
    assert set(routed["restore_payload"]) == {
        "previous_result_restore",
        "previous_result_restore_mode",
        "restore_previous_result_mode",
    }
    assert routed["restore_payload"]["previous_result_restore_mode"] == "summary"
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


def test_web_client_normalizes_route_response_and_builds_subflow_node_input_settings() -> None:
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
    node_input_settings = build_split_flow_node_input_settings("metadata_qa_flow", route_payload, state={}, session_id="s1")

    assert route_payload["selected_flow"] == "metadata_qa_flow"
    assert node_input_settings["00 Metadata QA Request Loader"]["state"]["current_data"]["row_count"] == 3


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
