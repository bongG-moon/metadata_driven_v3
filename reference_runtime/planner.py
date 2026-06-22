from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .metadata import get_product_key_columns


DEFAULT_SAMPLE_DATE = "20260612"


def build_intent_plan(
    question: str,
    metadata: dict[str, Any],
    state: dict[str, Any] | None = None,
    request_date: str | None = None,
) -> dict[str, Any]:
    """Create a small, evidence-friendly plan.

    The deterministic planner is intentionally simple. In production this
    component is the place where the LLM JSON planner would be called, then a
    normalizer would apply the same metadata checks used here.
    """

    state = state or {}
    date_value = request_date or DEFAULT_SAMPLE_DATE
    q_upper = question.upper()
    product_keys = get_product_key_columns(metadata)

    if _is_multi_step_wip_production_question(question):
        return _plan_wip_rank_then_production(question, metadata, date_value, product_keys)

    lot_id = _extract_lot_id(question)
    if lot_id and "HOLD" in q_upper and ("이력" in question or "HISTORY" in q_upper):
        return _plan_hold_history(question, lot_id)

    if "HOLD" in q_upper and "LOT" in q_upper and ("LIST" in q_upper or "목록" in question or "현재" in question):
        return _plan_hold_lot_list(question)

    if _is_waiting_lot_count_question(question):
        return _plan_lot_count_by_process(question, metadata, status_code="WAITING")

    if _is_running_lot_count_question(question):
        return _plan_lot_count_by_process(question, metadata, status_code="RUNNING")

    if _is_process_lot_wafer_die_question(question):
        return _plan_lot_quantity_summary(question, metadata)

    if _is_followup_equipment_question(question):
        return _plan_equipment_followup(question, metadata, state, product_keys)

    if _is_hbm_equipment_question(question):
        return _plan_hbm_equipment_by_model(question, product_keys)

    if _is_date_split_production_plan_gap_question(question):
        return _plan_yesterday_production_today_plan_gap(question, product_keys)

    if _is_low_output_question(question):
        return _plan_low_output_vs_target(question, metadata, date_value, product_keys)

    if _is_process_production_wip_product_question(question):
        return _plan_process_production_wip(question, metadata, date_value, product_keys)

    if ("목표" in question or "달성" in question) and (_mentions_da(question) or _mentions_wb(question)):
        return _plan_production_wip_target_rate(question, metadata, date_value, product_keys)

    if _is_total_production_wip_target_question(question):
        return _plan_total_production_wip_target(question, date_value, product_keys)

    recipe_plan = _plan_from_analysis_recipe(question, metadata, date_value, product_keys)
    if recipe_plan:
        return recipe_plan

    if _is_wip_quantity_question(question):
        return _plan_wip_total(question, metadata, date_value)

    if ("재공" in question or "WIP" in q_upper) and (_mentions_da(question) or _mentions_wb(question)):
        return _plan_single_wip_rank(question, metadata, date_value, product_keys)

    return {
        "intent_type": "finish",
        "route": "direct_answer",
        "question": question,
        "answer_hint": "질문에서 조회 대상 dataset과 분석 조건을 확정하지 못했습니다.",
        "retrieval_jobs": [],
        "analysis_kind": "none",
        "step_plan": [],
    }


def _base_plan(question: str, intent_type: str, analysis_kind: str) -> dict[str, Any]:
    return {
        "payload_version": "agent-v1",
        "intent_type": intent_type,
        "route": "analysis",
        "question": question,
        "analysis_kind": analysis_kind,
        "metadata_refs": [],
        "retrieval_jobs": [],
        "step_plan": [],
    }


def _plan_wip_rank_then_production(
    question: str,
    metadata: dict[str, Any],
    date_value: str,
    product_keys: list[str],
) -> dict[str, Any]:
    process_groups = {
        "DA": _process_values(metadata, "DA", question),
        "WB": _process_values(metadata, "WB", question),
    }
    all_processes = sorted({process for values in process_groups.values() for process in values})
    plan = _base_plan(question, "multi_step_analysis", "rank_wip_then_join_production")
    plan.update(
        {
            "date": date_value,
            "product_grain": product_keys,
            "requested_measures": [
                {"metric": "WIP", "dataset_key": "wip_today", "aggregation": "sum"},
                {"metric": "PRODUCTION", "dataset_key": "production_today", "aggregation": "sum"},
            ],
            "analysis_output_shape": "ranked_product_rows_with_joined_production",
            "retrieval_jobs": [
                {
                    "job_id": "job_wip_rank_source",
                    "source_alias": "wip_today_rank_scope",
                    "dataset_key": "wip_today",
                    "params": {"DATE": date_value},
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": all_processes}],
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "WIP"],
                    "purpose": "rank_source",
                },
                {
                    "job_id": "job_production_for_ranked_products",
                    "source_alias": "production_today_for_ranked_products",
                    "dataset_key": "production_today",
                    "params": {"DATE": date_value},
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": all_processes}],
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "PRODUCTION"],
                    "purpose": "dependent_measure_source",
                    "depends_on": "rank_wip_by_process_group",
                },
            ],
            "step_plan": [
                {
                    "step_id": "rank_wip_by_process_group",
                    "operation": "rank_top_n_per_filter_group",
                    "source_alias": "wip_today_rank_scope",
                    "metric": "WIP",
                    "top_n": 3,
                    "rank_groups": [
                        {"label": label, "field": "OPER_NAME", "values": values}
                        for label, values in process_groups.items()
                    ],
                    "group_by": ["RANK_GROUP", *product_keys],
                    "output_ref": "ranked_products",
                },
                {
                    "step_id": "aggregate_production_for_ranked_products",
                    "operation": "aggregate_for_previous_keys",
                    "source_alias": "production_today_for_ranked_products",
                    "depends_on": "rank_wip_by_process_group",
                    "metric": "PRODUCTION",
                    "group_by": product_keys,
                    "key_source_ref": "ranked_products",
                    "output_ref": "production_by_ranked_product",
                },
                {
                    "step_id": "join_rank_and_production",
                    "operation": "join_previous_steps",
                    "depends_on": ["rank_wip_by_process_group", "aggregate_production_for_ranked_products"],
                    "join_keys": product_keys,
                    "output_ref": "final_result",
                },
            ],
        }
    )
    return plan


