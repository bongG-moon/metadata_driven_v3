# 파일 설명: 14 Pandas Prompt Builder Langflow custom component 파일입니다.
# 흐름 역할: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_pandas_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    if payload.get("direct_response_ready"):
        prompt = json.dumps(
            {
                "code": "result_df = pd.DataFrame([])",
                "output_columns": [],
                "reasoning_steps": ["Direct metadata response already prepared; pandas execution should pass through."],
            },
            ensure_ascii=False,
        )
        return {"prompt": prompt, "payload": payload, "prompt_type": "direct_response_skip", "source_summary": {}}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}
    source_summary = _source_summary(runtime_sources, plan)
    source_filters = _filters_by_source(plan)

    prompt = "\n".join(
        [
            "You are the pandas code generation node for a Langflow manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Generate Python pandas code that uses only the provided variables: pd, sources, plan, state.",
            "sources is a dict mapping source_alias to pandas DataFrame.",
            "Use only source aliases that are actual keys in sources/source summaries, normally retrieval_jobs[*].source_alias. Do not invent generic aliases.",
            "plan and state are Python dicts. Use plan['key'], plan.get('key'), state.get('key'); never use plan.key or state.key.",
            "The code must assign the final pandas DataFrame to result_df.",
            "Final result columns must use the standard contract names requested by the normalized plan.",
            "Before this code runs, each source DataFrame is converted to a standardized pandas analysis view.",
            "Physical source columns listed in table_catalog.filter_mappings/required_param_mappings/standard_column_aliases are renamed to the standard names used by the plan.",
            "For joins, grouping, ranking, and output shaping, use the standard analysis column names from plan.",
            "Do not expect both a physical column and its standard alias to remain in sources; use standard names from product_grain, group_by, join_keys, and analysis_output_columns.",
            "Use physical source column names only when the source summary shows that column and the plan explicitly asks for a source-only measure/detail column with no standard alias.",
            "Do not translate measure columns to Korean labels, and do not keep temporary names such as PRODUCTION_sum, WIP_sum, OUT_PLAN_sum, or lowercase rank in result_df.",
            "Do not import modules. Do not read/write files. Do not use network, OS, eval, exec, open, or subprocess.",
            "Do not use numpy, np, or np.where. Use pandas Series operations such as div, fillna, where, mask, and boolean comparisons.",
            "Do not use pd.inf, float('inf'), or infinity replacement. Avoid division by zero with boolean masks before dividing.",
            "Do not use .to_frame() in generated code. For one total row with multiple metrics, build result_df with pd.DataFrame([{...}]).",
            "Do not use DataFrame.agg(named_metric=(column, func)).to_frame().T; DataFrame.agg can already return a DataFrame and then to_frame will fail.",
            "When combining scalar totals from multiple sources with no group_by, create one DataFrame row directly instead of merging DataFrames with no common key.",
            "If the generated code contains any import statement, the safety check will fail.",
            "",
            "Sequential plan execution rules:",
            "- Source retrieval applies only required source parameters such as DATE or LOT_ID. Apply every retrieval_jobs[*].filters condition inside the pandas code before aggregation/ranking/joining.",
            "- For filters, use the source_alias matching the retrieval job. Support op='eq', op='in', op='not_empty'/'exists', and ignore only PRODUCT_GRAIN/from_state filters that are explicitly state-driven.",
            "- Read plan['step_plan'] and implement every step in order; do not collapse a multi-step plan into only the easiest count or groupby.",
            "- Maintain a local dict named step_outputs. After every step, store the step DataFrame as step_outputs[step_id], and read previous steps from step_outputs for downstream filtering/joining.",
            "- Preserve intermediate DataFrames for ranked/filtering steps, then use them in later filtering, aggregation, and join steps.",
            "- If a step ranks top_n rows, perform that ranking before downstream metrics that depend on the ranked scope.",
            "- Treat step_plan operations as reusable primitives: aggregate_sum/aggregate_by_group groups by step.group_by and aggregates step.metric or step.metrics; rank_top_n groups/sorts by step fields; equipment_count_by_product counts step.count_column.nunique by group_by; hold_lot_in_tat_by_process calculates metrics from step fields; left_join joins named previous steps by join_key/join_keys.",
            "- For any rank step, aggregate the rank metric at the intended grain before sorting. Use step.group_by when present; if group_by is absent and step.grain is product, use plan['product_grain']; if the intent is total rank, use no group_by.",
            "- Do not add retrieval filter fields to group_by just because those columns exist in the source. Filter fields are grouping columns only when the user explicitly asked for that raw breakdown axis.",
            "- For rank_groups/per-group ranking, build the group label from step.rank_groups, aggregate by that group label plus the target entity grain, rank separately within each group label, and keep only the planned user-facing label/output columns in result_df.",
            "- For dependent lookup/aggregate steps after a rank step, restrict the later source to the ranked entity keys from step_outputs instead of re-ranking or grouping by filter columns.",
            "- Apply step.rename_columns when present before a later step references those renamed columns.",
            "- If the question or plan asks for multiple metrics, compute all of them and include every plan['analysis_output_columns'] column in result_df when source data exists.",
            "- If plan.matched_metric_terms or plan.metric_definitions contains formula/pandas_code_instructions, compute the derived row-level output columns first, then aggregate those output columns by step.group_by or total according to the aggregate step.",
            "- For aggregate steps with empty group_by, return one total row. For aggregate steps with group_by, return one row per requested group. Do not return row-level details for aggregate plans.",
            "- If plan.result_scope_columns exists, add each listed constant scope column to result_df unless result_df already has that column. These columns make aggregate rows self-describing, for example process group or product filter scope.",
            "- Do not include raw source/filter condition columns in result_df when they are only used to build rank_groups or filters. Use plan.rank_group_output_column/RANK_GROUP and result_scope columns as the user-facing group labels instead.",
            "- If generated output is missing required plan columns, the executor may replace it with a deterministic fallback.",
            "",
            "User question:",
            str(request.get("question") or ""),
            "",
            "Normalized intent plan:",
            json.dumps(plan, ensure_ascii=False, indent=2),
            "",
            "Available source DataFrames:",
            json.dumps(source_summary, ensure_ascii=False, indent=2),
            "",
            "Source filters to apply in pandas before analysis:",
            json.dumps(source_filters, ensure_ascii=False, indent=2),
            "",
            "Previous state summary:",
            json.dumps(_state_summary(state), ensure_ascii=False, indent=2),
            "",
            "Analysis instruction:",
            _analysis_instruction(plan),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "code": "Python code. It must set result_df.",
                    "output_columns": ["column names expected in result_df"],
                    "reasoning_steps": ["short reasoning steps"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "pandas_code", "source_summary": source_summary, "source_filters": source_filters}


def _analysis_instruction(plan: dict[str, Any]) -> str:
    kind = plan.get("analysis_kind")
    product_keys = plan.get("product_grain", [])
    if kind == "rank_wip_then_join_production":
        return (
            "Assign a user-facing group label from step_plan[0].rank_groups, aggregate WIP by that group label and product_grain, "
            "rank separately inside each group label, keep top_n, aggregate PRODUCTION for the ranked product keys, then left join. "
            "This is a multi-step question: first identify ranked products from WIP, then retrieve/aggregate production for those products. "
            "Use plan.rank_group_output_column as the final group label column when present, otherwise use RANK_GROUP. "
            "The raw rank_groups field is only for assigning labels and filtering; do not include it in the final result unless it is explicitly in analysis_output_columns. "
            f"The final result_df columns must be exactly [group label, 'WIP_RANK'] + product_grain {product_keys} "
            "+ ['WIP', 'PRODUCTION']. Do not output PRODUCTION_sum or rank."
        )
    if kind == "detail_rows":
        return (
            "Return detail source rows without aggregation or groupby. "
            "If step_plan[0].source_aliases exists, return rows from those aliases and add SOURCE_ALIAS so each row's source is clear; "
            "otherwise return the requested detail columns from step_plan[0].source_alias."
        )
    if kind == "rank_top_n":
        return (
            "First copy the step source DataFrame and apply that source_alias retrieval filters from plan['retrieval_jobs'] "
            "using pandas masks. Then aggregate the metric in step_plan[0].metric by "
            f"product_grain {product_keys}, rank descending, keep top_n."
        )
    if kind == "equipment_for_previous_products":
        return "Filter equipment rows by plan.state_product_keys using product_grain, then return equipment detail columns."
    if kind == "equipment_count_for_previous_products":
        return (
            "Filter equipment rows by plan.state_product_keys using product_grain, then calculate EQP_COUNT as EQPID.nunique(). "
            f"Return product_grain {product_keys} plus ['EQP_COUNT']; do not use lot_status for this calculation."
        )
    if kind == "aggregate_join":
        return (
            "Aggregate PRODUCTION and WIP from the exact retrieval job source aliases. "
            "If product_grain/group_by is empty, calculate scalar totals from each source and build one result row directly with pd.DataFrame([{...}]); "
            "do not merge scalar total DataFrames. If product_grain/group_by exists, aggregate each metric by that grain and outer join by that grain."
        )
    if kind == "production_wip_target_rate":
        return (
            "Aggregate PRODUCTION, WIP, and OUT_PLAN by product_grain, join them, and calculate ACHIEVEMENT_RATE. "
            f"The final result_df columns must be exactly product_grain {product_keys} plus "
            "['WIP', 'PRODUCTION', 'OUT_PLAN', 'ACHIEVEMENT_RATE']."
        )
    if kind == "low_output_vs_target":
        return (
            "Aggregate PRODUCTION and plan['target_column'] by product_grain. Rename the selected target measure "
            "to TARGET_QTY in the final result, even when the source column is INPUT_PLAN or OUT_PLAN. "
            "Calculate ACHIEVEMENT_RATE=PRODUCTION/TARGET_QTY, BALANCE=PRODUCTION-TARGET_QTY, and "
            "LOW_OUTPUT_FLAG=ACHIEVEMENT_RATE < plan.get('threshold', 1.0). "
            "When TARGET_QTY is zero, set ACHIEVEMENT_RATE to 0 using boolean masks; do not use pd.inf, float('inf'), numpy, or np.where. "
            f"The final result_df columns must be exactly product_grain {product_keys} plus "
            "['PRODUCTION', 'TARGET_QTY', 'ACHIEVEMENT_RATE', 'BALANCE', 'LOW_OUTPUT_FLAG']."
        )
    if kind == "lot_count_by_process":
        return "Group lot_status rows by OPER_SHORT_DESC and calculate LOT_COUNT as LOT_ID.nunique()."
    if kind == "top_wip_process_hold_lot_in_tat":
        return (
            "This is a sequential process-level analysis. Step 1: from the WIP source, group by OPER_NAME, "
            "sum WIP, sort descending, keep step_plan[0].top_n, and rename the process output column to OPER_SHORT_DESC. "
            "Step 2: from the lot_status source, use only rows whose OPER_SHORT_DESC/OPER_NAME is in those top processes; "
            "calculate HOLD_LOT_COUNT as LOT_ID.nunique() where LOT_HOLD_STAT_CD means HOLD/ONHOLD, and calculate "
            "AVG_IN_TAT as the numeric mean of IN_TAT for the selected process rows. Step 3: left join the lot metrics "
            "to the ranked WIP result and return exactly ['OPER_SHORT_DESC', 'WIP', 'HOLD_LOT_COUNT', 'AVG_IN_TAT']."
        )
    if kind == "lot_quantity_summary":
        return (
            "Return one row with LOT_COUNT=LOT_ID.nunique(), WF_QTY=sum(WF_QTY), DIE_QTY=sum(SUB_PROD_QTY). "
            "The final result_df columns must be exactly ['LOT_COUNT', 'WF_QTY', 'DIE_QTY']."
        )
    if kind == "aggregate_wip_total":
        return "Return one row with SCOPE=plan.scope_label or ALL and WIP=sum(WIP)."
    if kind == "aggregate_previous_source":
        return (
            "Use the restored previous runtime source rows, not a new retrieval. "
            "Read rows from step_plan[0].source_alias when present, otherwise use the first available source. "
            "Group by step_plan[0].group_by or product_grain, sum plan.metric, and return the group columns plus the metric. "
            "If group_by is empty, return one total row for the metric."
        )
    if kind == "overall_production_wip_target":
        return (
            "Sum PRODUCTION, WIP, and OUT_PLAN independently and return one row. "
            "Do not rename OUT_PLAN to TARGET. The final result_df columns must include ['PRODUCTION', 'WIP', 'OUT_PLAN']; "
            "if you add SCOPE, set it to ALL."
        )
    if kind == "date_split_production_plan_gap":
        return (
            "Aggregate yesterday PRODUCTION and today OUT_PLAN by product_grain, join by product_grain, and calculate "
            "BALANCE=OUT_PLAN-PRODUCTION. In the final result, keep the measure columns named PRODUCTION, OUT_PLAN, "
            f"and BALANCE. The final result_df columns must be exactly product_grain {product_keys} plus "
            "['PRODUCTION', 'OUT_PLAN', 'BALANCE']; do not use names like yesterday_PRODUCTION or today_OUT_PLAN."
        )
    if kind == "equipment_by_model":
        return (
            "Group equipment rows by EQP_MODEL, calculate EQP_COUNT=EQPID.nunique() and PRESS_CNT=sum(PRESS_CNT). "
            "The final result_df columns must be exactly ['EQP_MODEL', 'EQP_COUNT', 'PRESS_CNT']; "
            "do not rename PRESS_CNT to TOTAL_PRESS_CNT and do not omit EQP_COUNT."
        )
    if _is_top_wip_product_oldest_lot_plan(plan):
        return (
            "This is a sequential multi-source analysis. First aggregate WIP from the WIP source by product_grain "
            f"{product_keys}, sort WIP descending, and keep the top product. Then filter lot_status rows to that "
            "same product key, sort IN_TAT descending, and keep the top 1 oldest LOT. Return product_grain plus "
            "['WIP', 'LOT_ID', 'IN_TAT']. Do not return an empty contract DataFrame unless the actual source rows "
            "are empty after performing these steps."
        )
    return (
        "Use the normalized intent plan and step_plan to perform the requested pandas analysis over the provided "
        "source DataFrames. Do not create an empty contract DataFrame unless the real source rows are empty after "
        "applying the plan."
    )


def _is_top_wip_product_oldest_lot_plan(plan: dict[str, Any]) -> bool:
    kind = str(plan.get("analysis_kind") or "").lower()
    if kind in {
        "top_wip_product_oldest_lot",
        "wip_top_product_oldest_lot",
        "top_wip_product_lot_in_tat",
        "oldest_lot_for_top_wip_product",
    }:
        return True
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    has_wip = any(_job_matches_dataset(job, "wip") for job in jobs if isinstance(job, dict))
    has_lot = any(_job_matches_dataset(job, "lot") for job in jobs if isinstance(job, dict))
    step_text = json.dumps(plan.get("step_plan") or [], ensure_ascii=False).lower()
    return has_wip and has_lot and "in_tat" in step_text and "wip" in step_text


def _job_matches_dataset(job: dict[str, Any], token: str) -> bool:
    text = " ".join(str(job.get(key) or "") for key in ("dataset_key", "source_alias", "purpose")).lower()
    return token in text


def _source_summary(runtime_sources: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    summary = {}
    for alias, rows in runtime_sources.items():
        clean_rows = rows if isinstance(rows, list) else []
        preview_rows = _standardize_preview_rows(str(alias), clean_rows[:5], plan)
        summary[str(alias)] = {
            "row_count": len(clean_rows),
            "columns": _columns_from_rows(preview_rows),
            "preview_rows": preview_rows,
        }
    return summary


def _standardize_preview_rows(alias: str, rows: list[Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    aliases = _standard_aliases_for_source(alias, plan)
    result_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result = deepcopy(row)
        for standard, candidates in aliases.items():
            standard_text = str(standard or "").strip()
            if not standard_text:
                continue
            candidate_columns = [
                str(candidate)
                for candidate in candidates
                if str(candidate or "").strip()
                and str(candidate) != standard_text
                and str(candidate) in result
            ]
            if not candidate_columns:
                continue
            if standard_text in result:
                for candidate in candidate_columns:
                    if _is_blank(result.get(standard_text)) and not _is_blank(result.get(candidate)):
                        result[standard_text] = result.get(candidate)
                    result.pop(candidate, None)
                continue
            rename_source = candidate_columns[0]
            result[standard_text] = result.pop(rename_source)
            for candidate in candidate_columns[1:]:
                result.pop(candidate, None)
        result_rows.append(result)
    return result_rows


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for column in row:
            column_text = str(column or "").strip()
            if column_text and column_text not in columns:
                columns.append(column_text)
    return columns


def _standard_aliases_for_source(alias: str, plan: dict[str, Any]) -> dict[str, list[str]]:
    job = _job_for_source_alias(alias, plan)
    aliases: dict[str, list[str]] = {}
    standard_candidates = _standard_columns_from_plan(plan)
    if isinstance(job, dict):
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mapping = job.get(field) if isinstance(job.get(field), dict) else {}
            for standard, candidates in mapping.items():
                standard_text = str(standard or "").strip()
                if not standard_text or standard_text not in standard_candidates:
                    continue
                if not isinstance(candidates, list):
                    candidates = [candidates]
                aliases.setdefault(standard_text, [])
                aliases[standard_text].extend(str(item) for item in candidates if str(item or "").strip())
    return {key: _unique_columns([item for item in values if item != key]) for key, values in aliases.items()}


def _job_for_source_alias(alias: str, plan: dict[str, Any]) -> dict[str, Any]:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_alias = str(job.get("source_alias") or job.get("dataset_key") or "")
        if job_alias == alias:
            return job
    return {}


def _standard_columns_from_plan(plan: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    for key in ("product_grain", "analysis_output_columns"):
        value = plan.get(key)
        if isinstance(value, list):
            columns.extend(str(item) for item in value if str(item or "").strip())
    steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        for key in ("group_by", "join_keys", "output_columns"):
            value = step.get(key)
            if isinstance(value, list):
                columns.extend(str(item) for item in value if str(item or "").strip())
        for key in ("metric", "target_column", "count_column"):
            value = str(step.get(key) or "").strip()
            if value:
                columns.append(value)
    for key in ("metric", "target_column", "production_column"):
        value = str(plan.get(key) or "").strip()
        if value:
            columns.append(value)
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        required_columns = job.get("required_columns") if isinstance(job.get("required_columns"), list) else []
        columns.extend(str(item) for item in required_columns if str(item or "").strip())
        params = job.get("params") if isinstance(job.get("params"), dict) else {}
        columns.extend(str(key) for key in params.keys() if str(key or "").strip())
        filters = job.get("filters") if isinstance(job.get("filters"), list) else []
        for condition in filters:
            if not isinstance(condition, dict):
                continue
            field = str(condition.get("field") or "").strip()
            if field and field != "PRODUCT_GRAIN":
                columns.append(field)
    return _unique_columns(columns)


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _unique_columns(columns: list[str]) -> list[str]:
    result = []
    for column in columns:
        if column not in result:
            result.append(column)
    return result


def _filters_by_source(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        alias = str(job.get("source_alias") or job.get("dataset_key") or "").strip()
        filters = job.get("filters") if isinstance(job.get("filters"), list) else []
        if alias and filters:
            result[alias] = deepcopy([item for item in filters if isinstance(item, dict)])
    return result


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = _rows_from_current_data(current_data)
    return {
        "has_state": bool(state),
        "context": state.get("context", {}),
        "current_data_columns": current_data.get("columns", []),
        "current_data_row_count": current_data.get("row_count", 0),
        "current_data_preview_rows": rows[:3],
        "current_data_product_key_columns": current_data.get("product_key_columns", []),
        "current_data_product_key_values": _list_preview(current_data.get("product_key_values"), 20),
        "current_data_product_key_count": current_data.get("product_key_count", 0),
        "followup_source_results": state.get("followup_source_results", []),
    }


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _rows_from_current_data(current_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = current_data.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    data = current_data.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    return []


def _list_preview(value: Any, limit: int) -> list[Any]:
    return deepcopy(value[:limit]) if isinstance(value, list) else []


# 컴포넌트 설명: 14 Pandas Prompt Builder
# Langflow 표시 설명: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
class PandasPromptBuilder(Component):

    display_name = "14 Pandas Prompt Builder"
    description = "의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="pandas_prompt", display_name="Pandas Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt(self) -> Message:
        prompt_payload = build_pandas_prompt_payload(getattr(self, "payload", None))

        self.status = {
            "prompt_type": prompt_payload.get("prompt_type", "pandas_code"),
            "chars": len(prompt_payload["prompt"]),
            "sources": list(prompt_payload.get("source_summary", {}).keys()),
        }
        return Message(text=prompt_payload["prompt"])

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt_payload(self) -> Data:
        return Data(data=build_pandas_prompt_payload(getattr(self, "payload", None)))
