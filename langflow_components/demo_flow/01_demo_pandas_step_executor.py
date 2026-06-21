from __future__ import annotations

from typing import Any

import pandas as pd

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def execute_pandas_steps(payload: dict[str, Any]) -> dict[str, Any]:
    plan = payload["intent_plan"]
    sources = payload.get("runtime_sources", {})
    kind = plan.get("analysis_kind")
    if kind == "rank_wip_then_join_production":
        result = _rank_wip_then_join_production(plan, sources)
    elif kind == "detail_rows":
        result = _detail_rows(plan, sources)
    elif kind == "rank_top_n":
        result = _rank_top_n(plan, sources)
    elif kind == "equipment_for_previous_products":
        result = _equipment_for_previous_products(plan, sources)
    else:
        result = {"status": "empty", "columns": [], "rows": [], "row_count": 0, "errors": [f"Unsupported kind: {kind}"]}
    next_payload = dict(payload)
    next_payload["analysis"] = result
    return next_payload


def _rank_wip_then_join_production(plan: dict[str, Any], sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    step = plan["step_plan"][0]
    wip = pd.DataFrame(sources.get(step["source_alias"], []))
    production = pd.DataFrame(sources.get("production_today_for_ranked_products", []))
    if wip.empty:
        return _empty("No WIP rows found")
    wip["RANK_GROUP"] = wip["OPER_NAME"].apply(lambda value: _rank_group(value, step["rank_groups"]))
    ranked = _sum_by(wip[wip["RANK_GROUP"].notna()], ["RANK_GROUP", *product_keys], "WIP")
    ranked["WIP_RANK"] = ranked.groupby("RANK_GROUP")["WIP"].rank(method="first", ascending=False).astype(int)
    ranked = ranked[ranked["WIP_RANK"] <= int(step["top_n"])]
    ranked_keys = ranked[product_keys].drop_duplicates()
    prod_sum = _sum_by(production.merge(ranked_keys, on=product_keys, how="inner"), product_keys, "PRODUCTION")
    final = ranked.merge(prod_sum, on=product_keys, how="left").fillna({"PRODUCTION": 0})
    final["PRODUCTION"] = final["PRODUCTION"].astype(int)
    final = final.sort_values(["RANK_GROUP", "WIP_RANK"])
    return _ok(final[["RANK_GROUP", "WIP_RANK", *product_keys, "WIP", "PRODUCTION"]], "rank -> dependent aggregate -> join")


def _detail_rows(plan: dict[str, Any], sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    frame = pd.DataFrame(sources.get(step["source_alias"], []))
    columns = [column for column in step.get("columns", []) if column in frame.columns]
    if columns:
        frame = frame[columns]
    return _ok(frame, "detail rows")


def _rank_top_n(plan: dict[str, Any], sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    product_keys = plan["product_grain"]
    frame = pd.DataFrame(sources.get(step["source_alias"], []))
    grouped = _sum_by(frame, product_keys, step["metric"])
    grouped["RANK"] = grouped[step["metric"]].rank(method="first", ascending=False).astype(int)
    grouped = grouped[grouped["RANK"] <= int(step["top_n"])]
    return _ok(grouped[[*product_keys, step["metric"], "RANK"]], "aggregate -> rank")


def _equipment_for_previous_products(plan: dict[str, Any], sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    frame = pd.DataFrame(sources.get("equipment_for_previous_products", []))
    allowed = {tuple(item.get(key) for key in product_keys) for item in plan.get("state_product_keys", [])}
    if allowed and not frame.empty:
        frame = frame[frame.apply(lambda row: tuple(row.get(key) for key in product_keys) in allowed, axis=1)]
    columns = [column for column in ["EQPID", "EQP_MODEL", "PRESS_CNT", *product_keys, "LOT_ID", "RECIPE_ID"] if column in frame.columns]
    return _ok(frame[columns], "state product grain -> equipment detail")


def _sum_by(frame: pd.DataFrame, group_by: list[str], metric: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_by, metric])
    clean = frame.copy()
    clean[metric] = pd.to_numeric(clean[metric], errors="coerce").fillna(0)
    return clean.groupby(group_by, dropna=False, as_index=False)[metric].sum()


def _rank_group(process_name: str, rank_groups: list[dict[str, Any]]) -> str | None:
    for group in rank_groups:
        if process_name in set(group.get("values", [])):
            return group["label"]
    return None


def _ok(frame: pd.DataFrame, analysis_code: str) -> dict[str, Any]:
    rows = frame.to_dict(orient="records")
    return {
        "status": "ok",
        "analysis_code": analysis_code,
        "columns": list(frame.columns),
        "rows": rows,
        "row_count": len(rows),
        "errors": [],
    }


def _empty(message: str) -> dict[str, Any]:
    return {"status": "empty", "analysis_code": "", "columns": [], "rows": [], "row_count": 0, "errors": [message]}



class PandasStepExecutor(Component):
    display_name = "01 Demo Pandas Step Executor"
    description = "Fallback/demo pandas executor for local checks without a Langflow LLM node."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        payload = getattr(self.payload, "data", self.payload)
        return Data(data=execute_pandas_steps(payload))