def _plan_hold_history(question: str, lot_id: str) -> dict[str, Any]:
    plan = _base_plan(question, "detail_lookup", "detail_rows")
    plan.update(
        {
            "requested_measures": [],
            "detail_columns": ["LOT_ID", "HOLD_TM", "HOLD_CD", "HOLD_DESC", "HOLD_USER_ID", "EVENT_CD"],
            "retrieval_jobs": [
                {
                    "job_id": "job_hold_history",
                    "source_alias": "hold_history_for_lot",
                    "dataset_key": "hold_history",
                    "params": {"LOT_ID": lot_id},
                    "filters": [{"field": "LOT_ID", "op": "eq", "value": lot_id}],
                    "required_columns": ["LOT_ID", "HOLD_TM", "HOLD_CD", "HOLD_DESC", "HOLD_USER_ID", "EVENT_CD"],
                    "purpose": "detail_rows",
                }
            ],
            "step_plan": [
                {
                    "step_id": "return_hold_history_rows",
                    "operation": "detail_rows",
                    "source_alias": "hold_history_for_lot",
                    "columns": ["LOT_ID", "HOLD_TM", "HOLD_CD", "HOLD_DESC", "HOLD_USER_ID", "EVENT_CD"],
                }
            ],
        }
    )
    return plan


def _plan_hold_lot_list(question: str) -> dict[str, Any]:
    plan = _base_plan(question, "detail_lookup", "detail_rows")
    plan.update(
        {
            "requested_measures": [],
            "detail_columns": [
                "LOT_ID",
                "OPER_SHORT_DESC",
                "LOT_STAT_CD",
                "LOT_HOLD_STAT_CD",
                "SUB_PROD_QTY",
                "WF_QTY",
                "IN_TAT",
                "CUM_TAT",
            ],
            "retrieval_jobs": [
                {
                    "job_id": "job_current_hold_lots",
                    "source_alias": "current_hold_lots",
                    "dataset_key": "lot_status",
                    "params": {},
                    "filters": [{"field": "LOT_HOLD_STAT_CD", "op": "in", "values": ["HOLD", "OnHold"]}],
                    "required_columns": [
                        "LOT_ID",
                        "OPER_SHORT_DESC",
                        "LOT_STAT_CD",
                        "LOT_HOLD_STAT_CD",
                        "SUB_PROD_QTY",
                        "WF_QTY",
                        "IN_TAT",
                        "CUM_TAT",
                    ],
                    "purpose": "detail_rows",
                }
            ],
            "step_plan": [
                {
                    "step_id": "return_current_hold_lots",
                    "operation": "detail_rows",
                    "source_alias": "current_hold_lots",
                    "columns": [
                        "LOT_ID",
                        "OPER_SHORT_DESC",
                        "LOT_STAT_CD",
                        "LOT_HOLD_STAT_CD",
                        "SUB_PROD_QTY",
                        "WF_QTY",
                        "IN_TAT",
                        "CUM_TAT",
                    ],
                }
            ],
        }
    )
    return plan


