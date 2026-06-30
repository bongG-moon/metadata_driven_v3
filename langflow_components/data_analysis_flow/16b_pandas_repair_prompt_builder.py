# 파일 설명: 16B Pandas Repair Prompt Builder Langflow custom component 파일입니다.
# 흐름 역할: 실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_pandas_repair_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    repair = payload.get("pandas_repair") if isinstance(payload.get("pandas_repair"), dict) else {}
    if not repair.get("required"):
        route = str(repair.get("route") or "success")
        reason = str(repair.get("reason") or "pandas repair가 필요하지 않습니다.")
        prompt = "\n".join(
            [
                "이 payload는 pandas repair가 필요하지 않습니다.",
                f"복구 경로: {route}",
                f"사유: {reason}",
                "이 분기에서는 pandas code를 생성하지 마세요.",
                "후속 repair executor는 기존 payload를 변경하지 않고 통과시켜야 합니다.",
            ]
        )
        return {
            "prompt": prompt,
            "payload": payload,
            "prompt_type": "pandas_repair_skip",
            "repair_required": False,
            "repair_decision": repair,
        }

    context = repair.get("context") if isinstance(repair.get("context"), dict) else _pandas_repair_context(payload)
    context = deepcopy(context)
    context.setdefault("column_contract_summary", _column_contract_summary(payload))
    prompt = "\n".join(
        [
            "당신은 Langflow 제조 데이터 에이전트의 실패한 pandas code를 수정하는 repair 노드입니다.",
            "반드시 하나의 엄격한 JSON object만 반환하세요. markdown 코드블록으로 감싸지 마세요.",
            "제공된 변수 pd, sources, plan, state와 pandas_function_case/Specialized Functions에서 선택된 helper function만 사용해서 수정된 Python pandas code를 생성하세요.",
            "sources는 source_alias를 pandas DataFrame에 매핑하는 dict입니다.",
            "source alias는 sources/source summary의 실제 key만 사용하세요. 보통 retrieval_jobs[*].source_alias입니다. generic alias를 임의로 만들지 마세요.",
            "plan과 state는 Python dict입니다. plan['key'], plan.get('key'), state.get('key')를 사용하고 plan.key 또는 state.key는 절대 사용하지 마세요.",
            "plan은 이미 normalized intent plan 자체입니다. plan['intent_plan'] 같은 중첩 key를 만들거나 참조하지 마세요.",
            "수정 코드는 최종 pandas DataFrame을 반드시 result_df에 할당해야 합니다.",
            "_prod_df 또는 _filtered_df처럼 underscore로 시작하는 local variable name을 만들거나 참조하지 마세요. prod_df, wip_today_df, WAFER_OUT_QTY처럼 이름 안의 underscore는 허용됩니다.",
            "module을 import하지 마세요. 파일 read/write, network, OS, eval, exec, open, subprocess, numpy, np, np.where를 사용하지 마세요.",
            "pd.inf, float('inf'), infinity replacement를 사용하지 마세요. 나누기 전에 boolean mask로 division by zero를 피하세요.",
            "date/date-format repair에서는 datetime/date/timedelta를 import하지 마세요. pandas만 사용하세요: pd.to_datetime(..., errors='coerce'), Series.dt.strftime(...), string slicing, 또는 plan에 이미 있는 DATE value와 직접 string comparison.",
            "source별 DATE params/filters가 서로 다르면 각 source_alias에 지정된 DATE만 해당 DataFrame에 적용하세요. 한 source의 DATE를 다른 source에 복사하거나 전체 분석 공통 DATE로 덮어쓰지 마세요.",
            "pandas filter를 복구할 때 eq/in/not_in/starts_with/contains 같은 문자열 또는 범주형 비교는 source column도 비교값도 같은 형식으로 맞춘 뒤 비교하세요. 예: df[col].astype(str).str.strip().str.upper()와 str(value).strip().upper()를 비교하세요.",
            "SHIFT, DATE, OPER_NAME처럼 숫자/문자/공백 표기가 섞일 수 있는 filter column에 df[col] == '2' 같은 직접 비교를 사용하지 마세요. numeric range 비교(gte/gt/lte/lt)만 pd.to_numeric(..., errors='coerce')를 사용하세요.",
            "같은 intent plan과 사용 가능한 source DataFrame을 기준으로 실패한 코드를 고치세요. result column은 요청된 output contract와 맞아야 합니다.",
            "PRODUCTION이 최종 metric이면 TOTAL_PRODUCTION, PRODUCTION_QTY 같은 같은 값의 중복 alias를 만들지 말고 PRODUCTION을 사용하세요. WIP도 TOTAL_WIP 같은 중복 alias 없이 WIP를 사용하세요.",
            "DEN/DENSITY, PKG_TYPE1/PKG1, PKG_TYPE2/PKG2처럼 같은 의미의 standard/physical alias column을 result_df에 동시에 남기지 말고 plan의 standard column name을 우선하세요.",
            "함수 케이스 복구 규칙:",
            "- intent_plan.pandas_function_case 또는 step_plan item이 function_name을 선택하면 Specialized Functions의 의도와 helper 형태를 사용해 코드를 수정하세요.",
            "- apply_pandas_function_case step에서는 선택된 helper를 function_name(input_text, sources[source_alias]) 형태로 호출하거나, 제공된 참고 코드에서 helper를 inline 정의한 뒤 호출하세요.",
            "- helper input_text는 현재 step.get('input_text') 또는 plan.get('pandas_function_case', {}).get('input_text')에서 읽으세요. plan['intent_plan']은 존재하지 않습니다.",
            "- 제품 token helper의 input_text가 질문의 일부 token만 담고 있으면 사용자 질문에서 제품 속성 token 전체를 복원하세요. 예: 'UFBGA qdp제품'은 'UFBGA qdp'를 넘기고, 'qdp'만 넘기지 마세요.",
            "- 선택된 helper 호출에는 가능하면 positional argument를 사용하세요. helper signature가 명시적으로 문서화하지 않은 source_df= 같은 keyword argument를 임의로 만들지 마세요.",
            "- Specialized Functions가 더 풍부한 매칭 로직을 설명하는데도 선택된 function case를 단순 filter로 우회하지 마세요.",
            "- 제품 token pandas_function_case가 선택된 계획에서는 MODE/DEN/PKG_TYPE 같은 제품 속성 retrieval filter를 직접 새로 만들거나 helper 호출을 우회하지 마세요.",
            "- apply_pandas_function_case 뒤에 aggregate/rank/detail step이 이어지면 helper를 호출한 뒤 helper output schema를 먼저 확인하세요.",
            "- downstream step의 group_by/metric/output_columns에 필요한 column이 helper output에 모두 있으면 helper output을 filtered source row로 직접 사용하세요.",
            "- downstream에 필요한 column이 helper output에 없으면 helper output을 key table로만 쓰고, 원본 sources[source_alias]를 공통 key columns로 filter/merge한 뒤 aggregate/rank/detail을 수행하세요.",
            "- helper output에 없는 column으로 groupby, metric 계산, output selection을 하지 마세요. 필요한 column이 없으면 원본 source를 key로 제한한 filtered source row를 먼저 만드세요.",
            "- 입력 text의 일부 token이 helper 규칙상 무시 가능한 업무 단어인지, 반드시 매칭되어야 하는 조건 token인지는 Specialized Functions 설명을 따르세요.",
            "- 반드시 매칭되어야 하는 조건 token이 source data 어느 컬럼에도 매칭되지 않으면 부분 매칭 결과를 만들지 말고 빈 DataFrame 또는 0 집계 결과를 반환하세요.",
            "- 이전 error가 helper missing을 말하면 helper를 inline 정의한 뒤 호출해 self-contained code로 만들거나, executor에서 사용 가능한 경우에만 helper를 호출하세요.",
            "executor fallback이 row를 만들었다면 그 row는 기대 shape 힌트로만 취급하세요. fallback comment를 복사하거나 빈 placeholder를 반환하지 말고 원래 실패한 pandas code를 수정하세요.",
            "수정 코드에서 .to_frame()을 사용하지 마세요. group_by가 없는 one total row는 pd.DataFrame([{...}])로 result_df를 만드세요.",
            "DataFrame.agg(named_metric=(column, func)).to_frame().T를 사용하지 마세요. DataFrame.agg는 이미 DataFrame을 반환할 수 있고, 이후 to_frame은 실패할 수 있습니다.",
            "groupby(..., as_index=False)를 사용했다면 뒤에 reset_index()를 다시 붙이지 마세요. group column이 이미 column으로 남아 있어 cannot insert ... already exists 오류가 날 수 있습니다.",
            "groupby 결과를 DataFrame으로 만들 때는 groupby(group_cols, as_index=False).agg(...) 또는 groupby(group_cols).agg(...).reset_index() 중 하나만 사용하세요.",
            "retrieve_and_aggregate 또는 group_by가 없는 단일 metric total은 pd.DataFrame([{'PRODUCTION': df['PRODUCTION'].sum()}])처럼 row를 직접 만드세요.",
            "group_by가 없는 여러 source의 scalar total을 결합할 때는 공통 key 없는 DataFrame merge 대신 DataFrame row 하나를 직접 만드세요.",
            "컬럼 계약 규칙:",
            "- repaired code가 실행되기 전에 각 source DataFrame은 표준화된 pandas analysis view로 변환됩니다.",
            "- retrieval_jobs[*].filter_mappings, required_param_mappings, standard_column_aliases에 physical source column이 있으면 pandas code에서는 physical column name이 아니라 standard mapping key를 사용하세요.",
            "- standardize 이후 sources에 mapped physical column과 standard column이 둘 다 남아 있다고 가정하지 마세요.",
            "- repaired code 안에서 physical column을 standard column으로 다시 rename하지 마세요. source DataFrame은 실행 전에 이미 표준화되어 있습니다.",
            "- physical source column name은 standard mapping이 없고 source summary에서 그 column을 사용할 수 있을 때만 허용됩니다.",
            "- 아래 column_contract_summary를 보고 어떤 column이 standardize되었고 어떤 physical-only column이 허용되는지 판단하세요.",
            "단계 계획 복구 규칙:",
            "- intent_plan.step_plan의 모든 step을 순서대로 따르고, 각 step DataFrame을 step_outputs[step_id]에 저장하세요.",
            "- intent_plan.step_plan에 없는 step을 만들거나 참조하지 마세요. 실제 list 길이를 벗어나는 plan['step_plan'][i] 접근은 절대 하지 마세요.",
            "- step_outputs key는 intent_plan.step_plan의 실제 step_id 값을 정확히 사용하세요. 해당 step_id가 plan에 이미 있지 않다면 rank_da_*, rank_wb_*, combine_* 같은 split step을 임의로 만들지 마세요.",
            "- left_join step은 pandas left merge 결과를 그대로 보존하세요. plan이 명시하지 않은 한 오른쪽 metric 결측값을 0이나 빈 문자열로 임의 채움하지 마세요.",
            "- step.output_columns가 있으면 각 step 결과를 그 컬럼 순서로 정리하고, 최종 result_df는 마지막 step.output_columns 또는 intent_plan.analysis_output_columns 기준으로 정리하세요.",
            "",
            "실패 실행 context:",
            json.dumps(context, ensure_ascii=False, indent=2),
            "",
            "필수 JSON schema:",
            json.dumps(
                {
                    "code": "수정된 Python code. 반드시 result_df를 설정해야 합니다.",
                    "output_columns": ["result_df에 예상되는 column name"],
                    "reasoning_steps": ["repair 이유에 대한 짧은 설명"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {
        "prompt": prompt,
        "payload": payload,
        "prompt_type": "pandas_code_repair",
        "repair_required": True,
        "repair_decision": repair,
    }


def _pandas_repair_context(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = _analysis_from_payload(payload)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}
    return {
        "request": deepcopy(request),
        "intent_plan": deepcopy(payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}),
        "payload_summary": _payload_summary(payload),
        "column_contract_summary": _column_contract_summary(payload),
        "runtime_source_summary": _runtime_source_summary(runtime_sources),
        "state_summary": _state_summary(state),
        "failed_pandas_code_json": deepcopy(
            analysis.get("pandas_code_json") if isinstance(analysis.get("pandas_code_json"), dict) else {}
        ),
        "executed_code": str(analysis.get("analysis_code") or ""),
        "errors": _unique_text([*_as_text_list(analysis.get("errors")), *_as_text_list(analysis.get("repairable_errors"))]),
        "repairable_errors": _as_text_list(analysis.get("repairable_errors")),
        "used_executor_fallback": bool(analysis.get("used_executor_fallback")),
        "analysis_columns": _as_text_list(analysis.get("columns")),
        "analysis_row_count": analysis.get("row_count", 0),
        "llm_text_preview": str(analysis.get("llm_text_preview") or "")[:1200],
    }


def _analysis_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    if analysis:
        return analysis
    analysis_keys = {
        "status",
        "analysis_kind",
        "analysis_code",
        "columns",
        "rows",
        "row_count",
        "errors",
        "repairable_errors",
        "used_executor_fallback",
        "pandas_code_json",
        "llm_text_preview",
    }
    if any(key in payload for key in analysis_keys):
        return payload
    return {}


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("status", "warnings", "errors", "info", "direct_response_ready"):
        if key in payload:
            summary[key] = deepcopy(payload.get(key))
    for key in ("retrieval_jobs", "source_results"):
        value = payload.get(key)
        if isinstance(value, list):
            summary[key] = [_compact_dict(item, 12) for item in value[:20] if isinstance(item, dict)]
    return summary


def _column_contract_summary(payload: dict[str, Any]) -> dict[str, Any]:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    source_columns_by_alias = _source_columns_by_alias(payload)
    result: dict[str, Any] = {}
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        alias = str(job.get("source_alias") or job.get("dataset_key") or "").strip()
        if not alias:
            continue
        mapped_columns: dict[str, list[str]] = {}
        mapped_physical_columns: set[str] = set()
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mapping = job.get(field) if isinstance(job.get(field), dict) else {}
            for standard, candidates in mapping.items():
                standard_text = str(standard or "").strip()
                if not standard_text:
                    continue
                if not isinstance(candidates, list):
                    candidates = [candidates]
                physical_candidates = [
                    str(candidate)
                    for candidate in candidates
                    if str(candidate or "").strip() and str(candidate) != standard_text
                ]
                if not physical_candidates:
                    continue
                mapped_columns.setdefault(standard_text, [])
                mapped_columns[standard_text].extend(physical_candidates)
                mapped_physical_columns.update(physical_candidates)
        mapped_columns = {
            standard: _unique_columns(candidates)
            for standard, candidates in mapped_columns.items()
            if candidates
        }
        source_columns = source_columns_by_alias.get(alias, [])
        physical_only_columns = [
            column
            for column in source_columns
            if column not in mapped_physical_columns and column not in mapped_columns
        ]
        result[alias] = {
            "use_standard_names_for_mapped_columns": mapped_columns,
            "physical_only_columns_allowed_by_name": physical_only_columns,
        }
    return result


def _source_columns_by_alias(payload: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    source_results = payload.get("source_results") if isinstance(payload.get("source_results"), list) else []
    for source in source_results:
        if not isinstance(source, dict):
            continue
        alias = str(source.get("source_alias") or source.get("dataset_key") or "").strip()
        if not alias:
            continue
        columns = source.get("columns") if isinstance(source.get("columns"), list) else []
        if not columns:
            rows = source.get("rows") if isinstance(source.get("rows"), list) else []
            first_row = rows[0] if rows and isinstance(rows[0], dict) else {}
            columns = list(first_row.keys())
        result[alias] = _unique_columns([str(column) for column in columns if str(column or "").strip()])
    return result


def _runtime_source_summary(runtime_sources: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for alias, rows in runtime_sources.items():
        clean_rows = rows if isinstance(rows, list) else []
        first_row = clean_rows[0] if clean_rows and isinstance(clean_rows[0], dict) else {}
        summary[str(alias)] = {
            "row_count": len(clean_rows),
            "columns": list(first_row.keys()),
            "preview_rows": deepcopy(clean_rows[:5]),
        }
    return summary


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    rows = current_data.get("rows") if isinstance(current_data.get("rows"), list) else []
    return {
        "has_state": bool(state),
        "context": deepcopy(state.get("context", {})),
        "current_data_columns": deepcopy(current_data.get("columns", [])),
        "current_data_row_count": current_data.get("row_count", 0),
        "current_data_preview_rows": deepcopy(rows[:3]),
        "current_data_product_key_columns": deepcopy(current_data.get("product_key_columns", [])),
        "current_data_product_key_values": deepcopy(current_data.get("product_key_values", [])[:20])
        if isinstance(current_data.get("product_key_values"), list)
        else [],
    }


def _compact_dict(value: dict[str, Any], max_keys: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= max_keys:
            result["..."] = f"{len(value) - max_keys} more keys"
            break
        if key in {"data", "rows", "runtime_sources"}:
            if isinstance(item, list):
                result[key] = {"row_count": len(item), "preview_rows": deepcopy(item[:3])}
            elif isinstance(item, dict):
                result[key] = {"keys": list(item.keys())[:20]}
            else:
                result[key] = item
        else:
            result[key] = deepcopy(item)
    return result


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item) for item in value if str(item or "").strip()]


def _unique_text(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _unique_columns(columns: list[str]) -> list[str]:
    result: list[str] = []
    for column in columns:
        if column not in result:
            result.append(column)
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 16B Pandas Repair Prompt Builder
# Langflow 표시 설명: 실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다.
class PandasRepairPromptBuilder(Component):

    display_name = "16B Pandas Repair Prompt Builder"
    description = "실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다."
    inputs = [DataInput(name="payload", display_name="Repair Payload", required=True)]
    outputs = [
        Output(name="repair_prompt", display_name="Repair Prompt", method="build_prompt"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 실패 원인, 기존 코드, source 정보를 담아 pandas repair LLM 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt(self) -> Message:
        prompt_payload = build_pandas_repair_prompt_payload(getattr(self, "payload", None))
        self.status = {

            "prompt_type": prompt_payload.get("prompt_type", "pandas_code_repair"),
            "repair_required": prompt_payload.get("repair_required", False),
            "chars": len(prompt_payload["prompt"]),
        }
        return Message(text=prompt_payload["prompt"])
