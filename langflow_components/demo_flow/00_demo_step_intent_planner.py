from __future__ import annotations

import re
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


DEFAULT_SAMPLE_DATE = "20260612"


def plan_steps(payload: dict[str, Any]) -> dict[str, Any]:
    question = payload["request"]["question"]
    metadata = payload["metadata"]
    product_keys = list(metadata["domain_items"]["product_key_columns"])
    q_upper = question.upper()

    if _is_multi_step(question):
        intent_plan = _multi_step_plan(question, metadata, product_keys)
    elif "HOLD" in q_upper and "이력" in question:
        intent_plan = _hold_history_plan(question)
    elif "HOLD" in q_upper and "LOT" in q_upper:
        intent_plan = _hold_lot_plan(question)
    elif "이 제품" in question and ("장비" in question or "EQP" in q_upper):
        intent_plan = _equipment_followup_plan(question, payload.get("state", {}), product_keys)
    else:
        intent_plan = _single_wip_plan(question, metadata, product_keys)

    next_payload = dict(payload)
    next_payload["intent_plan"] = intent_plan
    next_payload["retrieval_jobs"] = intent_plan.get("retrieval_jobs", [])
    next_payload["metadata_context"] = _metadata_context(intent_plan)
    return next_payload


def _multi_step_plan(question: str, metadata: dict[str, Any], product_keys: list[str]) -> dict[str, Any]:
    da_processes = metadata["domain_items"]["process_groups"]["DA"]["processes"]
    wb_processes = metadata["domain_items"]["process_groups"]["WB"]["processes"]
    all_processes = sorted(set(da_processes + wb_processes))
    return {
        "intent_type": "multi_step_analysis",
        "analysis_kind": "rank_wip_then_join_production",
        "product_grain": product_keys,
        "requested_measures": ["WIP", "PRODUCTION"],
        "retrieval_jobs": [
            {
                "job_id": "job_wip_rank_source",
                "source_alias": "wip_today_rank_scope",
                "dataset_key": "wip_today",
                "params": {"DATE": DEFAULT_SAMPLE_DATE},
                "filters": [{"field": "OPER_NAME", "op": "in", "values": all_processes}],
                "required_columns": ["WORK_DT", "OPER_NAME", *product_keys, "WIP"],
                "purpose": "rank_source",
            },
            {
                "job_id": "job_production_for_ranked_products",
                "source_alias": "production_today_for_ranked_products",
                "dataset_key": "production_today",
                "params": {"DATE": DEFAULT_SAMPLE_DATE},
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
                    {"label": "DA", "field": "OPER_NAME", "values": da_processes},
                    {"label": "WB", "field": "OPER_NAME", "values": wb_processes},
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
                "output_ref": "production_by_ranked_product",
            },
            {
                "step_id": "join_rank_and_production",
                "operation": "join_previous_steps",
                "join_keys": product_keys,
                "output_ref": "final_result",
            },
        ],
    }


def _hold_history_plan(question: str) -> dict[str, Any]:
    lot_id = _extract_lot_id(question) or ""
    return {
        "intent_type": "detail_lookup",
        "analysis_kind": "detail_rows",
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


def _hold_lot_plan(question: str) -> dict[str, Any]:
    return {
        "intent_type": "detail_lookup",
        "analysis_kind": "detail_rows",
        "retrieval_jobs": [
            {
                "job_id": "job_current_hold_lots",
                "source_alias": "current_hold_lots",
                "dataset_key": "lot_status",
                "params": {},
                "filters": [{"field": "LOT_HOLD_STAT_CD", "op": "in", "values": ["HOLD", "OnHold"]}],
                "required_columns": ["LOT_ID", "OPER_SHORT_DESC", "LOT_STAT_CD", "LOT_HOLD_STAT_CD"],
                "purpose": "detail_rows",
            }
        ],
        "step_plan": [
            {
                "step_id": "return_current_hold_lots",
                "operation": "detail_rows",
                "source_alias": "current_hold_lots",
                "columns": ["LOT_ID", "OPER_SHORT_DESC", "LOT_STAT_CD", "LOT_HOLD_STAT_CD"],
            }
        ],
    }


def _equipment_followup_plan(question: str, state: dict[str, Any], product_keys: list[str]) -> dict[str, Any]:
    rows = (state.get("current_data") or {}).get("rows") or (state.get("current_data") or {}).get("data", {}).get("rows") or []
    product_tuples = []
    for row in rows:
        item = {key: row.get(key) for key in product_keys if row.get(key) not in (None, "")}
        if item and item not in product_tuples:
            product_tuples.append(item)
    return {
        "intent_type": "followup_transform",
        "analysis_kind": "equipment_for_previous_products",
        "product_grain": product_keys,
        "state_product_keys": product_tuples,
        "retrieval_jobs": [
            {
                "job_id": "job_equipment_for_previous_products",
                "source_alias": "equipment_for_previous_products",
                "dataset_key": "equipment_status",
                "params": {},
                "filters": [{"field": "PRODUCT_GRAIN", "op": "tuple_in", "values": product_tuples}],
                "required_columns": ["EQPID", "EQP_MODEL", "PRESS_CNT", *product_keys, "LOT_ID", "RECIPE_ID"],
                "purpose": "followup_detail_rows",
            }
        ],
        "step_plan": [
            {"step_id": "load_previous_product_keys", "operation": "read_state_current_data"},
            {
                "step_id": "filter_equipment_by_previous_products",
                "operation": "detail_rows_for_product_keys",
                "source_alias": "equipment_for_previous_products",
            },
        ],
    }


def _single_wip_plan(question: str, metadata: dict[str, Any], product_keys: list[str]) -> dict[str, Any]:
    da_processes = metadata["domain_items"]["process_groups"]["DA"]["processes"]
    return {
        "intent_type": "single_retrieval_analysis",
        "analysis_kind": "rank_top_n",
        "product_grain": product_keys,
        "retrieval_jobs": [
            {
                "job_id": "job_wip_rank",
                "source_alias": "wip_today_rank",
                "dataset_key": "wip_today",
                "params": {"DATE": DEFAULT_SAMPLE_DATE},
                "filters": [{"field": "OPER_NAME", "op": "in", "values": da_processes}],
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
                "top_n": 1,
                "group_by": product_keys,
            }
        ],
    }


def _is_multi_step(question: str) -> bool:
    q_upper = question.upper()
    return ("DA" in q_upper or "D/A" in q_upper) and ("WB" in q_upper or "W/B" in q_upper) and "각각" in question


def _extract_lot_id(question: str) -> str | None:
    match = re.search(r"\b[A-Z]\d{7}[A-Z0-9]+\b", question.upper())
    return match.group(0) if match else None


def _metadata_context(intent_plan: dict[str, Any]) -> dict[str, Any]:
    dataset_keys = []
    filter_keys = []
    for job in intent_plan.get("retrieval_jobs", []):
        if job["dataset_key"] not in dataset_keys:
            dataset_keys.append(job["dataset_key"])
        for condition in job.get("filters", []):
            field = condition.get("field")
            if field and field not in filter_keys:
                filter_keys.append(field)
    return {
        "domain_refs": [{"key": "product_grain", "columns": intent_plan.get("product_grain", [])}],
        "table_refs": [{"dataset_key": key} for key in dataset_keys],
        "filter_refs": [{"filter_key": key} for key in filter_keys],
    }



class StepIntentPlanner(Component):
    display_name = "00 Demo Step Intent Planner"
    description = "Fallback/demo planner for local checks without a Langflow LLM node."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        payload = getattr(self.payload, "data", self.payload)
        return Data(data=plan_steps(payload))
