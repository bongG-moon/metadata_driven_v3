from __future__ import annotations

from web_app.mock_api import MockApiClient


def test_mock_query_returns_compacted_result_and_loadable_rows() -> None:
    client = MockApiClient()
    result = client.run_query("오늘 전체 재공 수량 알려줘", session_id="test-session")

    assert result["api_mode"] == "python_mock"
    assert result["answer_message"]
    assert result["applied_scope"]["datasets"] == ["wip_today"]
    assert result["data"]["row_count"] >= 1
    assert result["data"]["data_ref"]["store"] == "python_mock"
    assert client.get_rows(result["data"]["data_ref"])
    assert client.sessions["test-session"]["current_data"]["source_dataset_keys"] == ["wip_today"]


def test_mock_query_supports_followup_state() -> None:
    client = MockApiClient()
    first = client.run_query("현재 da에서 재공이 가장 많은 제품 알려줘", session_id="followup")
    second = client.run_query("이 제품에 할당된 장비 현황 알려줘", session_id="followup", state=first["state"])

    assert second["intent_plan"]["intent_type"] == "followup_transform"
    assert "equipment_status" in second["applied_scope"]["datasets"]


def test_mock_query_supports_metadata_qa_without_langflow_api() -> None:
    client = MockApiClient()
    result = client.run_query("현재 조회 가능한 DATA LIST 알려줘", session_id="metadata-qa")

    assert result["response_type"] == "metadata_qa"
    assert result["direct_response_ready"] is True
    assert result["metadata_qa"]["metadata_action"] == "catalog_list"
    assert "production_today" in {row["DATASET_KEY"] for row in result["data"]["rows"]}
    assert result["state"]["context"]["last_route"] == "metadata_qa"


def test_mock_authoring_blocks_duplicate_ask_and_saves_merge() -> None:
    client = MockApiClient()
    raw_text = "Lot 수량은 LOT_ID count_distinct로 계산해."

    asked = client.run_authoring("domain", raw_text, "ask")
    assert asked["ui_status"] == "duplicate_choice_required"
    assert asked["items"][0]["payload"]["aggregation"] == "nunique"
    assert asked["pending_authoring_id"].startswith("pending-")

    merged = client.run_authoring("domain", raw_text, "merge")
    assert merged["ui_status"] == "saved"
    assert merged["write_result"]["saved_count"] == 1


def test_mock_table_authoring_requires_source_query_information() -> None:
    client = MockApiClient()
    result = client.run_authoring("table_catalog", "wip_today 데이터셋을 등록해줘", "ask")

    assert result["ui_status"] == "needs_more_input"
    assert result["review"]["supplement_requests"][0]["field"] == "source_config.query_template"


def test_metadata_lookup_reads_current_seed_files() -> None:
    client = MockApiClient()

    assert any(item["key"] == "DA" for item in client.list_metadata("domain"))
    assert any(item["dataset_key"] == "wip_today" for item in client.list_metadata("table_catalog"))
    assert any(item["filter_key"] == "DATE" for item in client.list_metadata("main_flow_filter"))
