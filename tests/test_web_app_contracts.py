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


def test_chat_metadata_summary_helpers_render_korean_descriptions() -> None:
    scope_lines = app.applied_scope_summary_lines(
        {
            "intent_type": "multi_source_analysis",
            "analysis_kind": "aggregate_join",
            "datasets": ["production_today", "wip_today"],
            "source_aliases": ["production_data", "wip_data"],
            "params_by_source": {"production_data": {"DATE": "20260622"}},
            "filters_by_source": {"production_data": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2"]}]},
        }
    )
    intent_lines = app.intent_plan_summary_lines(
        {
            "route": "data_analysis",
            "intent_type": "multi_source_analysis",
            "analysis_kind": "aggregate_join",
            "reasoning_steps": ["생산량과 재공을 함께 조회합니다."],
            "step_plan": [{"step_id": "join_result", "operation": "left_join", "source_alias": "production_data"}],
        }
    )
    pandas_lines = app.pandas_analysis_summary_lines(
        {
            "status": "ok",
            "executed": True,
            "row_count": 3,
            "columns": ["OPER_GROUP", "PRODUCTION", "WIP"],
            "reasoning_steps": ["공정 그룹별로 집계했습니다."],
        }
    )

    assert any("사용 데이터셋" in line for line in scope_lines)
    assert any("조회 파라미터" in line for line in scope_lines)
    assert any("판단 근거" in line for line in intent_lines)
    assert any("분석 단계" in line for line in intent_lines)
    assert any("Pandas 처리 상태" in line for line in pandas_lines)
    assert any("출력 컬럼" in line for line in pandas_lines)


def test_result_display_helpers_keep_full_rows_and_csv_bytes() -> None:
    rows = [
        {"B": 2, "A": "제품1"},
        {"B": 3, "A": "제품2"},
    ]

    frame = app.dataframe_with_columns(rows, ["A", "B"])
    csv_bytes = app.dataframe_csv_bytes(frame)

    assert list(frame.columns) == ["A", "B"]
    assert app.result_rows_are_preview({"data_is_preview": True}) is True
    assert app.result_rows_are_preview({"rows": rows, "row_count": 2}) is False
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert "제품1" in csv_bytes.decode("utf-8-sig")
