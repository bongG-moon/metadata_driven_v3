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
from lfx.io import DataInput, MessageTextInput, Output
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
def build_intent_prompt_payload(payload_value: Any, specialized_prompt_text: Any = "") -> dict[str, Any]:
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
                "reasoning_steps": ["메타데이터 직접 응답이 이미 준비되어 있으므로 downstream normalizer는 그대로 통과시키면 됩니다."],
            },
            ensure_ascii=False,
        )
        return {"prompt": prompt, "payload": payload, "prompt_type": "direct_response_skip"}
    question = str((payload.get("request") or {}).get("question") or "")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    request_date = _request_date(payload)
    specialized_prompt = _specialized_prompt(specialized_prompt_text)
    prompt = "\n".join(
        [
            "당신은 metadata-driven 제조 데이터 에이전트의 intent planning 노드입니다.",
            "이 프롬프트는 Langflow Gemini/LLM 노드로 전달되며, 해당 노드는 intent JSON을 반환해야 합니다.",
            "반드시 하나의 엄격한 JSON object만 반환하세요. markdown 코드블록으로 감싸지 마세요.",
            "제조 분석가처럼 생각해서 복잡한 질문을 순서가 있는 data/analysis step으로 나누세요.",
            "제공된 metadata만 사용하세요. dataset key나 filter field를 임의로 만들지 마세요.",
            "dataset, filter, metric, helper case를 선택하기 전에 사용자 표현을 domain metadata로 먼저 해석하세요.",
            "질문이 알려진 분석 패턴과 맞으면 domain metadata의 recipe와 extension rule을 계획 근거로 사용하세요.",
            "",
            "현재 날짜 파라미터:",
            request_date,
            "",
            "지원하는 analysis_kind 값:",
            json.dumps(SUPPORTED_ANALYSIS_KINDS, ensure_ascii=False),
            "",
            "메타데이터 요약:",
            json.dumps(_metadata_summary(metadata, request_date), ensure_ascii=False, indent=2),
            "",
            "이전 state 요약:",
            json.dumps(_state_summary(state), ensure_ascii=False, indent=2),
            "",
            "사용자 질문:",
            question,
            "",
            "추가 Specialized Prompt:",
            specialized_prompt,
            "",
            "필수 JSON schema:",
            json.dumps(
                {
                    "intent_type": "single_retrieval_analysis | multi_source_analysis | multi_step_analysis | detail_lookup | followup_transform | finish",
                    "analysis_kind": "지원되는 analysis_kind 중 하나",
                    "datasets": ["dataset_key"],
                    "params_by_dataset": {
                        "dataset_key": {
                            "DATE": "metadata.datasets[dataset_key].date_param_value_for_current_request 값을 정확히 복사",
                            "LOT_ID": "optional",
                        }
                    },
                    "filters": [{"field": "metadata의 filter field", "op": "eq|in|not_in|not_empty|empty|starts_with|last_char_in|tuple_in", "value": "optional", "values": []}],
                    "product_grain": ["entity grouping에 사용할 standard column, total/detail rows이면 []"],
                    "metric": "ranking/aggregation에 사용할 standard metric column",
                    "top_n": "top/rank 질문의 양의 정수",
                    "rank_order": "desc | asc",
                    "analysis_output_columns": ["pandas 이후 기대되는 standard result column, optional"],
                    "pandas_function_case": {
                        "key": "optional key from metadata.domain_items.pandas_function_cases",
                        "function_name": "optional helper function name",
                        "input_text": "helper에 전달할 사용자 원문 또는 표현",
                    },
                    "retrieval_jobs": [
                        {
                            "dataset_key": "dataset key from metadata",
                            "source_alias": "short unique alias",
                            "purpose": "이 데이터가 필요한 이유",
                            "source_scope": {
                                "date_scope": "today | yesterday | concrete date | all/none, optional but recommended",
                                "process_scope": "이 source에만 적용되는 process/group label, optional",
                                "status_scope": "이 source에만 적용되는 status/shift/scope label, optional",
                            },
                            "params": {},
                            "filters": [],
                            "required_columns": ["retrieval에 필요한 dataset physical/source column"],
                            "required_param_mappings": {"DATE": ["physical column copied from metadata"]},
                            "filter_mappings": {"standard logical column": ["dataset physical/source columns copied from metadata"]},
                            "standard_column_aliases": {"standard logical column": ["dataset physical/source columns copied from metadata"]},
                            "date_format": "metadata.datasets[dataset_key].date_format이 있으면 복사",
                            "pandas_preprocessing": {"standardize_columns": True},
                        }
                    ],
                    "step_plan": [
                        {
                            "step_id": "짧은 id",
                            "operation": "analysis operation",
                            "source_alias": "source alias",
                            "metric": "optional metric column",
                            "top_n": "optional positive integer",
                            "rank_order": "optional desc|asc",
                            "grain": "optional semantic grain such as product, process, lot, device, total, or detail",
                            "rank_groups": [{"label": "사용자가 요청한 group label", "field": "metadata 기반 source/filter field", "values": ["이 group에 포함되는 source value"]}],
                            "rank_group_output_column": "optional final output column for rank group labels",
                            "function_case_key": "optional pandas_function_cases key when this step applies a helper case",
                            "function_name": "optional helper function name when this step applies a helper case",
                            "input_text": "사용자 질문에서 복사한 optional helper input text",
                            "group_by": ["optional grouping columns"],
                            "output_columns": ["optional standard result columns"],
                        }
                    ],
                    "depends_on_state": False,
                    "requires_full_previous_result_restore": False,
                    "previous_result_restore_mode": "summary | full",
                    "reasoning_steps": ["짧은 reasoning step"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "",
            "규칙:",
            "- 사용자가 계산 요약이 아니라 source/detail row를 요청하면 intent_type=detail_lookup을 사용하세요.",
            "- 사용자가 상세 데이터, raw data, 원본 row, 전체 row를 요청하거나 집계/grouping하지 말라고 하면 group_by를 강제하지 말고 analysis_kind=detail_rows로 source row를 보존하세요.",
            "- total/summary quantity 요청과 raw/detail data 요청을 혼동하지 마세요. total/summary quantity는 하나의 집계 결과 row를 요구하고, raw/detail data는 detail_rows를 요구합니다.",
            "- 명시적인 grouping, ranking, detail, raw 표현이 없는 metric/quantity 질문은 기본적으로 aggregate total로 처리하세요: group_by=[], 결과 row 1개, additive output metric 합계.",
            "- 하나의 dataset만 필요한 aggregation/ranking 질문에는 intent_type=single_retrieval_analysis를 사용하세요.",
            "- 여러 dataset이 필요한 질문에는 intent_type=multi_source_analysis를 사용하세요.",
            "- 한 step이 만든 key를 다음 step에서 재사용해야 하면 intent_type=multi_step_analysis를 사용하세요.",
            "- 질문이 previous state에 의존하면 intent_type=followup_transform을 사용하세요.",
            "- intent_type=finish가 아니면 datasets의 모든 dataset에 대해 반드시 retrieval_jobs를 반환하세요. datasets/params/filters만 반환하지 마세요.",
            "- intent_type=finish가 아닌 analysis request에는 반드시 step_plan을 반환하세요. step_plan에는 어떤 operation이 어떤 source_alias를 쓰는지 드러나야 합니다.",
            "- step_plan[].source_alias와 step_plan[].source_aliases는 retrieval_jobs[].source_alias 값과 정확히 일치해야 합니다. retrieval_jobs에 없는 generic alias를 만들지 마세요.",
            "- 절차적 filtering/parsing을 metadata.domain_items.pandas_function_cases 항목이 처리해야 하는 경우 pandas_function_case를 설정하고 operation='apply_pandas_function_case', function_case_key, function_name, input_text가 있는 step_plan item을 추가하세요.",
            "- 제품 token pandas_function_case의 input_text에는 질문에서 발견된 모든 제품 속성 token을 포함하세요. 예를 들어 '오늘 da에서 UFBGA qdp제품 생산량'은 input_text='UFBGA qdp'이고, 'lpddr4 lc 64g 제품'은 input_text='lpddr4 lc 64g'입니다. qdp처럼 마지막 token 하나만 남기지 마세요.",
            "- 제품 token input_text에는 날짜/시점, 공정 scope, metric/동사 표현은 넣지 마세요. 예: 오늘, 어제, da에서, 생산량, 재공, 알려줘는 제외하고 제품 속성 token만 남깁니다.",
            "- DATE params는 dataset별 실행 parameter입니다. 해당 dataset metadata의 required_params/required_param_mappings에 DATE가 있을 때만 retrieval_jobs[].params.DATE를 추가하세요.",
            "- DATE가 table_catalog.filter_mappings에만 있으면 optional filter로 취급하세요. 사용자가 today/yesterday/current/구체 날짜처럼 date-scoped 질문을 명시한 경우에만 retrieval_jobs[].filters DATE를 추가하세요.",
            "- 날짜를 묻지 않는 raw/detail dataset lookup에는 DATE params나 DATE filter를 추가하지 마세요.",
            "- DATE가 required이거나 명시적으로 filter로 요청되면 metadata.datasets[dataset_key].date_format과 date_param_value_for_current_request를 읽고, 그 dataset 전용 format을 정확히 사용하세요.",
            f"- dataset date_format이 YYYYMMDD이면 DATE는 {_date_param_value_for_dataset(request_date, {'date_format': 'YYYYMMDD'})} 형태여야 합니다. 이 dataset에 {_date_param_value_for_dataset(request_date, {'date_format': 'YYYY-MM-DD'})}를 출력하지 마세요.",
            f"- dataset date_format이 YYYY-MM-DD이면 DATE는 {_date_param_value_for_dataset(request_date, {'date_format': 'YYYY-MM-DD'})} 형태여야 합니다. 이 dataset에 {_date_param_value_for_dataset(request_date, {'date_format': 'YYYYMMDD'})}를 출력하지 마세요.",
            "- dataset 자체 metadata가 그렇게 지시하지 않는 한, 한 dataset의 date format을 다른 dataset에 복사하지 마세요.",
            "- retrieval job에 DATE params가 있으면, 가능할 때 dataset metadata의 required_param_mappings와 date_format도 해당 retrieval_jobs item에 복사하세요.",
            "- product_grain, step_plan[].group_by, step_plan[].join_keys, final output_columns는 metadata의 standard logical column name으로 유지하세요. dataset별 physical name으로 바꾸지 마세요.",
            "- metric 결과 column은 metric의 standard name을 유지하세요. 예를 들어 HBM 제품 생산량이어도 HBM_PRODUCTION_QTY가 아니라 PRODUCTION을 analysis_output_columns와 step_plan.output_columns에 사용하세요. HBM 같은 scope label은 필요하면 result_scope_columns로 분리하세요.",
            "- retrieval_jobs[].required_columns에는 table_catalog.columns/filter_mappings/standard_column_aliases에서 확인한 dataset physical/source column을 요청하세요. pandas 단계가 join, grouping, ranking, output shaping 전에 source DataFrame을 standardize합니다.",
            "- physical column을 pandas에서 standardize할 수 있도록 table_catalog.filter_mappings와 standard_column_aliases가 있으면 각 retrieval job에 복사하세요.",
            "- 이전 결과 자체를 재계산, filtering, sort, regroup하거나 detail row로 보여주는 follow-up 질문은 requires_full_previous_result_restore=true와 previous_result_restore_mode=full을 설정하세요.",
            "- 같은 previous data를 다른 dimension으로 breakdown하는 follow-up 질문은 새 retrieval_jobs를 만들지 마세요. reuse_previous_runtime_sources=true, requires_full_previous_result_restore=true, previous_result_restore_mode=full을 설정하고, metric 합계가 필요하면 적절한 previous-source analysis kind를 사용하세요.",
            "- previous product key만 새 retrieval에 필요한 follow-up 질문은 previous_result_restore_mode=summary를 유지하세요.",
            "- current 또는 relative-date 질문은 history를 명시하지 않는 한 요청한 time scope와 metadata date_scope가 맞는 dataset을 우선하세요.",
            "- status, category, detail 요청은 hardcoded value 대신 domain metadata와 table_catalog metadata를 사용하세요.",
            "- top/bottom/rank 질문에는 nested rank object를 반환하지 마세요. ranking 값은 top-level metric/top_n/rank_order에 두고 rank step_plan item에도 반복하세요.",
            "- 가장 많은/most/highest/top 질문에서 명시적인 개수가 없으면 top_n=1, rank_order=desc를 사용하세요.",
            "- top/bottom/rank 질문 뒤에 dependent lookup이 있으면 rank step을 먼저, dependent retrieval/analysis step을 나중에 표현하세요.",
            "- filter scope와 grouping grain을 분리하세요. row selection에만 쓰는 column은 group_by/output_columns가 아니라 retrieval_jobs[].filters 또는 rank_groups[].field에 두세요.",
            "- filtered result를 식별하는 데 도움이 되는 경우 filter scope column은 result_scope_columns 또는 final output의 label로 나타날 수 있습니다.",
            "- 다만 사용자가 raw breakdown axis나 raw/detail row를 명시적으로 요청하지 않는 한 filter-only scope column을 group_by/join_keys로 사용하지 마세요.",
            "- filtered scope의 total 질문은 step_plan[].group_by=[]와 join_keys=[]로 설정하세요. filter-only column으로 join/grouping하지 말고 result_scope_columns/output_columns로 scope label을 보여주세요.",
            "- group_by는 ranking 또는 aggregation 대상 entity에서 선택하고, total 질문에는 empty group_by를 사용하세요.",
            "- 사용자가 여러 scope를 비교하면 scope별로 별도의 source-specific retrieval_jobs filters와 step_plan output을 만드세요. 서로 다른 scope filter를 하나의 애매한 filter로 합치지 말고 각 source에만 유지하세요.",
            "- source-specific scope는 global question wording보다 우선합니다.",
            "- source-local hint는 retrieval_jobs[].source_scope에 넣고, 해당 job의 params/filters에만 반영하세요.",
            "- 질문이 source별로 다른 scope를 지정하면 top-level filters를 모든 retrieval job에 복사하지 마세요. 각 filter는 source_scope가 맞는 job에만 유지하세요.",
            "- 질문에 yesterday/current, 어제/현재처럼 서로 다른 date scope가 source별로 함께 나오면 하나의 DATE를 모든 retrieval job에 복사하지 마세요. 각 retrieval job의 source_scope.date_scope, params.DATE, filters.DATE를 해당 source 표현에 맞게 분리하세요.",
            "- rank source와 dependent lookup source의 date scope가 다르면 rank step의 source job과 dependent step의 source job에 서로 다른 DATE를 유지하세요.",
            "- 질문이 여러 scope에 대해 같은 measure를 요구하면 각 scope를 별도로 aggregate하고, 하나의 애매한 metric column 대신 user-facing scope-labeled column을 반환하세요.",
            "- 사용자가 한 metric source에 대해 all/overall scope를 요청하면, 명시적으로 요청하지 않는 한 더 좁은 scope filter를 적용하지 마세요.",
            "- 사용자가 요청한 group/scope 각각에 대해 top/rank 결과를 요청하면(각각, 각, 별로, per each), 그 grouping intent를 step_plan[].rank_groups로 표현하세요.",
            "- per-group ranking은 user-facing group label과 ranked entity grain으로 group/rank하세요. 사용자가 raw field를 breakdown axis로 요청하지 않았다면 raw condition field별로 따로 rank하지 마세요.",
            "- rank_groups에서는 raw metadata-backed field를 rank_groups[].field와 retrieval filters에만 사용하세요. 사용자가 raw field별 breakdown을 명시적으로 요청하지 않는 한 final output_columns에 그 raw field를 포함하지 마세요.",
            "- rank group label은 rank_group_output_column/output_columns를 통해 user-facing final column으로 제공하세요.",
            "- top/rank 질문 뒤에 dependent lookup, count, detail, oldest/longest selection이 있으면 matching metadata analysis_recipes 항목을 우선하고 rank step을 dependent step보다 먼저 표현하세요.",
            "- dependent count에는 다른 dataset으로 대체하지 말고 metadata의 count source와 count_column을 보존하세요.",
            "- loose top-level group_by/output_columns를 step_plan 대체물로 쓰지 마세요. product_grain과 analysis_output_columns를 사용하고, 필요하면 관련 step 안에 group_by/output_columns를 포함하세요.",
            "- analysis_recipes 항목이 질문과 맞으면 required_quantity_terms, required_dataset_families, metric_terms, grain_policy, source_aliases_by_family, defaults, output_columns를 planning evidence로 사용하세요.",
            "- grain_policy가 grouping을 결정합니다. aggregate_total은 하나의 total row이고, question_or_product_grain은 질문이 명시한 grain을 쓰되 product-level row가 자연스러울 때만 product grain을 사용한다는 뜻입니다.",
            "- 필요한 dataset, filter, formula, value mapping이 metadata에 없으면 hardcode하지 마세요. 가능한 metadata-backed plan을 반환하고 누락 항목은 reasoning_steps에 설명하세요.",
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "intent", "specialized_prompt": specialized_prompt}


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
        "pandas_function_cases": domain.get("pandas_function_cases", {}),
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


def _specialized_prompt(value: Any) -> str:
    text = _clean_text(value)
    return text or "추가 Specialized Prompt가 제공되지 않았습니다."


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        for key in ("text", "content", "value"):
            if data.get(key):
                return str(data[key]).strip()
    return str(value).strip()


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
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(
            name="specialized_prompt_text",
            display_name="Specialized Prompt",
            value="",
            required=False,
        ),
    ]
    outputs = [
        Output(name="intent_prompt", display_name="Intent Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 질문, 메타데이터, 이전 state를 바탕으로 의도 분석 LLM에 보낼 프롬프트와 context payload를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt(self) -> Message:
        prompt_payload = build_intent_prompt_payload(
            getattr(self, "payload", None),
            getattr(self, "specialized_prompt_text", ""),
        )

        self.status = {
            "prompt_type": prompt_payload.get("prompt_type", "intent"),
            "chars": len(prompt_payload["prompt"]),
            "has_specialized_prompt": bool(_clean_text(getattr(self, "specialized_prompt_text", ""))),
        }
        return Message(text=prompt_payload["prompt"])

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 질문, 메타데이터, 이전 state를 바탕으로 의도 분석 LLM에 보낼 프롬프트와 context payload를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt_payload(self) -> Data:
        return Data(
            data=build_intent_prompt_payload(
                getattr(self, "payload", None),
                getattr(self, "specialized_prompt_text", ""),
            )
        )
