from __future__ import annotations

from typing import Any

import pandas as pd


def run_analysis(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    analysis_kind = plan.get("analysis_kind")
    if analysis_kind == "rank_wip_then_join_production":
        return _rank_wip_then_join_production(plan, runtime_sources)
    if analysis_kind == "detail_rows":
        return _detail_rows(plan, runtime_sources)
    if analysis_kind == "rank_top_n":
        return _rank_top_n(plan, runtime_sources)
    if analysis_kind == "equipment_for_previous_products":
        return _equipment_for_previous_products(plan, runtime_sources)
    if analysis_kind == "equipment_count_for_previous_products":
        return _equipment_count_for_previous_products(plan, runtime_sources)
    if analysis_kind == "aggregate_join":
        return _aggregate_join(plan, runtime_sources)
    if analysis_kind == "production_wip_target_rate":
        return _production_wip_target_rate(plan, runtime_sources)
    if analysis_kind == "lot_count_by_process":
        return _lot_count_by_process(plan, runtime_sources)
    if analysis_kind == "lot_quantity_summary":
        return _lot_quantity_summary(plan, runtime_sources)
    if analysis_kind == "aggregate_wip_total":
        return _aggregate_wip_total(plan, runtime_sources)
    if analysis_kind == "low_output_vs_target":
        return _low_output_vs_target(plan, runtime_sources)
    if analysis_kind == "date_split_production_plan_gap":
        return _date_split_production_plan_gap(plan, runtime_sources)
    if analysis_kind == "overall_production_wip_target":
        return _overall_production_wip_target(plan, runtime_sources)
    if analysis_kind == "equipment_by_model":
        return _equipment_by_model(plan, runtime_sources)
    step_plan_result = _run_step_plan_if_supported(plan, runtime_sources)
    if step_plan_result is not None:
        return step_plan_result
    return _empty_result(plan, f"Unsupported analysis_kind: {analysis_kind}")


def _rows_for_dataset(
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
    dataset_key: str,
    fallback_aliases: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    for job in plan.get("retrieval_jobs", []):
        if not isinstance(job, dict) or str(job.get("dataset_key") or "") != dataset_key:
            continue
        alias = str(job.get("source_alias") or "")
        if alias in runtime_sources:
            return runtime_sources.get(alias, [])
    for alias in fallback_aliases:
        if alias in runtime_sources:
            return runtime_sources.get(alias, [])
    return []


def _rank_wip_then_join_production(
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    rank_step = plan["step_plan"][0]
    wip_df = pd.DataFrame(runtime_sources.get(rank_step["source_alias"], []))
    prod_df = pd.DataFrame(runtime_sources.get("production_today_for_ranked_products", []))

    if wip_df.empty:
        return _empty_result(plan, "No WIP rows found for rank step")

    wip_df["RANK_GROUP"] = wip_df["OPER_NAME"].apply(lambda value: _rank_group_for_process(value, rank_step["rank_groups"]))
    wip_df = wip_df[wip_df["RANK_GROUP"].notna()].copy()
    ranked = _sum_by(wip_df, ["RANK_GROUP", *product_keys], "WIP")
    ranked["WIP_RANK"] = ranked.groupby("RANK_GROUP")["WIP"].rank(method="first", ascending=False).astype(int)
    ranked = ranked[ranked["WIP_RANK"] <= int(rank_step["top_n"])].copy()
    ranked = ranked.sort_values(["RANK_GROUP", "WIP_RANK", "WIP"], ascending=[True, True, False])

    if prod_df.empty:
        production = pd.DataFrame(columns=[*product_keys, "PRODUCTION"])
    else:
        ranked_keys = _key_frame(ranked, product_keys)
        production_source = prod_df.merge(ranked_keys, on=product_keys, how="inner")
        production = _sum_by(production_source, product_keys, "PRODUCTION")

    final = ranked.merge(production, on=product_keys, how="left")
    final["PRODUCTION"] = final["PRODUCTION"].fillna(0).astype(int)
    final = final[["RANK_GROUP", "WIP_RANK", *product_keys, "WIP", "PRODUCTION"]]
    return _result(
        plan,
        final,
        analysis_code=(
            "wip_df -> assign RANK_GROUP -> groupby(RANK_GROUP, product_grain).sum(WIP) -> "
            "rank within each RANK_GROUP -> filter top_n -> production_df filtered by ranked product keys -> "
            "groupby(product_grain).sum(PRODUCTION) -> left join"
        ),
        intermediate_refs={
            "ranked_products": _preview_frame(ranked),
            "production_by_ranked_product": _preview_frame(production),
        },
    )


def _detail_rows(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    rows = runtime_sources.get(step["source_alias"], [])
    frame = pd.DataFrame(rows)
    columns = [column for column in step.get("columns", []) if column in frame.columns]
    if columns:
        frame = frame[columns]
    return _result(plan, frame, analysis_code="return detail rows with requested detail columns")


def _rank_top_n(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    product_keys = plan["product_grain"]
    frame = pd.DataFrame(runtime_sources.get(step["source_alias"], []))
    if frame.empty:
        return _empty_result(plan, "No rows found for rank step")
    metric = step["metric"]
    grouped = _sum_by(frame, product_keys, metric)
    grouped["RANK"] = grouped[metric].rank(method="first", ascending=False).astype(int)
    grouped = grouped[grouped["RANK"] <= int(step["top_n"])].sort_values("RANK")
    return _result(
        plan,
        grouped[[*product_keys, metric, "RANK"]],
        analysis_code=f"groupby(product_grain).sum({metric}) -> rank desc -> top_n",
    )


def _equipment_for_previous_products(
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    source_alias = plan["retrieval_jobs"][0]["source_alias"]
    frame = pd.DataFrame(runtime_sources.get(source_alias, []))
    if frame.empty:
        return _empty_result(plan, "No equipment rows found")
    product_tuples = plan.get("state_product_keys", [])
    if product_tuples:
        allowed = {tuple(item.get(key) for key in product_keys) for item in product_tuples}
        mask = frame.apply(lambda row: tuple(row.get(key) for key in product_keys) in allowed, axis=1)
        frame = frame[mask].copy()
    columns = ["EQPID", "EQP_MODEL", "PRESS_CNT", *product_keys, "LOT_ID", "RECIPE_ID"]
    columns = [column for column in columns if column in frame.columns]
    return _result(
        plan,
        frame[columns],
        analysis_code="read previous product grain from state -> filter equipment rows by product tuple -> detail rows",
    )


def _equipment_count_for_previous_products(
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    source_alias = plan["retrieval_jobs"][0]["source_alias"]
    frame = pd.DataFrame(runtime_sources.get(source_alias, []))
    if frame.empty:
        return _empty_result(plan, "No equipment rows found")
    product_tuples = plan.get("state_product_keys", [])
    if product_tuples:
        allowed = {tuple(item.get(key) for key in product_keys) for item in product_tuples}
        mask = frame.apply(lambda row: tuple(row.get(key) for key in product_keys) in allowed, axis=1)
        frame = frame[mask].copy()
    if frame.empty:
        return _empty_result(plan, "No equipment rows matched previous product keys")
    if product_keys:
        result = frame.groupby(product_keys, dropna=False)["EQPID"].nunique().reset_index(name="EQP_COUNT")
    else:
        result = pd.DataFrame([{"EQP_COUNT": int(frame["EQPID"].nunique())}])
    return _result(
        plan,
        result[[*product_keys, "EQP_COUNT"]],
        analysis_code="read previous product grain from state -> filter equipment rows -> EQP_COUNT = EQPID.nunique()",
    )


def _aggregate_join(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    prod_rows = _rows_for_dataset(plan, runtime_sources, "production_today")
    wip_rows = _rows_for_dataset(plan, runtime_sources, "wip_today")
    prod = _sum_by(pd.DataFrame(prod_rows), product_keys, "PRODUCTION")
    wip = _sum_by(pd.DataFrame(wip_rows), product_keys, "WIP")
    final = prod.merge(wip, on=product_keys, how="outer").fillna({"PRODUCTION": 0, "WIP": 0})
    final["PRODUCTION"] = final["PRODUCTION"].astype(int)
    final["WIP"] = final["WIP"].astype(int)
    return _result(
        plan,
        final[[*product_keys, "PRODUCTION", "WIP"]],
        analysis_code="aggregate production and WIP by product grain -> outer join by product grain",
        intermediate_refs={"production_by_product": _preview_frame(prod), "wip_by_product": _preview_frame(wip)},
    )


def _production_wip_target_rate(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    production = _sum_by(pd.DataFrame(runtime_sources.get("scope_production_today", [])), product_keys, "PRODUCTION")
    wip = _sum_by(pd.DataFrame(runtime_sources.get("scope_wip_today", [])), product_keys, "WIP")
    target = _sum_by(pd.DataFrame(runtime_sources.get("scope_target", [])), product_keys, "OUT_PLAN")
    final = production.merge(wip, on=product_keys, how="outer").merge(target, on=product_keys, how="outer")
    for column in ["PRODUCTION", "WIP", "OUT_PLAN"]:
        final[column] = final[column].fillna(0).astype(float)
    final["ACHIEVEMENT_RATE"] = final.apply(
        lambda row: round((row["PRODUCTION"] / row["OUT_PLAN"] * 100), 2) if row["OUT_PLAN"] else 0,
        axis=1,
    )
    final[["PRODUCTION", "WIP", "OUT_PLAN"]] = final[["PRODUCTION", "WIP", "OUT_PLAN"]].astype(int)
    return _result(
        plan,
        final[[*product_keys, "PRODUCTION", "WIP", "OUT_PLAN", "ACHIEVEMENT_RATE"]],
        analysis_code=(
            "aggregate PRODUCTION/WIP/OUT_PLAN by product grain -> join -> "
            "ACHIEVEMENT_RATE = sum(PRODUCTION) / sum(OUT_PLAN) * 100"
        ),
    )


def _lot_count_by_process(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    frame = pd.DataFrame(runtime_sources.get(step["source_alias"], []))
    if frame.empty:
        return _empty_result(plan, "No lot rows found")
    result = (
        frame.groupby("OPER_SHORT_DESC", dropna=False)["LOT_ID"]
        .nunique()
        .reset_index(name="LOT_COUNT")
        .sort_values(["LOT_COUNT", "OPER_SHORT_DESC"], ascending=[False, True])
    )
    return _result(
        plan,
        result,
        analysis_code="groupby(OPER_SHORT_DESC).LOT_ID.nunique() -> LOT_COUNT",
    )


def _lot_quantity_summary(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    step = plan["step_plan"][0]
    frame = pd.DataFrame(runtime_sources.get(step["source_alias"], []))
    if frame.empty:
        return _empty_result(plan, "No lot rows found")
    scope_label = str(plan.get("scope_label") or "PROCESS")
    result = pd.DataFrame(
        [
            {
                "SCOPE": scope_label,
                "LOT_COUNT": int(frame["LOT_ID"].nunique()),
                "WF_QTY": int(pd.to_numeric(frame["WF_QTY"], errors="coerce").fillna(0).sum()),
                "DIE_QTY": int(pd.to_numeric(frame["SUB_PROD_QTY"], errors="coerce").fillna(0).sum()),
            }
        ]
    )
    return _result(
        plan,
        result,
        analysis_code="LOT_COUNT = LOT_ID.nunique(); WF_QTY/SUB_PROD_QTY aggregate by sum",
    )


def _aggregate_wip_total(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    frame = pd.DataFrame(runtime_sources.get("wip_total", []))
    total = int(pd.to_numeric(frame.get("WIP", pd.Series(dtype="float")), errors="coerce").fillna(0).sum())
    result = pd.DataFrame([{"SCOPE": plan.get("scope_label", "ALL"), "WIP": total}])
    return _result(plan, result, analysis_code="sum(WIP) for the requested scope")


def _low_output_vs_target(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    target_column = plan.get("target_column", "OUT_PLAN")
    threshold = float(plan.get("threshold_percent", 90.0))
    production = _sum_by(pd.DataFrame(runtime_sources.get("low_output_production", [])), product_keys, "PRODUCTION")
    target = _sum_by(pd.DataFrame(runtime_sources.get("low_output_target", [])), product_keys, target_column)
    final = production.merge(target, on=product_keys, how="outer")
    final["PRODUCTION"] = pd.to_numeric(final["PRODUCTION"], errors="coerce").fillna(0)
    final[target_column] = pd.to_numeric(final[target_column], errors="coerce").fillna(0)
    final["TARGET_QTY"] = final[target_column]
    final["ACHIEVEMENT_RATE"] = final.apply(
        lambda row: round((row["PRODUCTION"] / row["TARGET_QTY"] * 100), 2) if row["TARGET_QTY"] else 0,
        axis=1,
    )
    final["BALANCE"] = (final["TARGET_QTY"] - final["PRODUCTION"]).clip(lower=0)
    final["LOW_OUTPUT_FLAG"] = final["ACHIEVEMENT_RATE"] < threshold
    final = final[final["LOW_OUTPUT_FLAG"]].copy()
    for column in ["PRODUCTION", "TARGET_QTY", "BALANCE"]:
        final[column] = final[column].astype(int)
    final = final.sort_values(["ACHIEVEMENT_RATE", "BALANCE"], ascending=[True, False])
    return _result(
        plan,
        final[[*product_keys, "PRODUCTION", "TARGET_QTY", "ACHIEVEMENT_RATE", "BALANCE", "LOW_OUTPUT_FLAG"]],
        analysis_code=(
            "aggregate PRODUCTION and target by product grain -> "
            "ACHIEVEMENT_RATE = PRODUCTION / TARGET_QTY * 100 -> filter below threshold"
        ),
    )


def _date_split_production_plan_gap(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    product_keys = plan["product_grain"]
    production = _sum_by(pd.DataFrame(runtime_sources.get("yesterday_production", [])), product_keys, "PRODUCTION")
    target = _sum_by(pd.DataFrame(runtime_sources.get("today_target", [])), product_keys, "OUT_PLAN")
    final = production.merge(target, on=product_keys, how="outer")
    final["PRODUCTION"] = pd.to_numeric(final["PRODUCTION"], errors="coerce").fillna(0)
    final["OUT_PLAN"] = pd.to_numeric(final["OUT_PLAN"], errors="coerce").fillna(0)
    final["BALANCE"] = (final["OUT_PLAN"] - final["PRODUCTION"]).astype(int)
    final[["PRODUCTION", "OUT_PLAN"]] = final[["PRODUCTION", "OUT_PLAN"]].astype(int)
    return _result(
        plan,
        final[[*product_keys, "PRODUCTION", "OUT_PLAN", "BALANCE"]],
        analysis_code="yesterday production and today target keep separate dates -> join by product grain -> BALANCE",
    )


def _overall_production_wip_target(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    production = _sum_metric(runtime_sources.get("total_production_today", []), "PRODUCTION")
    wip = _sum_metric(runtime_sources.get("total_wip_today", []), "WIP")
    target = _sum_metric(runtime_sources.get("total_target", []), "OUT_PLAN")
    frame = pd.DataFrame([{"SCOPE": "ALL", "PRODUCTION": production, "WIP": wip, "OUT_PLAN": target}])
    return _result(plan, frame, analysis_code="sum each dataset independently and return one total row")


def _equipment_by_model(plan: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    frame = pd.DataFrame(runtime_sources.get("hbm_equipment_status", []))
    if frame.empty:
        return _empty_result(plan, "No HBM equipment rows found")
    frame["PRESS_CNT"] = pd.to_numeric(frame["PRESS_CNT"], errors="coerce").fillna(0)
    result = (
        frame.groupby("EQP_MODEL", dropna=False)
        .agg(EQP_COUNT=("EQPID", "nunique"), PRESS_CNT=("PRESS_CNT", "sum"))
        .reset_index()
        .sort_values(["PRESS_CNT", "EQP_MODEL"], ascending=[False, True])
    )
    result["PRESS_CNT"] = result["PRESS_CNT"].astype(int)
    return _result(
        plan,
        result,
        analysis_code="filter HBM equipment rows -> groupby(EQP_MODEL).agg(EQP_COUNT=nunique, PRESS_CNT=sum)",
    )



def _run_step_plan_if_supported(
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    if not steps:
        return None
    supported = {
        "rank_top_n",
        "aggregate",
        "aggregate_by_group",
        "aggregate_metric",
        "aggregate_sum",
        "aggregate_sum_by_group",
        "sum_by_group",
        "equipment_count_by_product",
        "unique_count_by_group",
        "nunique_by_group",
        "hold_lot_in_tat_by_process",
        "left_join",
    }
    if any(str(step.get("operation") or "") not in supported for step in steps if isinstance(step, dict)):
        return None

    frames_by_step: dict[str, pd.DataFrame] = {}
    last_frame: pd.DataFrame | None = None
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return None
        operation = str(step.get("operation") or "")
        if operation == "rank_top_n":
            frame = _step_rank_top_n(step, plan, runtime_sources, frames_by_step)
        elif operation in {"aggregate", "aggregate_by_group", "aggregate_metric", "aggregate_sum", "aggregate_sum_by_group", "sum_by_group"}:
            frame = _step_aggregate(step, plan, runtime_sources, frames_by_step)
        elif operation in {"equipment_count_by_product", "unique_count_by_group", "nunique_by_group"}:
            frame = _step_unique_count(step, runtime_sources, frames_by_step)
        elif operation == "hold_lot_in_tat_by_process":
            frame = _step_hold_lot_in_tat(step, runtime_sources, frames_by_step)
        elif operation == "left_join":
            frame = _step_left_join(step, frames_by_step)
        else:
            return None
        if frame is None:
            return None
        step_id = str(step.get("step_id") or f"step_{index + 1}")
        frames_by_step[step_id] = frame
        last_frame = frame

    if last_frame is None:
        return None
    output_columns = _step_output_columns({"output_columns": plan.get("analysis_output_columns")}) or _step_output_columns(steps[-1])
    final = _select_step_columns(last_frame, output_columns)
    return _result(
        plan,
        final,
        analysis_code="execute metadata analysis_recipe step_plan primitives",
        intermediate_refs={name: _preview_frame(frame) for name, frame in frames_by_step.items()},
    )


def _step_rank_top_n(
    step: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    metric = str(step.get("metric") or plan.get("metric") or "").strip()
    if not metric or metric not in frame.columns:
        return None
    work = frame.copy()
    work[metric] = pd.to_numeric(work[metric], errors="coerce").fillna(0)
    group_by = _available_columns(work, step.get("group_by"))
    if group_by:
        result = work.groupby(group_by, dropna=False, as_index=False)[metric].sum()
    else:
        result = work
    ascending = str(step.get("rank_order") or plan.get("rank_order") or "desc").lower() in {"asc", "ascending"}
    result = result.sort_values(metric, ascending=ascending).head(_top_n_for_step(step, plan))
    result = _apply_step_renames(result, step)
    return _select_step_columns(result, _step_output_columns(step))


def _step_aggregate(
    step: dict[str, Any],
    plan: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    metrics = _step_metric_columns(step, plan, frame)
    if not metrics:
        return None
    aggregation = _step_aggregation(step)
    if not aggregation:
        return None
    group_by = _available_columns(frame, step.get("group_by"))
    work = frame.copy()
    if aggregation in {"sum", "mean", "max", "min"}:
        for metric in metrics:
            work[metric] = pd.to_numeric(work[metric], errors="coerce")
        if aggregation == "sum":
            work[metrics] = work[metrics].fillna(0)
    if group_by:
        result = work.groupby(group_by, dropna=False, as_index=False)[metrics].agg(aggregation)
    else:
        result = pd.DataFrame([{metric: _aggregate_series(work[metric], aggregation) for metric in metrics}])
    result = _apply_metric_output_aliases(result, step, metrics, group_by)
    result = _apply_step_renames(result, step)
    return _select_step_columns(result, _step_output_columns(step))


def _step_unique_count(
    step: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    count_column = str(step.get("count_column") or "").strip()
    if not count_column or count_column not in frame.columns:
        return None
    group_by = _available_columns(frame, step.get("group_by"))
    output_column = _count_output_column(step, group_by)
    if group_by:
        result = frame.groupby(group_by, dropna=False)[count_column].nunique().reset_index(name=output_column)
    else:
        result = pd.DataFrame([{output_column: frame[count_column].nunique()}])
    return _select_step_columns(result, _step_output_columns(step))


def _step_hold_lot_in_tat(
    step: dict[str, Any],
    runtime_sources: dict[str, list[dict[str, Any]]],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame | None:
    frame = _frame_for_step_source(step, runtime_sources)
    if frame is None:
        return None
    frame = _filter_frame_from_previous_step(frame, step, frames_by_step)
    group_by = _available_columns(frame, step.get("group_by"))
    if not group_by:
        return None
    count_column = str(step.get("count_column") or "LOT_ID").strip()
    tat_column = str(step.get("tat_column") or "IN_TAT").strip()
    status_column = str(step.get("hold_status_column") or "LOT_HOLD_STAT_CD").strip()
    if count_column not in frame.columns or tat_column not in frame.columns:
        return None
    work = frame.copy()
    work[tat_column] = pd.to_numeric(work[tat_column], errors="coerce")
    base = work[group_by].drop_duplicates()
    if status_column in work.columns:
        status = work[status_column].astype(str).str.upper().str.replace(" ", "", regex=False)
        hold_mask = status.isin({"HOLD", "ONHOLD", "Y", "YES", "TRUE"})
    else:
        hold_mask = pd.Series(False, index=work.index)
    hold_counts = work[hold_mask].groupby(group_by, dropna=False)[count_column].nunique().reset_index(name="HOLD_LOT_COUNT")
    avg_in_tat = work.groupby(group_by, dropna=False)[tat_column].mean().reset_index(name="AVG_IN_TAT")
    result = base.merge(hold_counts, on=group_by, how="left").merge(avg_in_tat, on=group_by, how="left")
    result["HOLD_LOT_COUNT"] = result["HOLD_LOT_COUNT"].fillna(0).astype(int)
    return _select_step_columns(result, _step_output_columns(step))


def _step_left_join(step: dict[str, Any], frames_by_step: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    left_step = str(step.get("left_step") or "").strip()
    right_step = str(step.get("right_step") or "").strip()
    if not left_step or not right_step or left_step not in frames_by_step or right_step not in frames_by_step:
        return None
    left = frames_by_step[left_step]
    right = frames_by_step[right_step]
    join_keys = _step_join_keys(step, left, right)
    if not join_keys:
        return None
    result = left.merge(right, on=join_keys, how="left")
    for column in _step_output_columns(step):
        if column not in result.columns:
            result[column] = 0 if column.endswith("_COUNT") else None
    return _select_step_columns(result, _step_output_columns(step))


def _frame_for_step_source(step: dict[str, Any], runtime_sources: dict[str, list[dict[str, Any]]]) -> pd.DataFrame | None:
    alias = str(step.get("source_alias") or "").strip()
    if not alias or alias not in runtime_sources:
        return None
    return pd.DataFrame(runtime_sources.get(alias, []))


def _filter_frame_from_previous_step(
    frame: pd.DataFrame,
    step: dict[str, Any],
    frames_by_step: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    previous_step_id = str(step.get("filter_from_step") or "").strip()
    if previous_step_id and previous_step_id in frames_by_step:
        previous = frames_by_step[previous_step_id]
    elif frames_by_step:
        previous = next(reversed(frames_by_step.values()))
    else:
        return frame
    join_keys = _step_join_keys(step, frame, previous)
    if not join_keys:
        default_keys = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "TSV_DIE_TYP"]
        join_keys = [column for column in default_keys if column in frame.columns and column in previous.columns]
    if not join_keys:
        return frame
    selected = previous[join_keys].drop_duplicates()
    return frame.merge(selected, on=join_keys, how="inner")


def _step_join_keys(step: dict[str, Any], left: pd.DataFrame, right: pd.DataFrame) -> list[str]:
    raw_keys = step.get("join_keys") if isinstance(step.get("join_keys"), list) else []
    if not raw_keys and step.get("join_key"):
        raw_keys = [step.get("join_key")]
    return [str(key) for key in raw_keys if str(key) in left.columns and str(key) in right.columns]


def _available_columns(frame: pd.DataFrame, columns: Any) -> list[str]:
    return [str(column) for column in columns if str(column) in frame.columns] if isinstance(columns, list) else []


def _step_metric_columns(step: dict[str, Any], plan: dict[str, Any], frame: pd.DataFrame) -> list[str]:
    candidates: list[Any] = []
    raw_metrics = step.get("metrics") if isinstance(step.get("metrics"), list) else []
    candidates.extend(raw_metrics)
    for key in ("metric", "value_column", "measure_column", "quantity_column"):
        if step.get(key):
            candidates.append(step.get(key))
    if isinstance(plan.get("metrics"), list):
        candidates.extend(plan.get("metrics", []))
    if plan.get("metric"):
        candidates.append(plan.get("metric"))
    if not candidates:
        group_by = set(_available_columns(frame, step.get("group_by")))
        output_columns = _step_output_columns(step) or _step_output_columns({"output_columns": plan.get("analysis_output_columns")})
        candidates.extend(column for column in output_columns if str(column) not in group_by)
    return _unique_columns([str(column) for column in candidates if str(column) in frame.columns])


def _step_aggregation(step: dict[str, Any]) -> str:
    raw_value = str(step.get("aggregation") or step.get("agg") or step.get("agg_func") or "sum").strip().lower()
    aliases = {
        "avg": "mean",
        "average": "mean",
        "count_distinct": "nunique",
        "distinct_count": "nunique",
        "total": "sum",
        "unique_count": "nunique",
    }
    value = aliases.get(raw_value, raw_value)
    return value if value in {"count", "max", "mean", "min", "nunique", "sum"} else ""


def _aggregate_series(series: pd.Series, aggregation: str) -> Any:
    if aggregation == "sum":
        return pd.to_numeric(series, errors="coerce").fillna(0).sum()
    if aggregation == "mean":
        return pd.to_numeric(series, errors="coerce").mean()
    if aggregation == "max":
        return pd.to_numeric(series, errors="coerce").max()
    if aggregation == "min":
        return pd.to_numeric(series, errors="coerce").min()
    if aggregation == "count":
        return series.count()
    if aggregation == "nunique":
        return series.nunique()
    return None


def _apply_metric_output_aliases(
    frame: pd.DataFrame,
    step: dict[str, Any],
    metrics: list[str],
    group_by: list[str],
) -> pd.DataFrame:
    if len(metrics) != 1:
        return frame
    metric = metrics[0]
    output_column = str(step.get("output_column") or "").strip()
    if output_column and output_column not in frame.columns:
        return frame.rename(columns={metric: output_column})
    output_columns = _step_output_columns(step)
    metric_outputs = [column for column in output_columns if column not in group_by]
    if len(metric_outputs) == 1 and metric_outputs[0] != metric and metric_outputs[0] not in frame.columns:
        return frame.rename(columns={metric: metric_outputs[0]})
    return frame


def _top_n_for_step(step: dict[str, Any], plan: dict[str, Any]) -> int:
    value = step.get("top_n", plan.get("top_n", 1))
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return 1


def _apply_step_renames(frame: pd.DataFrame, step: dict[str, Any]) -> pd.DataFrame:
    renames = step.get("rename_columns") if isinstance(step.get("rename_columns"), dict) else {}
    if not renames:
        return frame
    return frame.rename(columns={str(source): str(target) for source, target in renames.items()})


def _step_output_columns(step: dict[str, Any]) -> list[str]:
    columns = step.get("output_columns") if isinstance(step.get("output_columns"), list) else []
    return [str(column) for column in columns if str(column or "").strip()]


def _select_step_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if not columns:
        return frame
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = 0 if column.endswith("_COUNT") else None
    return result[columns]


def _count_output_column(step: dict[str, Any], group_by: list[str]) -> str:
    explicit = str(step.get("output_column") or "").strip()
    if explicit:
        return explicit
    for column in _step_output_columns(step):
        if column not in group_by:
            return column
    return "COUNT"


def _unique_columns(columns: list[str]) -> list[str]:
    result = []
    for column in columns:
        if column not in result:
            result.append(column)
    return result
def _sum_by(frame: pd.DataFrame, group_by: list[str], metric: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_by, metric])
    clean = frame.copy()
    clean[metric] = pd.to_numeric(clean[metric], errors="coerce").fillna(0)
    return clean.groupby(group_by, dropna=False, as_index=False)[metric].sum()


def _sum_metric(rows: list[dict[str, Any]], metric: str) -> int:
    frame = pd.DataFrame(rows)
    if frame.empty or metric not in frame:
        return 0
    return int(pd.to_numeric(frame[metric], errors="coerce").fillna(0).sum())


def _rank_group_for_process(process_name: Any, rank_groups: list[dict[str, Any]]) -> str | None:
    for group in rank_groups:
        if process_name in set(group.get("values", [])):
            return group["label"]
    return None


def _key_frame(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=keys)
    return frame[keys].drop_duplicates()


def _result(
    plan: dict[str, Any],
    frame: pd.DataFrame,
    analysis_code: str,
    intermediate_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = frame.to_dict(orient="records")
    return {
        "status": "ok",
        "analysis_kind": plan.get("analysis_kind"),
        "analysis_code": analysis_code,
        "columns": list(frame.columns),
        "rows": rows,
        "row_count": len(rows),
        "intermediate_refs": intermediate_refs or {},
        "errors": [],
    }


def _empty_result(plan: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "status": "empty",
        "analysis_kind": plan.get("analysis_kind"),
        "analysis_code": "",
        "columns": [],
        "rows": [],
        "row_count": 0,
        "intermediate_refs": {},
        "errors": [message],
    }


def _preview_frame(frame: pd.DataFrame, limit: int = 5) -> dict[str, Any]:
    return {"row_count": len(frame), "columns": list(frame.columns), "preview_rows": frame.head(limit).to_dict(orient="records")}