def _plan_lot_count_by_process(question: str, metadata: dict[str, Any], status_code: str) -> dict[str, Any]:
    plan = _base_plan(question, "single_retrieval_analysis", "lot_count_by_process")
    plan.update(
        {
            "requested_measures": [
                {"metric": "LOT_COUNT", "dataset_key": "lot_status", "aggregation": "nunique", "quantity_column": "LOT_ID"}
            ],
            "retrieval_jobs": [
                {
                    "job_id": "job_lot_count_by_process",
                    "source_alias": "lot_count_by_process",
                    "dataset_key": "lot_status",
                    "params": {},
                    "filters": [{"field": "LOT_STAT_CD", "op": "eq", "value": status_code}],
                    "required_columns": ["LOT_ID", "OPER_SHORT_DESC", "LOT_STAT_CD", "TECH", "DEN", "MODE"],
                    "purpose": "lot_count",
                }
            ],
            "step_plan": [
                {
                    "step_id": "count_lots_by_process",
                    "operation": "count_distinct",
                    "source_alias": "lot_count_by_process",
                    "group_by": ["OPER_SHORT_DESC"],
                    "quantity_column": "LOT_ID",
                    "output_column": "LOT_COUNT",
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan


def _plan_lot_quantity_summary(question: str, metadata: dict[str, Any]) -> dict[str, Any]:
    process_key = _process_group_key(question) or "DA"
    processes = _process_values(metadata, process_key, question)
    source_alias = f"{process_key.lower()}_lot_quantity_summary"
    plan = _base_plan(question, "single_retrieval_analysis", "lot_quantity_summary")
    plan.update(
        {
            "scope_label": process_key,
            "requested_measures": [
                {"metric": "LOT_COUNT", "dataset_key": "lot_status", "aggregation": "nunique", "quantity_column": "LOT_ID"},
                {"metric": "WF_QTY", "dataset_key": "lot_status", "aggregation": "sum"},
                {"metric": "DIE_QTY", "dataset_key": "lot_status", "aggregation": "sum", "source_column": "SUB_PROD_QTY"},
            ],
            "retrieval_jobs": [
                {
                    "job_id": f"job_{source_alias}",
                    "source_alias": source_alias,
                    "dataset_key": "lot_status",
                    "params": {},
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": processes}],
                    "required_columns": ["LOT_ID", "OPER_SHORT_DESC", "SUB_PROD_QTY", "WF_QTY", "LOT_STAT_CD", "LOT_HOLD_STAT_CD"],
                    "purpose": "lot_quantity_summary",
                }
            ],
            "step_plan": [
                {
                    "step_id": "summarize_lot_wafer_die",
                    "operation": "aggregate_lot_wafer_die",
                    "source_alias": source_alias,
                    "quantity_column": "LOT_ID",
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan


def _plan_equipment_followup(
    question: str,
    metadata: dict[str, Any],
    state: dict[str, Any],
    product_keys: list[str],
) -> dict[str, Any]:
    previous_rows = _previous_current_rows(state)
    product_tuples = _extract_product_tuples(previous_rows, product_keys)
    count_requested = _is_equipment_count_question(question)
    analysis_kind = "equipment_count_for_previous_products" if count_requested else "equipment_for_previous_products"
    requested_measures = (
        [{"metric": "EQP_COUNT", "dataset_key": "equipment_status", "aggregation": "nunique", "quantity_column": "EQPID"}]
        if count_requested
        else [{"metric": "PRESS_CNT", "dataset_key": "equipment_status", "aggregation": "detail"}]
    )
    required_columns = ["EQPID", *product_keys] if count_requested else ["EQPID", "EQP_MODEL", "PRESS_CNT", *product_keys, "LOT_ID", "RECIPE_ID"]
    output_columns = [*product_keys, "EQP_COUNT"] if count_requested else ["EQPID", "EQP_MODEL", "PRESS_CNT", *product_keys, "LOT_ID", "RECIPE_ID"]
    plan = _base_plan(question, "followup_transform", analysis_kind)
    plan.update(
        {
            "product_grain": product_keys,
            "state_product_keys": product_tuples,
            "requested_measures": requested_measures,
            "retrieval_jobs": [
                {
                    "job_id": "job_equipment_for_previous_products",
                    "source_alias": "equipment_for_previous_products",
                    "dataset_key": "equipment_status",
                    "params": {},
                    "filters": [{"field": "PRODUCT_GRAIN", "op": "tuple_in", "values": product_tuples}],
                    "required_columns": required_columns,
                    "purpose": "followup_equipment_count" if count_requested else "followup_detail_rows",
                }
            ],
            "step_plan": [
                {
                    "step_id": "load_previous_product_keys",
                    "operation": "read_state_current_data",
                    "columns": product_keys,
                    "output_ref": "previous_product_keys",
                },
                {
                    "step_id": "count_equipment_for_previous_products" if count_requested else "filter_equipment_by_previous_products",
                    "operation": "equipment_count_for_previous_products" if count_requested else "detail_rows_for_product_keys",
                    "source_alias": "equipment_for_previous_products",
                    "depends_on": "load_previous_product_keys",
                    "columns": output_columns,
                    "output_ref": "final_result",
                },
            ],
        }
    )
    return plan


def _plan_hbm_equipment_by_model(question: str, product_keys: list[str]) -> dict[str, Any]:
    plan = _base_plan(question, "single_retrieval_analysis", "equipment_by_model")
    plan.update(
        {
            "product_grain": product_keys,
            "requested_measures": [{"metric": "PRESS_CNT", "dataset_key": "equipment_status", "aggregation": "sum"}],
            "retrieval_jobs": [
                {
                    "job_id": "job_hbm_equipment_status",
                    "source_alias": "hbm_equipment_status",
                    "dataset_key": "equipment_status",
                    "params": {},
                    "filters": [{"field": "PKG_TYPE1", "op": "eq", "value": "HBM"}],
                    "required_columns": ["EQPID", "EQP_MODEL", "PRESS_CNT", *product_keys, "RECIPE_ID"],
                    "purpose": "equipment_summary",
                }
            ],
            "step_plan": [
                {
                    "step_id": "aggregate_hbm_equipment_by_model",
                    "operation": "aggregate_equipment_by_model",
                    "source_alias": "hbm_equipment_status",
                    "group_by": ["EQP_MODEL"],
                    "metric": "PRESS_CNT",
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan


def _plan_process_production_wip(
    question: str,
    metadata: dict[str, Any],
    date_value: str,
    product_keys: list[str],
) -> dict[str, Any]:
    process_key = _process_group_key(question) or "WB"
    processes = _process_values(metadata, process_key, question)
    is_lpddr5 = "LPDDR5" in question.upper()
    source_prefix = f"lpddr5_{process_key.lower()}" if is_lpddr5 else f"{process_key.lower()}_product"
    common_filters = [{"field": "OPER_NAME", "op": "in", "values": processes}]
    if is_lpddr5:
        common_filters.insert(0, {"field": "MODE", "op": "eq", "value": "LPDDR5"})
    plan = _base_plan(question, "multi_source_analysis", "aggregate_join")
    plan.update(
        {
            "date": date_value,
            "product_grain": product_keys,
            "requested_measures": [
                {"metric": "PRODUCTION", "dataset_key": "production_today", "aggregation": "sum"},
                {"metric": "WIP", "dataset_key": "wip_today", "aggregation": "sum"},
            ],
            "retrieval_jobs": [
                {
                    "job_id": f"job_{source_prefix}_production",
                    "source_alias": f"{source_prefix}_production_today",
                    "dataset_key": "production_today",
                    "params": {"DATE": date_value},
                    "filters": deepcopy(common_filters),
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "PRODUCTION"],
                    "purpose": "measure_source",
                },
                {
                    "job_id": f"job_{source_prefix}_wip",
                    "source_alias": f"{source_prefix}_wip_today",
                    "dataset_key": "wip_today",
                    "params": {"DATE": date_value},
                    "filters": deepcopy(common_filters),
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "WIP"],
                    "purpose": "measure_source",
                },
            ],
            "step_plan": [
                {
                    "step_id": f"aggregate_{source_prefix}_production",
                    "operation": "aggregate",
                    "source_alias": f"{source_prefix}_production_today",
                    "metric": "PRODUCTION",
                    "group_by": product_keys,
                    "output_ref": "production_by_product",
                },
                {
                    "step_id": f"aggregate_{source_prefix}_wip",
                    "operation": "aggregate",
                    "source_alias": f"{source_prefix}_wip_today",
                    "metric": "WIP",
                    "group_by": product_keys,
                    "output_ref": "wip_by_product",
                },
                {
                    "step_id": "join_production_and_wip",
                    "operation": "join_previous_steps",
                    "depends_on": [f"aggregate_{source_prefix}_production", f"aggregate_{source_prefix}_wip"],
                    "join_keys": product_keys,
                    "output_ref": "final_result",
                },
            ],
        }
    )
    return plan


def _plan_low_output_vs_target(
    question: str,
    metadata: dict[str, Any],
    date_value: str,
    product_keys: list[str],
) -> dict[str, Any]:
    process_key = "DA" if _mentions_da(question) else "WB"
    processes = _process_values(metadata, process_key, question)
    target_column = "INPUT_PLAN" if "INPUT계획" in question.upper() or "INPUT계획" in question else "OUT_PLAN"
    plan = _base_plan(question, "multi_source_analysis", "low_output_vs_target")
    plan.update(
        {
            "date": date_value,
            "product_grain": product_keys,
            "threshold_percent": 90.0,
            "target_column": target_column,
            "requested_measures": [
                {"metric": "PRODUCTION", "dataset_key": "production_today", "aggregation": "sum"},
                {"metric": target_column, "dataset_key": "target", "aggregation": "sum"},
                {"metric": "ACHIEVEMENT_RATE", "formula": f"sum(PRODUCTION) / sum({target_column}) * 100"},
                {"metric": "BALANCE", "formula": f"max(sum({target_column}) - sum(PRODUCTION), 0)"},
            ],
            "retrieval_jobs": [
                {
                    "job_id": "job_low_output_production",
                    "source_alias": "low_output_production",
                    "dataset_key": "production_today",
                    "params": {"DATE": date_value},
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": processes}],
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "PRODUCTION"],
                    "purpose": "actual_source",
                },
                {
                    "job_id": "job_low_output_target",
                    "source_alias": "low_output_target",
                    "dataset_key": "target",
                    "params": {},
                    "filters": [{"field": "DATE", "op": "eq", "value": _date_with_dash(date_value)}],
                    "required_columns": ["DATE", *product_keys, "INPUT_PLAN", "OUT_PLAN"],
                    "purpose": "baseline_source",
                },
            ],
            "step_plan": [
                {
                    "step_id": "aggregate_actual_and_target",
                    "operation": "aggregate_join_with_low_output_flag",
                    "group_by": product_keys,
                    "target_column": target_column,
                    "threshold_percent": 90.0,
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan


def _plan_yesterday_production_today_plan_gap(question: str, product_keys: list[str]) -> dict[str, Any]:
    plan = _base_plan(question, "multi_source_analysis", "date_split_production_plan_gap")
    plan.update(
        {
            "product_grain": product_keys,
            "requested_measures": [
                {"metric": "PRODUCTION", "dataset_key": "production", "date": "20260611", "aggregation": "sum"},
                {"metric": "OUT_PLAN", "dataset_key": "target", "date": "2026-06-12", "aggregation": "sum"},
                {"metric": "BALANCE", "formula": "sum(OUT_PLAN) - sum(PRODUCTION)"},
            ],
            "retrieval_jobs": [
                {
                    "job_id": "job_yesterday_production",
                    "source_alias": "yesterday_production",
                    "dataset_key": "production",
                    "params": {},
                    "filters": [{"field": "DATE", "op": "eq", "value": "20260611"}],
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "PRODUCTION"],
                    "purpose": "actual_source",
                },
                {
                    "job_id": "job_today_target",
                    "source_alias": "today_target",
                    "dataset_key": "target",
                    "params": {},
                    "filters": [{"field": "DATE", "op": "eq", "value": "2026-06-12"}],
                    "required_columns": ["DATE", *product_keys, "OUT_PLAN"],
                    "purpose": "baseline_source",
                },
            ],
            "step_plan": [
                {
                    "step_id": "join_yesterday_production_today_plan",
                    "operation": "aggregate_join_with_balance",
                    "group_by": product_keys,
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan


def _plan_total_production_wip_target(question: str, date_value: str, product_keys: list[str]) -> dict[str, Any]:
    plan = _base_plan(question, "multi_source_analysis", "overall_production_wip_target")
    plan.update(
        {
            "date": date_value,
            "retrieval_jobs": [
                {
                    "job_id": "job_total_production",
                    "source_alias": "total_production_today",
                    "dataset_key": "production_today",
                    "params": {"DATE": date_value},
                    "filters": [],
                    "required_columns": ["WORK_DT", "PRODUCTION"],
                    "purpose": "measure_source",
                },
                {
                    "job_id": "job_total_wip",
                    "source_alias": "total_wip_today",
                    "dataset_key": "wip_today",
                    "params": {"DATE": date_value},
                    "filters": [],
                    "required_columns": ["WORK_DT", "WIP"],
                    "purpose": "measure_source",
                },
                {
                    "job_id": "job_total_target",
                    "source_alias": "total_target",
                    "dataset_key": "target",
                    "params": {},
                    "filters": [{"field": "DATE", "op": "eq", "value": _date_with_dash(date_value)}],
                    "required_columns": ["DATE", "OUT_PLAN"],
                    "purpose": "plan_source",
                },
            ],
            "step_plan": [
                {
                    "step_id": "summarize_total_production_wip_target",
                    "operation": "aggregate_total_measures",
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan


def _plan_wip_total(question: str, metadata: dict[str, Any], date_value: str) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    scope_label = "ALL"
    if _mentions_da(question) and "전체" not in question:
        filters = [{"field": "OPER_NAME", "op": "in", "values": _process_values(metadata, "DA", question)}]
        scope_label = "DA"
    elif _mentions_wb(question) and "전체" not in question:
        filters = [{"field": "OPER_NAME", "op": "in", "values": _process_values(metadata, "WB", question)}]
        scope_label = "WB"

    plan = _base_plan(question, "single_retrieval_analysis", "aggregate_wip_total")
    plan.update(
        {
            "date": date_value,
            "scope_label": scope_label,
            "requested_measures": [{"metric": "WIP", "dataset_key": "wip_today", "aggregation": "sum"}],
            "retrieval_jobs": [
                {
                    "job_id": "job_wip_total",
                    "source_alias": "wip_total",
                    "dataset_key": "wip_today",
                    "params": {"DATE": date_value},
                    "filters": filters,
                    "required_columns": ["WORK_DT", "OPER_NAME", "WIP"],
                    "purpose": "wip_total",
                }
            ],
            "step_plan": [
                {
                    "step_id": "sum_wip_total",
                    "operation": "aggregate_total",
                    "source_alias": "wip_total",
                    "metric": "WIP",
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan


def _plan_production_wip_target_rate(
    question: str,
    metadata: dict[str, Any],
    date_value: str,
    product_keys: list[str],
) -> dict[str, Any]:
    process_key = "DA" if _mentions_da(question) else "WB"
    processes = _process_values(metadata, process_key, question)
    plan = _base_plan(question, "multi_source_analysis", "production_wip_target_rate")
    plan.update(
        {
            "date": date_value,
            "product_grain": product_keys,
            "requested_measures": [
                {"metric": "PRODUCTION", "dataset_key": "production_today", "aggregation": "sum"},
                {"metric": "WIP", "dataset_key": "wip_today", "aggregation": "sum"},
                {"metric": "OUT_PLAN", "dataset_key": "target", "aggregation": "sum"},
                {"metric": "ACHIEVEMENT_RATE", "formula": "sum(PRODUCTION) / sum(OUT_PLAN) * 100"},
            ],
            "retrieval_jobs": [
                {
                    "job_id": "job_scope_production",
                    "source_alias": "scope_production_today",
                    "dataset_key": "production_today",
                    "params": {"DATE": date_value},
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": processes}],
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "PRODUCTION"],
                    "purpose": "measure_source",
                },
                {
                    "job_id": "job_scope_wip",
                    "source_alias": "scope_wip_today",
                    "dataset_key": "wip_today",
                    "params": {"DATE": date_value},
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": processes}],
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "WIP"],
                    "purpose": "measure_source",
                },
                {
                    "job_id": "job_scope_target",
                    "source_alias": "scope_target",
                    "dataset_key": "target",
                    "params": {},
                    "filters": [{"field": "DATE", "op": "eq", "value": _date_with_dash(date_value)}],
                    "required_columns": ["DATE", *product_keys, "INPUT_PLAN", "OUT_PLAN"],
                    "purpose": "plan_source",
                },
            ],
            "step_plan": [
                {
                    "step_id": "aggregate_production_wip_target",
                    "operation": "aggregate_join_with_formula",
                    "metrics": ["PRODUCTION", "WIP", "OUT_PLAN"],
                    "formula": "ACHIEVEMENT_RATE = PRODUCTION / OUT_PLAN * 100",
                    "group_by": product_keys,
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan


def _plan_single_wip_rank(
    question: str,
    metadata: dict[str, Any],
    date_value: str,
    product_keys: list[str],
) -> dict[str, Any]:
    process_key = "DA" if _mentions_da(question) else "WB"
    processes = _process_values(metadata, process_key, question)
    top_n = 1 if ("가장" in question or "TOP 1" in question.upper()) else 3
    plan = _base_plan(question, "single_retrieval_analysis", "rank_top_n")
    plan.update(
        {
            "date": date_value,
            "product_grain": product_keys,
            "requested_measures": [{"metric": "WIP", "dataset_key": "wip_today", "aggregation": "sum"}],
            "retrieval_jobs": [
                {
                    "job_id": "job_wip_rank",
                    "source_alias": "wip_today_rank",
                    "dataset_key": "wip_today",
                    "params": {"DATE": date_value},
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": processes}],
                    "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "WIP"],
                    "purpose": "rank_source",
                }
            ],
            "step_plan": [
                {
                    "step_id": "rank_wip_products",
                    "operation": "rank_top_n",
                    "source_alias": "wip_today_rank",
                    "metric": "WIP",
                    "top_n": top_n,
                    "group_by": product_keys,
                    "output_ref": "final_result",
                }
            ],
        }
    )
    return plan



def _plan_from_analysis_recipe(
    question: str,
    metadata: dict[str, Any],
    date_value: str,
    product_keys: list[str],
) -> dict[str, Any] | None:
    recipes = _analysis_recipes(metadata)
    for recipe_key, recipe in recipes.items():
        if not isinstance(recipe, dict):
            continue
        if str(recipe.get("intent_type") or "").strip() != "multi_step_analysis":
            continue
        if not _recipe_matches(question, recipe):
            continue
        top_n = _recipe_top_n(question, recipe)
        grain_policy = str(recipe.get("grain_policy") or "").strip()
        resolved_product_keys = [] if grain_policy == "recipe_step_grain" else list(product_keys)
        output_columns = _text_list(recipe.get("output_columns"))
        plan = _base_plan(question, "multi_step_analysis", str(recipe.get("default_analysis_kind") or recipe_key))
        plan.update(
            {
                "date": date_value,
                "product_grain": resolved_product_keys,
                "top_n": top_n,
                "matched_analysis_recipe": str(recipe_key),
                "recipe_grain_policy": grain_policy,
                "metadata_refs": [{"section": "analysis_recipes", "key": str(recipe_key)}],
                "analysis_output_columns": output_columns,
                "output_columns": output_columns,
                "requested_measures": _recipe_requested_measures(recipe),
                "retrieval_jobs": _recipe_retrieval_jobs(recipe, metadata, question, date_value),
                "step_plan": _recipe_step_plan(recipe, top_n),
            }
        )
        return plan
    return None


def _analysis_recipes(metadata: dict[str, Any]) -> dict[str, Any]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    recipes = domain.get("analysis_recipes") if isinstance(domain.get("analysis_recipes"), dict) else {}
    return recipes


def _recipe_matches(question: str, recipe: dict[str, Any]) -> bool:
    forbidden = recipe.get("forbidden_question_cues") if isinstance(recipe.get("forbidden_question_cues"), list) else []
    if forbidden and any(_cue_matches(question, cue) for cue in forbidden):
        return False
    required = recipe.get("required_question_cues") if isinstance(recipe.get("required_question_cues"), list) else []
    if required:
        return all(_cue_group_matches(question, cue) for cue in required)
    cues = recipe.get("question_cues") if isinstance(recipe.get("question_cues"), list) else []
    return bool(cues) and all(_cue_matches(question, cue) for cue in cues)


def _cue_group_matches(question: str, cue: Any) -> bool:
    if isinstance(cue, list):
        return any(_cue_matches(question, item) for item in cue)
    if isinstance(cue, dict):
        any_items = cue.get("any") if isinstance(cue.get("any"), list) else []
        all_items = cue.get("all") if isinstance(cue.get("all"), list) else []
        if any_items:
            return any(_cue_matches(question, item) for item in any_items)
        if all_items:
            return all(_cue_matches(question, item) for item in all_items)
    return _cue_matches(question, cue)


def _cue_matches(question: str, cue: Any) -> bool:
    cue_text = str(cue or "").strip()
    if not cue_text:
        return False
    question_variants = _match_variants(question)
    cue_variants = _match_variants(cue_text)
    return any(cue_variant and any(cue_variant in question_variant for question_variant in question_variants) for cue_variant in cue_variants)


def _match_variants(value: Any) -> set[str]:
    raw = str(value or "").lower().strip()
    normalized = re.sub(r"[\s_/-]+", " ", raw).strip()
    compact = normalized.replace(" ", "")
    return {item for item in {raw, normalized, compact, raw.replace("_", " "), raw.replace(" ", "_")} if item}


def _recipe_top_n(question: str, recipe: dict[str, Any]) -> int:
    defaults = recipe.get("defaults") if isinstance(recipe.get("defaults"), dict) else {}
    default_top_n = defaults.get("top_n", 1)
    try:
        fallback = int(default_top_n)
    except (TypeError, ValueError):
        fallback = 1
    matches = [int(match.group(0)) for match in re.finditer(r"\b\d{1,2}\b", str(question or ""))]
    return next((value for value in matches if value > 0), fallback if fallback > 0 else 1)


def _recipe_requested_measures(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for term in _text_list(recipe.get("required_quantity_terms")):
        result.append({"metric": term, "source": "analysis_recipe"})
    return result


def _recipe_retrieval_jobs(recipe: dict[str, Any], metadata: dict[str, Any], question: str, date_value: str) -> list[dict[str, Any]]:
    jobs = []
    aliases = recipe.get("source_aliases_by_family") if isinstance(recipe.get("source_aliases_by_family"), dict) else {}
    columns_by_family = recipe.get("required_columns_by_family") if isinstance(recipe.get("required_columns_by_family"), dict) else {}
    for family in _text_list(recipe.get("required_dataset_families")):
        dataset_key = _dataset_for_recipe_family(family, metadata, question)
        if not dataset_key:
            continue
        alias = str(aliases.get(family) or f"{family}_data")
        catalog = _dataset_catalog(metadata, dataset_key)
        required_columns = _text_list(columns_by_family.get(family)) or _default_required_columns(catalog)
        jobs.append(
            {
                "job_id": f"recipe_{str(recipe.get('default_analysis_kind') or 'analysis')}_{dataset_key}",
                "source_alias": alias,
                "dataset_key": dataset_key,
                "params": _params_for_recipe_dataset(catalog, date_value),
                "filters": _filters_for_recipe_dataset(catalog, metadata, question),
                "required_columns": required_columns,
                "purpose": f"analysis_recipe:{family}",
            }
        )
    return jobs


def _dataset_for_recipe_family(family: str, metadata: dict[str, Any], question: str) -> str:
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    candidates = [
        (str(dataset_key), item)
        for dataset_key, item in catalog.items()
        if isinstance(item, dict) and str(item.get("dataset_family") or "") == family
    ]
    if not candidates:
        return ""
    text = str(question or "").lower()
    wants_history = any(token in text for token in ["yesterday", "history"])
    if wants_history:
        for dataset_key, item in candidates:
            if str(item.get("date_scope") or "") == "history":
                return dataset_key
    for dataset_key, item in candidates:
        if str(item.get("date_scope") or "") == "current_day":
            return dataset_key
    return candidates[0][0]


def _dataset_catalog(metadata: dict[str, Any], dataset_key: str) -> dict[str, Any]:
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    item = catalog.get(dataset_key)
    return item if isinstance(item, dict) else {}


def _params_for_recipe_dataset(catalog: dict[str, Any], date_value: str) -> dict[str, Any]:
    required_params = catalog.get("required_params") if isinstance(catalog.get("required_params"), list) else []
    if "DATE" in required_params:
        return {"DATE": date_value}
    return {}


def _filters_for_recipe_dataset(catalog: dict[str, Any], metadata: dict[str, Any], question: str) -> list[dict[str, Any]]:
    mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    process_key = _process_group_key(question)
    if process_key and "OPER_NAME" in mappings:
        return [{"field": "OPER_NAME", "op": "in", "values": _process_values(metadata, process_key, question)}]
    return []


def _default_required_columns(catalog: dict[str, Any]) -> list[str]:
    columns = catalog.get("columns") if isinstance(catalog.get("columns"), list) else []
    return _text_list(columns)


def _recipe_step_plan(recipe: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
    template = recipe.get("step_plan_template") if isinstance(recipe.get("step_plan_template"), list) else []
    aliases = recipe.get("source_aliases_by_family") if isinstance(recipe.get("source_aliases_by_family"), dict) else {}
    steps = []
    for raw_step in template:
        if not isinstance(raw_step, dict):
            continue
        step = _expand_recipe_value(deepcopy(raw_step), top_n)
        family = str(step.pop("source_family", "") or "")
        if family and not step.get("source_alias"):
            step["source_alias"] = str(aliases.get(family) or f"{family}_data")
        steps.append(step)
    return steps


def _expand_recipe_value(value: Any, top_n: int) -> Any:
    if value == "$top_n":
        return top_n
    if isinstance(value, list):
        return [_expand_recipe_value(item, top_n) for item in value]
    if isinstance(value, dict):
        return {key: _expand_recipe_value(item, top_n) for key, item in value.items()}
    return value


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result
def _is_multi_step_wip_production_question(question: str) -> bool:
    q_upper = question.upper()
    return (
        ("DA" in q_upper or "D/A" in q_upper)
        and ("WB" in q_upper or "W/B" in q_upper)
        and "각각" in question
        and ("재공" in question or "WIP" in q_upper)
        and ("생산" in question or "PRODUCTION" in q_upper)
    )


def _is_process_production_wip_product_question(question: str) -> bool:
    q_upper = question.upper()
    if not _mentions_process_group(question):
        return False
    if not (("재공" in question or "WIP" in q_upper) and ("생산" in question or "실적" in question or "PRODUCTION" in q_upper)):
        return False
    if not ("제품" in question or "PRODUCT" in q_upper or "LPDDR5" in q_upper):
        return False
    if any(term in question for term in ["목표", "계획", "달성"]):
        return False
    rank_terms = ["상위", "하위", "가장", "많은", "적은", "최대", "최소", "랭크", "랭킹"]
    if any(term in question for term in rank_terms) or "TOP" in q_upper or "RANK" in q_upper:
        return False
    return True


def _mentions_da(question: str) -> bool:
    q_upper = question.upper()
    return "DA" in q_upper or "D/A" in q_upper


def _mentions_wb(question: str) -> bool:
    q_upper = question.upper()
    return "WB" in q_upper or "W/B" in q_upper


def _process_group_key(question: str) -> str:
    if _mentions_da(question):
        return "DA"
    if _mentions_wb(question):
        return "WB"
    return ""


def _mentions_process_group(question: str) -> bool:
    return bool(_process_group_key(question))


def _is_followup_equipment_question(question: str) -> bool:
    q_upper = question.upper()
    return ("이 제품" in question or "해당 제품" in question or "THIS PRODUCT" in q_upper) and (
        "장비" in question or "EQP" in q_upper or "EQUIPMENT" in q_upper
    )


def _is_equipment_count_question(question: str) -> bool:
    q_upper = question.upper()
    return (
        "장비 대수" in question
        or "설비 대수" in question
        or "장비 수" in question
        or "설비 수" in question
        or "장비수" in question
        or "설비수" in question
        or "몇 대" in question
        or "몇대" in question
        or "EQP_COUNT" in q_upper
        or "EQUIPMENT COUNT" in q_upper
    )


def _is_waiting_lot_count_question(question: str) -> bool:
    return "작업대기" in question and "LOT" in question.upper() and ("수량" in question or "몇" in question)


def _is_running_lot_count_question(question: str) -> bool:
    q_upper = question.upper()
    return ("작업중" in question or "작업 중" in question or "RUNNING" in q_upper) and "LOT" in q_upper and (
        "수량" in question or "몇" in question
    )


def _is_process_lot_wafer_die_question(question: str) -> bool:
    q_upper = question.upper()
    return _mentions_process_group(question) and "LOT" in q_upper and "WAFER" in q_upper and "DIE" in q_upper


def _is_hbm_equipment_question(question: str) -> bool:
    q_upper = question.upper()
    return "HBM" in q_upper and ("장비" in question or "EQP" in q_upper) and ("현황" in question or "보유" in question)


def _is_low_output_question(question: str) -> bool:
    return ("저조" in question or "미달" in question or "부족" in question) and (_mentions_da(question) or _mentions_wb(question))


def _is_date_split_production_plan_gap_question(question: str) -> bool:
    return "어제" in question and "오늘" in question and ("생산계획" in question or "계획" in question) and ("차이" in question or "BAL" in question.upper())


def _is_total_production_wip_target_question(question: str) -> bool:
    return "생산량" in question and "재공" in question and ("목표" in question or "계획" in question) and not (_mentions_da(question) or _mentions_wb(question))


def _is_wip_quantity_question(question: str) -> bool:
    q_upper = question.upper()
    if not ("재공" in question or "WIP" in q_upper):
        return False
    if "가장" in question or "상위" in question:
        return False
    return "수량" in question or "전체" in question or "합계" in question


def _extract_lot_id(question: str) -> str | None:
    match = re.search(r"\b[A-Z]\d{7}[A-Z0-9]+\b", question.upper())
    if not match:
        return None
    return match.group(0)


def _process_values(metadata: dict[str, Any], group_key: str, question: str) -> list[str]:
    group = metadata["domain_items"]["process_groups"][group_key]
    q_upper = question.upper()
    exact_values = [process for process in group["processes"] if process.upper() in q_upper]
    if exact_values:
        return exact_values
    return list(group["processes"])


def _previous_current_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    current_data = state.get("current_data") or {}
    if "rows" in current_data:
        return list(current_data.get("rows") or [])
    data = current_data.get("data") or {}
    return list(data.get("rows") or [])


def _extract_product_tuples(rows: list[dict[str, Any]], product_keys: list[str]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = {key: row.get(key) for key in product_keys if row.get(key) not in (None, "")}
        if not item:
            continue
        identity = tuple(item.get(key) for key in product_keys)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
    return result


def _date_with_dash(date_value: str) -> str:
    if len(date_value) == 8:
        return f"{date_value[0:4]}-{date_value[4:6]}-{date_value[6:8]}"
    return date_value
