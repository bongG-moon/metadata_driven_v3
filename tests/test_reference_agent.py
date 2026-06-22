from __future__ import annotations

from pathlib import Path

from reference_runtime import run_agent


ROOT = Path(__file__).resolve().parents[1]


def test_multi_step_rank_wip_with_production_keeps_da_wb_groups():
    payload = run_agent(
        "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘",
        root=str(ROOT),
    )

    assert payload["intent_plan"]["intent_type"] == "multi_step_analysis"
    assert payload["applied_scope"]["step_ids"] == [
        "rank_wip_by_process_group",
        "aggregate_production_for_ranked_products",
        "join_rank_and_production",
    ]
    assert {"wip_today", "production_today"}.issubset(set(payload["applied_scope"]["datasets"]))
    assert {"RANK_GROUP", "WIP", "PRODUCTION"}.issubset(set(payload["data"]["columns"]))
    assert sorted({row["RANK_GROUP"] for row in payload["data"]["rows"]}) == ["DA", "WB"]
    assert len([row for row in payload["data"]["rows"] if row["RANK_GROUP"] == "DA"]) == 3
    assert len([row for row in payload["data"]["rows"] if row["RANK_GROUP"] == "WB"]) == 3


def test_process_product_production_and_wip_join_for_da():
    payload = run_agent("오늘 da에서 재공과 생산량을 제품별로 알려줘", root=str(ROOT))

    assert payload["intent_plan"]["analysis_kind"] == "aggregate_join"
    assert {"production_today", "wip_today"}.issubset(set(payload["applied_scope"]["datasets"]))
    assert {"TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "PRODUCTION", "WIP"}.issubset(
        set(payload["data"]["columns"])
    )
    assert payload["data"]["row_count"] > 1
    assert "RANK" not in payload["data"]["columns"]


def test_process_product_production_and_wip_join_for_wb():
    payload = run_agent("오늘 wb에서 재공과 생산량을 제품별로 알려줘", root=str(ROOT))

    assert payload["intent_plan"]["analysis_kind"] == "aggregate_join"
    assert {"production_today", "wip_today"}.issubset(set(payload["applied_scope"]["datasets"]))
    assert {"PRODUCTION", "WIP"}.issubset(set(payload["data"]["columns"]))
    assert payload["data"]["row_count"] > 1


def test_hold_history_uses_hold_history_dataset_and_detail_rows():
    payload = run_agent("T1234567GEN1 LOT의 HOLD이력 알려줘", root=str(ROOT))

    assert payload["intent_plan"]["analysis_kind"] == "detail_rows"
    assert payload["applied_scope"]["datasets"] == ["hold_history"]
    assert {"LOT_ID", "HOLD_TM", "HOLD_CD", "HOLD_DESC"}.issubset(set(payload["data"]["columns"]))
    assert payload["data"]["rows"][0]["LOT_ID"] == "T1234567GEN1"


def test_followup_equipment_uses_current_data_product_grain():
    first = run_agent("현재 da에서 재공이 가장 많은 제품 알려줘", root=str(ROOT))
    second = run_agent("이 제품에 할당된 장비 현황 알려줘", state=first["state"], root=str(ROOT))

    assert second["intent_plan"]["intent_type"] == "followup_transform"
    assert second["intent_plan"]["state_product_keys"]
    assert second["applied_scope"]["datasets"] == ["equipment_status"]
    assert {"EQPID", "EQP_MODEL"}.issubset(set(second["data"]["columns"]))
    assert second["data"]["row_count"] >= 1


def test_followup_equipment_count_uses_equipment_only():
    first = run_agent("현재 da에서 재공이 가장 많은 제품 알려줘", root=str(ROOT))
    second = run_agent("이 제품의 이 공정에 할당된 장비 대수를 알려줘", state=first["state"], root=str(ROOT))

    assert second["intent_plan"]["intent_type"] == "followup_transform"
    assert second["intent_plan"]["analysis_kind"] == "equipment_count_for_previous_products"
    assert second["applied_scope"]["datasets"] == ["equipment_status"]
    assert "EQP_COUNT" in second["data"]["columns"]
    assert second["data"]["rows"][0]["EQP_COUNT"] >= 1


