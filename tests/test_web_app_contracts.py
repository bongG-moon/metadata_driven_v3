from __future__ import annotations

from web_app import app


def test_authoring_input_payload_appends_review_notes() -> None:
    payload = app.authoring_input_payload("원문 설명", "기존 항목과 충돌하면 merge로 처리")

    assert payload == "원문 설명\n\n[추가 검수 지시]\n기존 항목과 충돌하면 merge로 처리"


def test_authoring_trace_stages_builds_current_trace_dict() -> None:
    result = {
        "ui_status": "saved",
        "items": [{"dataset_key": "production_today", "payload": {"display_name": "Production Today"}}],
        "review": {"ready_to_save": True, "item_reviews": [{"decision": "pass"}]},
        "write_result": {"status": "ok", "saved_count": "1"},
        "trace": {
            "raw_text": "생산량 데이터를 등록해줘",
            "refined_text": "production_today 등록",
            "duplicate_decision": {"action": "replace", "requires_user_choice": False},
        },
    }

    stages = app.authoring_trace_stages(result)

    assert [stage["stage"] for stage in stages] == ["input", "refinement", "normalization", "duplicate", "review", "write"]
    assert app.authoring_saved(result) is True
    assert app.authoring_status_label("duplicate_choice_required") == "중복 처리 선택 필요"


def test_state_summary_for_sidebar_uses_compact_current_data() -> None:
    state = {
        "current_data": {
            "source_dataset_keys": ["production_today"],
            "source_aliases": ["production_data"],
            "row_count": "128",
            "preview_rows": [{"MODE": "HBM3E"}],
            "columns": ["WORK_DT", "MODE", "DEVICE", "PRODUCTION"],
            "product_key_summary": {"product_count": "7"},
        }
    }

    summary = app.state_summary_for_sidebar(state, {})
    html = app.active_scope_sidebar_html(state, {})

    assert summary["datasets"] == ["production_today"]
    assert summary["row_count"] == 128
    assert summary["product_key_count"] == 7
    assert "production_today" in html
    assert "Rows" in html


def test_authoring_example_text_reads_flow_example_files() -> None:
    text = app.authoring_example_text("table_catalog")

    assert "query_template" in text
    assert "filter_mappings" in text
