# 파일 설명: 02 Intent Prompt Builder Langflow custom component 파일입니다.
# 흐름 역할: 질문, 메타데이터, 이전 state를 바탕으로 의도 분석 LLM에 보낼 프롬프트와 context payload를 만듭니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


SUPPORTED_ANALYSIS_KINDS = [
    "rank_wip_then_join_production",
    "detail_rows",
    "rank_top_n",
    "equipment_for_previous_products",
    "equipment_count_for_previous_products",
    "aggregate_join",
    "production_wip_target_rate",
    "low_output_vs_target",
    "lot_count_by_process",
    "lot_quantity_summary",
    "aggregate_wip_total",
    "overall_production_wip_target",
    "date_split_production_plan_gap",
    "equipment_by_model",
    "none",
]


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 질문, 메타데이터, 이전 state를 바탕으로 의도 분석 LLM에 보낼 프롬프트와 context payload를 만듭니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_intent_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    if _direct_response_ready(payload):
        prompt = json.dumps(
            {
                "intent_type": "metadata_lookup",
                "analysis_kind": ((payload.get("metadata_qa") or {}).get("metadata_action") or "none")
                if isinstance(payload.get("metadata_qa"), dict)
                else "none",
                "route": (payload.get("intent_plan") or {}).get("route", "metadata_qa")
                if isinstance(payload.get("intent_plan"), dict)
                else "metadata_qa",
                "reasoning_steps": ["Direct metadata response already prepared; downstream normalizer should pass through."],
            },
            ensure_ascii=False,
        )
        return {"prompt": prompt, "payload": payload, "prompt_type": "direct_response_skip"}
    question = str((payload.get("request") or {}).get("question") or "")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    request_date = _request_date(payload)
    prompt = "\n".join(
        [
            "You are the intent planning node for a metadata-driven manufacturing data agent.",
            "This prompt will be sent to a Langflow Gemini/LLM node, and that node must return the intent JSON.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Think like a manufacturing analyst: split complex questions into ordered data/analysis steps.",
            "Use the provided metadata. Do not invent dataset keys or filter fields.",
            "Resolve product/status words through domain metadata product_terms/status_terms before choosing filters.",
            "Resolve metric words through domain metadata metric_terms and quantity_terms before choosing datasets.",
            "Use domain metadata analysis_recipes when the question matches a known analysis pattern.",
            "",
            "Current date parameter:",
            request_date,
            "",
            "Supported analysis_kind values:",
            json.dumps(SUPPORTED_ANALYSIS_KINDS, ensure_ascii=False),
            "",
            "Metadata summary:",
            json.dumps(_metadata_summary(metadata, request_date), ensure_ascii=False, indent=2),
            "",
            "Previous state summary:",
            json.dumps(_state_summary(state), ensure_ascii=False, indent=2),
            "",
            "User question:",
            question,
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "intent_type": "single_retrieval_analysis | multi_source_analysis | multi_step_analysis | detail_lookup | followup_transform | finish",
                    "analysis_kind": "one supported analysis_kind",
                    "datasets": ["dataset_key"],
                    "params_by_dataset": {
                        "dataset_key": {
                            "DATE": "copy metadata.datasets[dataset_key].date_param_value_for_current_request exactly",
                            "LOT_ID": "optional",
                        }
                    },
                    "filters": [{"field": "metadata filter field", "op": "eq|in|not_in|not_empty|empty|starts_with|last_char_in|tuple_in", "value": "optional", "values": []}],
                    "product_grain": ["columns used for product/process grouping, or [] for total/detail rows"],
                    "metric": "standard metric column for ranking/aggregation, such as WIP or PRODUCTION",
                    "top_n": "positive integer for top/rank questions",
                    "rank_order": "desc | asc",
                    "analysis_output_columns": ["standard result columns expected after pandas, optional"],
                    "retrieval_jobs": [
                        {
                            "dataset_key": "dataset key from metadata",
                            "source_alias": "short unique alias",
                            "purpose": "why this data is needed",
                            "params": {},
                            "filters": [],
                            "required_columns": ["dataset physical/source columns needed for retrieval"],
                            "required_param_mappings": {"DATE": ["physical column copied from metadata"]},
                            "filter_mappings": {"standard logical column": ["dataset physical/source columns copied from metadata"]},
                            "standard_column_aliases": {"standard logical column": ["dataset physical/source columns copied from metadata"]},
                            "date_format": "copy metadata.datasets[dataset_key].date_format when present",
                            "pandas_preprocessing": {"standardize_columns": True},
                        }
                    ],
                    "step_plan": [
                        {
                            "step_id": "short id",
                            "operation": "analysis operation",
                            "source_alias": "source alias",
                            "metric": "optional metric column",
                            "top_n": "optional positive integer",
                            "rank_order": "optional desc|asc",
                            "grain": "optional semantic grain such as product, process, lot, device, total, or detail",
                            "rank_groups": [{"label": "requested group label", "field": "metadata-backed source/filter field", "values": ["source values included in this group"]}],
                            "rank_group_output_column": "optional final output column for rank group labels, e.g. OPER_GROUP when grouping OPER_NAME-derived process groups",
                            "group_by": ["optional grouping columns"],
                            "output_columns": ["optional standard result columns"],
                        }
                    ],
                    "depends_on_state": False,
                    "requires_full_previous_result_restore": False,
                    "previous_result_restore_mode": "summary | full",
                    "reasoning_steps": ["short Korean or English reasoning step"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "Rules:",
            "- Use intent_type=detail_lookup for detail row requests such as a specific LOT hold history or hold lot list.",
            "- If the user asks for 상세 데이터, 세부 데이터, 원본 row, 전체 row, or says not to aggregate/group, preserve source rows with analysis_kind=detail_rows instead of forcing group_by.",
            "- Do not confuse 전체 수량/전체 실적/총/합계 with 전체 데이터. 전체 데이터/raw/original/detail asks for detail_rows, but 전체 수량/전체 실적/총/합계 asks for one aggregated total row.",
            "- For metric or quantity questions without 별/별로/per/by/rank/detail/raw wording, default to aggregate total: group_by=[], one result row, and sum every additive output metric.",
            "- For 제품별/product-by questions, group by product_grain. For 차수별/공정 차수별 questions, group by OPER_NUM. For 세부공정별/세부 공정별/process-step questions, group by OPER_NAME.",
            "- If a metric term defines derived output_columns such as WAFER_OUT_QTY and FAIL_UNIT_QTY, compute those row-level columns first and then aggregate them at the requested grain. Do not return row-level derived values unless detail_rows was explicitly requested.",
            "- Use intent_type=single_retrieval_analysis for one-dataset aggregation/ranking questions.",
            "- Use intent_type=multi_source_analysis for questions that need multiple datasets.",
            "- Use intent_type=multi_step_analysis when one step creates keys that the next step must reuse.",
            "- If analysis_kind=rank_wip_then_join_production, intent_type must be multi_step_analysis.",
            "- Always return retrieval_jobs for every dataset in datasets unless intent_type=finish. Do not return only datasets/params/filters.",
            "- Always return step_plan for analysis requests unless intent_type=finish. The step_plan must say which operation uses which source_alias.",
            "- step_plan[].source_alias and step_plan[].source_aliases must exactly match retrieval_jobs[].source_alias values. Do not invent generic aliases that are not present in retrieval_jobs.",
            "- DATE params are dataset-specific execution parameters. Add retrieval_jobs[].params.DATE only when that dataset metadata has DATE in required_params/required_param_mappings.",
            "- If DATE exists only in table_catalog.filter_mappings, treat it as an optional filter. Add retrieval_jobs[].filters DATE only when the user explicitly asks a date-scoped question such as today/yesterday/current/a concrete date.",
            "- Do not add DATE params or DATE filters for a raw/detail dataset lookup that does not ask for a date.",
            "- When DATE is required or explicitly requested as a filter, read metadata.datasets[dataset_key].date_format and date_param_value_for_current_request. Use that exact dataset-specific format.",
            f"- If a dataset date_format is YYYYMMDD, DATE must look like {_date_param_value_for_dataset(request_date, {'date_format': 'YYYYMMDD'})}. Do not output {_date_param_value_for_dataset(request_date, {'date_format': 'YYYY-MM-DD'})} for that dataset.",
            f"- If a dataset date_format is YYYY-MM-DD, DATE must look like {_date_param_value_for_dataset(request_date, {'date_format': 'YYYY-MM-DD'})}. Do not output {_date_param_value_for_dataset(request_date, {'date_format': 'YYYYMMDD'})} for that dataset.",
            "- Never copy target's YYYY-MM-DD format to production_today, wip_today, or other datasets unless that dataset's own metadata says YYYY-MM-DD.",
            "- When a retrieval job contains DATE params, also copy required_param_mappings and date_format from the dataset metadata into that retrieval_jobs item when present.",
            "- Keep product_grain, step_plan[].group_by, step_plan[].join_keys, and final output_columns in standard logical column names from metadata. Do not replace them with dataset-specific physical names such as PKG1, PKG2, DENSITY, or MCPSALENO.",
            "- In retrieval_jobs[].required_columns, request the dataset's physical/source columns from table_catalog.columns/filter_mappings/standard_column_aliases. The pandas stage standardizes source DataFrames before joins, grouping, ranking, and output shaping.",
            "- Copy table_catalog.filter_mappings and standard_column_aliases into each retrieval job when present, so physical columns such as PKG1/PKG2/MCPSALENO can be standardized to PKG_TYPE1/PKG_TYPE2/MCP_NO for pandas.",
            "- Use intent_type=followup_transform when the question says 이 제품/그 제품/해당 제품/이때/그때/방금 결과 and needs previous state.",
            "- For follow-up equipment questions, use only equipment_status unless the user explicitly asks for Lot, Hold, wafer, or die data.",
            "- For follow-up 장비 현황/설비 현황 questions, use analysis_kind=equipment_for_previous_products and return equipment detail rows.",
            "- For follow-up 장비 대수/설비 대수/몇 대 questions, use analysis_kind=equipment_count_for_previous_products and calculate EQP_COUNT as EQPID.nunique().",
            "- For follow-up 장비 대수/설비 대수/몇 대 questions, intent_type must be followup_transform, datasets must be exactly ['equipment_status'], and retrieval_jobs must contain only equipment_status. Do not use capacity for assigned equipment count.",
            "- For 장비 보유 현황/설비 보유 현황 by EQP_MODEL/model별 questions, use intent_type=single_retrieval_analysis, dataset equipment_status, and analysis_kind=equipment_by_model. Calculate EQP_COUNT as EQPID.nunique() and PRESS_CNT as sum(PRESS_CNT); do not use detail_rows unless the user asks for list/detail rows.",
            "- For follow-up questions that recalculate, filter, sort, regroup, or show detail rows from the previous result itself, set requires_full_previous_result_restore=true and previous_result_restore_mode=full.",
            "- For follow-up questions that ask to break down the same previous data by another dimension such as DEVICE/공정/제품, do not create new retrieval_jobs; set reuse_previous_runtime_sources=true, requires_full_previous_result_restore=true, previous_result_restore_mode=full, and use analysis_kind=aggregate_previous_source when a metric should be summed.",
            "- For follow-up questions that only need previous product keys for a new retrieval, keep previous_result_restore_mode=summary.",
            "- For 오늘/현재, prefer datasets whose metadata date_scope is current_day unless the question asks for history.",
            "- For 목표/계획, use dataset families and quantity/metric terms from metadata, and preserve each dataset's date_format.",
            "- For status or detail requests, use status_terms and table_catalog metadata instead of hardcoded status codes.",
            "- For 작업대기/작업중 Lot 수량 questions, use lot_status with the matching status_terms value and calculate LOT_COUNT as LOT_ID.nunique().",
            "- If a question asks lot count plus wafer count plus die quantity for a process group such as DA or WB, use lot_status with that process group's metadata filters and analysis_kind=lot_quantity_summary.",
            "- If a question asks LPDDR5 or another product condition plus DA/WB production and WIP together, use production_today and wip_today with the process group filters and analysis_kind=aggregate_join.",
            "- If a question asks production/실적/생산량 and WIP/재공 together by product/product별 for a process group, and it does not ask for top/rank/상위/가장 or target/목표/계획/달성률, use production_today + wip_today with analysis_kind=aggregate_join and group by product_grain.",
            "- For top/bottom/rank questions, do not return a nested rank object. Put ranking values in top-level metric/top_n/rank_order and repeat them in the rank step_plan item.",
            "- For 가장 많은/most/highest/top questions without an explicit count, use top_n=1 and rank_order=desc.",
            "- For top/bottom/rank questions followed by a dependent lookup, express rank first and dependent retrieval/analysis steps second.",
            "- Separate filter scope from grouping grain. A column used only to select rows must stay in retrieval_jobs[].filters or rank_groups[].field, not in group_by/output_columns.",
            "- Filter scope columns such as date, shift, process group, process name, or status may appear in result_scope_columns or final output as labels when they help identify the filtered result.",
            "- However, do not use filter-only scope columns as group_by/join_keys unless the user explicitly asks for that raw breakdown axis, such as 조별, 일자별, 공정별, 상태별, or raw/detail rows.",
            "- For total questions over a filtered scope, set step_plan[].group_by=[] and join_keys=[]; show scope labels with result_scope_columns/output_columns instead of joining/grouping by DATE, SHIFT, OPER_NAME, or other filter-only columns.",
            "- Choose group_by from the entity being ranked or aggregated: product questions use product_grain, raw process/operation columns only when the user explicitly asks for raw process/step breakdown, and total questions use an empty group_by.",
            "- When the user compares A versus B scopes, such as INPUT versus B/G1 or DA versus WB, create separate source-specific retrieval_jobs filters and step_plan outputs for each scope. Do not put the B scope filter on the A source or merge both scopes into one ambiguous OPER_NAME IN filter.",
            "- For sequential questions such as 'find the top product in yesterday DP, then show today's DA WIP', the first retrieval job gets only the DP/yesterday filters and the second retrieval job gets only the DA/today filters. Never add the union of all mentioned process groups to every retrieval job.",
            "- When a question asks the same measures for multiple process groups, aggregate each process-group scope separately and return user-facing columns such as DA_PRODUCTION, DA_WIP, WB_PRODUCTION, WB_WIP rather than a single combined PRODUCTION/WIP pair.",
            "- When the user says 전 공정/전체 공정/all process for one metric source, do not apply a process filter to that source. Keep process filters only on the source aliases whose scope explicitly names that process.",
            "- Product terms such as HBM, MOBILE, or AUTO향 are filter conditions. Keep their raw condition fields in filters only, and add a user-facing PRODUCT_GROUP result label instead of outputting raw condition values such as TSV_DIE_TYP=NOT_EMPTY.",
            "- If the ranked or aggregated entity is DEVICE, group/rank by DEVICE. Do not replace DEVICE with product_grain just because a product filter such as MOBILE is present.",
            "- If the user asks top/rank results for each requested group/scope (각각, 각, 별로, per each), express that grouping intent with step_plan[].rank_groups.",
            "- For per-group product ranking, group/rank by the user-facing group label plus product_grain; do not rank separately by the raw condition field unless the user requested that raw field as the breakdown axis.",
            "- For rank_groups, use the raw metadata-backed field only in rank_groups[].field and retrieval filters. Do not include that raw field in final output_columns unless the user explicitly asks to break down by that raw field.",
            "- Give rank group labels a user-facing final column via rank_group_output_column/output_columns. For example, if rank_groups[].field is OPER_NAME but the user asks for DA/WB groups, use OPER_GROUP in final output_columns rather than OPER_NAME.",
            "- For top/rank questions followed by a dependent lookup, count, detail, or oldest/longest selection, prefer a matching metadata analysis_recipes item and express the rank step before the dependent step.",
            "- For dependent counts, preserve the count source and count_column from metadata instead of substituting another dataset.",
            "- Do not use loose top-level group_by/output_columns as substitutes for step_plan. Use product_grain and analysis_output_columns, and include group_by/output_columns inside the relevant step when needed.",
            "- Use aggregate_wip_total only for one-dataset total/sum questions that metadata identifies as WIP/current quantity work.",
            "- Use aggregate_join only for a simple multi-source join when no matching analysis_recipes item gives a more specific plan.",
            "- If an analysis_recipes item matches the question, use its required_quantity_terms, required_dataset_families, metric_terms, grain_policy, source_aliases_by_family, defaults, and output_columns as planning evidence.",
            "- grain_policy decides grouping: aggregate_total means one total row; question_or_product_grain means use the grain explicitly requested by the question, otherwise use the product grain only when product-level rows are natural.",
            "- If a required dataset, filter, formula, or value mapping is not present in metadata, do not hardcode it. Return the closest metadata-backed plan and explain the missing item in reasoning_steps.",
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "intent"}


def _metadata_summary(metadata: dict[str, Any], request_date: str) -> dict[str, Any]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = {}
    for key, item in (table_catalog.get("datasets") or {}).items():
        if not isinstance(item, dict):
            continue
        datasets[key] = {
            "family": item.get("dataset_family"),
            "date_scope": item.get("date_scope", ""),
            "source_type": item.get("source_type"),
            "required_params": item.get("required_params", []),
            "required_param_mappings": item.get("required_param_mappings", {}),
            "date_format": _dataset_date_format(item),
            "date_param_value_for_current_request": _date_param_value_for_dataset(request_date, item),
            "quantity": item.get("primary_quantity_column"),
            "filter_fields": sorted((item.get("filter_mappings") or {}).keys()),
            "filter_mappings": item.get("filter_mappings", {}),
            "standard_column_aliases": item.get("standard_column_aliases", {}),
            "columns": item.get("columns", []),
        }
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    return {
        "process_groups": domain.get("process_groups", {}),
        "product_terms": domain.get("product_terms", {}),
        "quantity_terms": domain.get("quantity_terms", {}),
        "metric_terms": domain.get("metric_terms", {}),
        "analysis_recipes": domain.get("analysis_recipes", {}),
        "status_terms": domain.get("status_terms", {}),
        "product_key_columns": domain.get("product_key_columns", []),
        "datasets": datasets,
    }


def _dataset_date_format(dataset: dict[str, Any]) -> str:
    explicit = str(dataset.get("date_format") or "").strip()
    if explicit:
        return explicit
    date_keys = set(dataset.get("required_params") or [])
    if isinstance(dataset.get("required_param_mappings"), dict):
        date_keys.update(dataset["required_param_mappings"].keys())
    if isinstance(dataset.get("filter_mappings"), dict):
        date_keys.update(dataset["filter_mappings"].keys())
    if "DATE" in date_keys:
        return "YYYYMMDD"
    return ""


def _date_param_value_for_dataset(request_date: str, dataset: dict[str, Any]) -> str:
    fmt = _dataset_date_format(dataset)
    clean = str(request_date or "").strip().replace("-", "").replace("/", "").replace(".", "")
    if not clean:
        return ""
    if fmt == "YYYY-MM-DD" and len(clean) == 8:
        return f"{clean[0:4]}-{clean[4:6]}-{clean[6:8]}"
    if fmt == "YYYY/MM/DD" and len(clean) == 8:
        return f"{clean[0:4]}/{clean[4:6]}/{clean[6:8]}"
    if fmt == "YYYY.MM.DD" and len(clean) == 8:
        return f"{clean[0:4]}.{clean[4:6]}.{clean[6:8]}"
    return clean


def _request_date(payload: dict[str, Any]) -> str:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    date_value = str(request.get("date") or request.get("request_date") or "").strip()
    return (date_value or _runtime_reference_date()).replace("-", "")


def _runtime_reference_date() -> str:
    try:
        zoneinfo = import_module("zoneinfo")
        return datetime.now(zoneinfo.ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    except Exception:
        return datetime.now().strftime("%Y%m%d")


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


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


def _direct_response_ready(payload: dict[str, Any]) -> bool:
    return bool(payload.get("direct_response_ready"))


# 컴포넌트 설명: 02 Intent Prompt Builder
# Langflow 표시 설명: 질문, 메타데이터, 이전 state를 바탕으로 의도 분석 LLM에 보낼 프롬프트와 context payload를 만듭니다.
class IntentPromptBuilder(Component):

    display_name = "02 Intent Prompt Builder"
    description = "질문, 메타데이터, 이전 state를 바탕으로 의도 분석 LLM에 보낼 프롬프트와 context payload를 만듭니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="intent_prompt", display_name="Intent Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 질문, 메타데이터, 이전 state를 바탕으로 의도 분석 LLM에 보낼 프롬프트와 context payload를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt(self) -> Message:
        prompt_payload = build_intent_prompt_payload(getattr(self, "payload", None))

        self.status = {"prompt_type": prompt_payload.get("prompt_type", "intent"), "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 질문, 메타데이터, 이전 state를 바탕으로 의도 분석 LLM에 보낼 프롬프트와 context payload를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt_payload(self) -> Data:
        return Data(data=build_intent_prompt_payload(getattr(self, "payload", None)))
