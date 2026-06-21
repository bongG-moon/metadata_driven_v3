from __future__ import annotations

import json

from web_app.langflow_client import normalize_authoring_response, normalize_query_response


def test_normalize_query_response_accepts_current_api_response_shape() -> None:
    raw = {
        "outputs": [
            {
                "results": {
                    "api_message": {
                        "text": json.dumps(
                            {
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
                            },
                            ensure_ascii=False,
                        )
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