def test_lpddr5_wb_production_and_wip_join():
    payload = run_agent("현재 MODE값이 LPDDR5인 제품의 W/B공정에서 생산량과 재공 수량 알려줘", root=str(ROOT))

    assert {"production_today", "wip_today"}.issubset(set(payload["applied_scope"]["datasets"]))
    assert {"PRODUCTION", "WIP"}.issubset(set(payload["data"]["columns"]))
    assert payload["data"]["rows"][0]["MODE"] == "LPDDR5"


def test_lpddr5_da_production_and_wip_join():
    payload = run_agent("현재 MODE값이 LPDDR5인 제품의 D/A공정에서 생산량과 재공 수량 알려줘", root=str(ROOT))

    assert payload["intent_plan"]["analysis_kind"] == "aggregate_join"
    assert {"production_today", "wip_today"}.issubset(set(payload["applied_scope"]["datasets"]))
    assert {"PRODUCTION", "WIP"}.issubset(set(payload["data"]["columns"]))
    assert payload["data"]["rows"][0]["MODE"] == "LPDDR5"
    production_filters = payload["applied_scope"]["filters_by_source"]["lpddr5_da_production_today"]
    assert any(item["field"] == "OPER_NAME" and "D/A1" in item.get("values", []) for item in production_filters)


def test_lot_count_uses_lot_id_nunique_not_quantity_sum():
    payload = run_agent("현재 작업대기 Lot 수량을 공정별로 알려줘", root=str(ROOT))

    assert payload["intent_plan"]["analysis_kind"] == "lot_count_by_process"
    assert payload["applied_scope"]["datasets"] == ["lot_status"]
    assert {"OPER_SHORT_DESC", "LOT_COUNT"}.issubset(set(payload["data"]["columns"]))
    assert payload["analysis"]["analysis_code"].find("nunique") >= 0


def test_running_lot_count_uses_running_status():
    payload = run_agent("현재 작업중 Lot 수량을 공정별로 알려줘", root=str(ROOT))

    assert payload["intent_plan"]["analysis_kind"] == "lot_count_by_process"
    assert payload["applied_scope"]["datasets"] == ["lot_status"]
    assert {"OPER_SHORT_DESC", "LOT_COUNT"}.issubset(set(payload["data"]["columns"]))
    filters = payload["applied_scope"]["filters_by_source"]["lot_count_by_process"]
    assert filters == [{"field": "LOT_STAT_CD", "op": "eq", "value": "RUNNING"}]


def test_wb_lot_wafer_die_summary_uses_lot_status():
    payload = run_agent(
        "현재 W/B공정에서 재공 lot이 몇개인지, wafer가 몇개인지, die수량은 몇개인지 알려줘",
        root=str(ROOT),
    )

    assert payload["intent_plan"]["analysis_kind"] == "lot_quantity_summary"
    assert payload["applied_scope"]["datasets"] == ["lot_status"]
    assert {"SCOPE", "LOT_COUNT", "WF_QTY", "DIE_QTY"}.issubset(set(payload["data"]["columns"]))
    assert payload["data"]["rows"][0]["SCOPE"] == "WB"
    filters = payload["applied_scope"]["filters_by_source"]["wb_lot_quantity_summary"]
    assert any(item["field"] == "OPER_NAME" and "W/B1" in item.get("values", []) for item in filters)


def test_low_output_vs_target_has_balance_and_flag():
    payload = run_agent("오늘 D/A1공정에서 목표값 대비해서 생산량이 저조한 제품을 알려줘", root=str(ROOT))

    assert payload["intent_plan"]["analysis_kind"] == "low_output_vs_target"
    assert {"production_today", "target"}.issubset(set(payload["applied_scope"]["datasets"]))
    assert {"TARGET_QTY", "ACHIEVEMENT_RATE", "BALANCE", "LOW_OUTPUT_FLAG"}.issubset(set(payload["data"]["columns"]))
    assert payload["data"]["row_count"] >= 1


def test_followup_overall_wip_resets_previous_da_scope():
    first = run_agent("현재 da에서 재공이 가장 많은 제품 알려줘", root=str(ROOT))
    second = run_agent("전체 재공 수량 알려줘", state=first["state"], root=str(ROOT))

    assert second["intent_plan"]["analysis_kind"] == "aggregate_wip_total"
    assert second["data"]["rows"][0]["SCOPE"] == "ALL"
    filters = second["applied_scope"]["filters_by_source"]["wip_total"]
    assert filters == []
    assert "source_dataset_keys" in second["state"]["current_data"]
