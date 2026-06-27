# 파일 설명: 14 Pandas Prompt Builder Langflow custom component 파일입니다.
# 흐름 역할: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import ast
import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_pandas_prompt_payload(payload_value: Any, specialized_functions_text: Any = "") -> dict[str, Any]:
    payload = _payload(payload_value)
    if payload.get("direct_response_ready"):
        prompt = json.dumps(
            {
                "code": "result_df = pd.DataFrame([])",
                "output_columns": [],
                "reasoning_steps": ["메타데이터 직접 응답이 이미 준비되어 있으므로 pandas 실행은 그대로 통과시키면 됩니다."],
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
    function_cases = _pandas_function_cases(
        payload,
        plan,
        str(request.get("question") or ""),
        source_summary,
        specialized_functions_text,
    )
    payload_for_executor = deepcopy(payload)
    payload_for_executor["pandas_function_case_runtime"] = deepcopy(function_cases.get("runtime", {}))

    prompt = "\n".join(
        [
            "당신은 Langflow 제조 데이터 에이전트의 pandas code generation 노드입니다.",
            "반드시 하나의 엄격한 JSON object만 반환하세요. markdown 코드블록으로 감싸지 마세요.",
            "제공된 변수 pd, sources, plan, state와 Specialized Functions에서 로드된 helper function만 사용해서 Python pandas 코드를 생성하세요.",
            "sources는 source_alias를 pandas DataFrame에 매핑하는 dict입니다.",
            "source alias는 sources/source summary의 실제 key만 사용하세요. 보통 retrieval_jobs[*].source_alias입니다. generic alias를 임의로 만들지 마세요.",
            "plan과 state는 Python dict입니다. plan['key'], plan.get('key'), state.get('key')를 사용하고 plan.key 또는 state.key는 절대 사용하지 마세요.",
            "생성 코드는 최종 pandas DataFrame을 반드시 result_df에 할당해야 합니다.",
            "최종 result column은 normalized plan이 요청한 standard contract name을 사용해야 합니다.",
            "이 코드가 실행되기 전에 각 source DataFrame은 표준화된 pandas analysis view로 변환됩니다.",
            "table_catalog.filter_mappings/required_param_mappings/standard_column_aliases에 있는 physical source column은 plan에서 사용하는 standard name으로 rename됩니다.",
            "join, grouping, ranking, output shaping에는 plan의 standard analysis column name을 사용하세요.",
            "sources에 physical column과 standard alias가 둘 다 남아 있을 것이라고 기대하지 마세요. product_grain, group_by, join_keys, analysis_output_columns의 standard name을 사용하세요.",
            "source summary에 해당 physical column이 보이고 plan이 standard alias 없는 source-only measure/detail column을 명시적으로 요구할 때만 physical source column name을 사용하세요.",
            "measure column을 한글 label로 번역하지 말고, PRODUCTION_sum, WIP_sum, OUT_PLAN_sum, lowercase rank 같은 임시 이름을 result_df에 남기지 마세요.",
            "_prod_df 또는 _filtered_df처럼 underscore로 시작하는 local variable name을 만들거나 참조하지 마세요. prod_df, wip_today_df, WAFER_OUT_QTY처럼 이름 안의 underscore는 허용됩니다.",
            "module을 import하지 마세요. 파일 read/write, network, OS, eval, exec, open, subprocess를 사용하지 마세요.",
            "numpy, np, np.where를 사용하지 마세요. div, fillna, where, mask, boolean comparison 같은 pandas Series operation을 사용하세요.",
            "pd.inf, float('inf'), infinity replacement를 사용하지 마세요. 나누기 전에 boolean mask로 division by zero를 피하세요.",
            "date/date-format 처리는 datetime/date/timedelta를 import하지 마세요. pandas만 사용하세요: pd.to_datetime(..., errors='coerce'), Series.dt.strftime(...), string slicing, 또는 plan filters/params에 이미 있는 DATE value와 직접 string comparison.",
            "metadata에서 이미 DATE param/filter를 받은 dataset은 pandas 코드 안에서 날짜를 다시 계산하지 말고 그 string value를 직접 사용하는 것을 우선하세요.",
            "생성 코드에서 .to_frame()을 사용하지 마세요. 여러 metric의 one total row는 pd.DataFrame([{...}])로 result_df를 만드세요.",
            "DataFrame.agg(named_metric=(column, func)).to_frame().T를 사용하지 마세요. DataFrame.agg는 이미 DataFrame을 반환할 수 있고, 이후 to_frame은 실패할 수 있습니다.",
            "group_by가 없는 여러 source의 scalar total을 결합할 때는 공통 key 없는 DataFrame merge 대신 DataFrame row 하나를 직접 만드세요.",
            "생성 코드에 import statement가 포함되면 safety check가 실패합니다.",
            "",
            "순차 step_plan 실행 규칙:",
            "- Source retrieval은 DATE 또는 LOT_ID 같은 required source parameter만 적용합니다. aggregation/ranking/joining 전에 retrieval_jobs[*].filters 조건은 pandas 코드 안에서 모두 적용하세요.",
            "- filter에는 retrieval job과 일치하는 source_alias를 사용하세요. op='eq', op='in', op='not_in', op='not_empty'/'exists', op='empty', op='starts_with', op='last_char_in', op='gte'/'gt'/'lte'/'lt' 같은 numeric comparison을 지원하세요. 명시적으로 state-driven인 PRODUCT_GRAIN/from_state filter만 무시하세요.",
            "- plan['step_plan']을 읽고 모든 step을 순서대로 구현하세요. multi-step plan을 쉬운 count나 groupby 하나로 축약하지 마세요.",
            "- step_outputs라는 local dict를 유지하세요. 모든 step 이후 step DataFrame을 step_outputs[step_id]에 저장하고, downstream filtering/joining에는 step_outputs의 이전 step을 읽어 사용하세요.",
            "- step에 input_step_id가 있으면 sources[source_alias]를 다시 읽지 말고 step_outputs[input_step_id]를 해당 step의 input DataFrame으로 사용하세요.",
            "- apply_pandas_function_case step 이후 같은 source_alias에 대한 aggregate/rank/detail step이 이어지면 function-case output을 이후 step의 filtered source로 취급하세요.",
            "- ranking/filtering step의 intermediate DataFrame을 보존하고, 나중의 filtering, aggregation, join step에서 사용하세요.",
            "- step이 top_n row를 ranking하면 ranked scope에 의존하는 downstream metric보다 먼저 그 ranking을 수행하세요.",
            "- step_plan operation은 재사용 primitive로 취급하세요: aggregate_sum/aggregate_by_group은 step.group_by로 group하고 step.metric 또는 step.metrics를 aggregate합니다. rank_top_n은 step field로 group/sort합니다. equipment_count_by_product는 group_by별 step.count_column.nunique를 계산합니다. hold_lot_in_tat_by_process는 step field에서 metric을 계산합니다. left_join은 이름이 있는 이전 step을 join_key/join_keys로 join합니다.",
            "- 모든 rank step은 sorting 전에 intended grain에서 rank metric을 먼저 aggregate하세요. step.group_by가 있으면 그것을 사용하고, group_by가 없고 step.grain이 product이면 plan['product_grain']을 사용하세요. total rank 의도이면 group_by를 사용하지 마세요.",
            "- retrieval filter field가 source에 존재한다는 이유만으로 group_by에 추가하지 마세요. filter field는 사용자가 raw breakdown axis를 명시적으로 요청한 경우에만 grouping column입니다.",
            "- rank_groups/per-group ranking은 step.rank_groups로 group label을 만들고, 그 group label과 target entity grain으로 aggregate한 뒤, 각 group label 안에서 따로 rank하고, 계획된 user-facing label/output column만 result_df에 남기세요.",
            "- rank step 이후 dependent lookup/aggregate step은 다시 ranking하거나 filter column으로 grouping하지 말고, step_outputs의 ranked entity key로 later source를 제한하세요.",
            "- later step이 renamed column을 참조하기 전에 step.rename_columns가 있으면 먼저 적용하세요.",
            "- 질문이나 plan이 여러 metric을 요구하면 모두 계산하고, source data가 있을 때 plan['analysis_output_columns']의 모든 column을 result_df에 포함하세요.",
            "- plan.matched_metric_terms 또는 plan.metric_definitions에 formula/pandas_code_instructions가 있으면 derived row-level output column을 먼저 계산한 뒤 aggregate step에 따라 step.group_by 또는 total로 그 output column을 aggregate하세요.",
            "- empty group_by가 있는 aggregate step은 one total row를 반환하세요. group_by가 있는 aggregate step은 요청한 group별 row를 반환하세요. aggregate plan에서 row-level detail을 반환하지 마세요.",
            "- plan.result_scope_columns가 있으면 result_df에 이미 해당 column이 없는 한 각 scope column을 constant column으로 추가하세요. 이 column은 process group 또는 product filter scope처럼 aggregate row를 스스로 설명하게 합니다.",
            "- raw source/filter condition column이 rank_groups 또는 filter를 만드는 데만 쓰이면 result_df에 포함하지 마세요. user-facing group label에는 plan.rank_group_output_column/RANK_GROUP과 result_scope column을 사용하세요.",
            "- sbm_wip.WIP 또는 prod_today.PRODUCTION 같은 dotted source-qualified name을 final result column name으로 사용하지 마세요. WIP, PRODUCTION, INPUT_QTY, TODAY_INPUT_QTY 같은 plain user-facing metric column을 사용하고, 동일 metric의 두 scope를 함께 보여야 할 때만 SBM_WIP, SG_WIP 같은 scope-prefixed name을 사용하세요.",
            "- generated output에 필요한 plan column이 빠지면 executor가 deterministic fallback으로 대체할 수 있습니다.",
            "",
            "사용자 질문:",
            str(request.get("question") or ""),
            "",
            "정규화된 intent plan:",
            json.dumps(plan, ensure_ascii=False, indent=2),
            "",
            "사용 가능한 source DataFrame:",
            json.dumps(source_summary, ensure_ascii=False, indent=2),
            "",
            "분석 전에 pandas에서 적용할 source filter:",
            json.dumps(source_filters, ensure_ascii=False, indent=2),
            "",
            "Specialized Functions:",
            function_cases["prompt_text"],
            "",
            "이전 state 요약:",
            json.dumps(_state_summary(state), ensure_ascii=False, indent=2),
            "",
            "분석 지시:",
            _analysis_instruction(plan),
            "",
            "필수 JSON schema:",
            json.dumps(
                {
                    "code": "Python code. 반드시 result_df를 설정해야 합니다.",
                    "output_columns": ["result_df에 예상되는 column name"],
                    "reasoning_steps": ["짧은 reasoning step"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {
        "prompt": prompt,
        "payload": payload_for_executor,
        "prompt_type": "pandas_code",
        "source_summary": source_summary,
        "source_filters": source_filters,
        "pandas_function_cases": function_cases["cases"],
        "pandas_function_case_runtime": function_cases.get("runtime", {}),
    }


def _pandas_function_cases(
    payload: dict[str, Any],
    plan: dict[str, Any],
    question: str,
    source_summary: dict[str, Any],
    manual_text: Any,
) -> dict[str, Any]:
    manual = _clean_text(manual_text)
    manual_code_blocks = _extract_python_code_blocks(manual)
    manual_function_names = sorted(_defined_function_names_from_blocks(manual_code_blocks))
    selected_domain_cases = _matched_domain_function_cases(payload, plan, question, source_summary)
    selected_domain_cases = [
        _with_function_case_implementation_status(case, manual_function_names)
        for case in selected_domain_cases
    ]
    cases: list[dict[str, Any]] = []
    if manual:
        cases.append(
            {
                "key": "manual_text_input",
                "source": "specialized_functions_text",
                "instructions": manual,
                "defined_functions": manual_function_names,
            }
        )
    cases.extend(selected_domain_cases)
    runtime = {
        "manual_text": manual,
        "manual_code_blocks": manual_code_blocks,
        "manual_function_names": manual_function_names,
        "selected_cases": [
            {
                "key": case.get("key"),
                "function_name": case.get("function_name"),
                "implementation_available": case.get("implementation_available", False),
                "implementation_source": case.get("implementation_source", ""),
            }
            for case in selected_domain_cases
            if case.get("function_name")
        ],
        "missing_helpers": [
            {
                "key": case.get("key"),
                "function_name": case.get("function_name"),
                "message": (
                    f"pandas_function_cases.{case.get('key')}가 {case.get('function_name')} helper를 선택했지만 "
                    "실행 가능한 helper 구현이 제공되지 않았습니다."
                ),
            }
            for case in selected_domain_cases
            if case.get("function_name") and not case.get("implementation_available")
        ],
    }
    if not cases:
        return {
            "cases": [],
            "prompt_text": "선택된 specialized pandas function case가 없습니다.",
            "runtime": runtime,
        }
    prompt_payload = {
        "rules": [
            "이 case들은 재사용 helper-function 안내입니다. 새 data source를 추가하지 않습니다.",
            "metadata case는 function_code가 포함된 경우를 제외하면 선택 힌트입니다.",
            "Specialized Functions에 붙여넣은 code는 선택된 function_name에 대한 실행 가능한 helper code입니다.",
            "function case를 적용할 때 preview_rows가 아니라 sources의 실제 DataFrame을 사용하세요.",
            "plan.pandas_function_case 또는 step_plan의 function_case_key/function_name이 case를 지정하면 선택된 helper function을 명시적으로 호출하세요.",
            "case가 function_name과 function_code를 제공하면 pandas executor가 해당 helper를 로드합니다. generated code에서는 helper를 직접 호출하고 재정의하지 마세요.",
            "선택된 case가 function_name만 제공하고 function_code가 없으면 분석 전에 Specialized Functions에 해당 function이 정의되어 있어야 합니다.",
            "metadata hint만 보고 선택된 helper를 합성, 근사 구현, 재정의하지 마세요.",
            "missing_helpers가 비어 있지 않으면 code가 빈 result_df만 만들고 reasoning_steps에 선택된 helper 구현이 없다고 설명하는 JSON response를 반환하세요.",
            "product-token lookup case에서는 사용자 질문의 concrete token으로 source row를 filter하세요. token filtering 없이 전체 product list를 반환하는 것은 잘못된 결과입니다.",
            "token이 설정된 token column 어디에도 match되지 않으면 전체 분석을 실패시키지 말고 해당 token만 filtering에서 제외하세요.",
            "matched row로 실제 result_df를 반환하세요. print warning이나 print output에 의존하지 마세요.",
        ],
        "selected_cases": cases,
        "missing_helpers": runtime["missing_helpers"],
    }
    return {
        "cases": cases,
        "prompt_text": json.dumps(prompt_payload, ensure_ascii=False, indent=2),
        "runtime": runtime,
    }


def _with_function_case_implementation_status(case: dict[str, Any], manual_function_names: list[str]) -> dict[str, Any]:
    result = deepcopy(case)
    function_name = str(result.get("function_name") or "").strip()
    if not function_name:
        return result
    if _clean_text(_function_case_code_text(result.get("function_code"))):
        result["implementation_available"] = True
        result["implementation_source"] = "metadata.function_code"
    elif function_name in set(manual_function_names):
        result["implementation_available"] = True
        result["implementation_source"] = "specialized_functions_text"
    else:
        result["implementation_available"] = False
        result["implementation_source"] = ""
    return result


def _matched_domain_function_cases(
    payload: dict[str, Any],
    plan: dict[str, Any],
    question: str,
    source_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    raw_cases = domain.get("pandas_function_cases") if isinstance(domain.get("pandas_function_cases"), dict) else {}
    selected: list[dict[str, Any]] = []
    for case_key, case in raw_cases.items():
        if not isinstance(case, dict):
            continue
        if _function_case_matches(str(case_key), case, question, plan, source_summary):
            selected.append(_compact_function_case(str(case_key), case))
    return selected


def _function_case_matches(
    case_key: str,
    case: dict[str, Any],
    question: str,
    plan: dict[str, Any],
    source_summary: dict[str, Any],
) -> bool:
    if _plan_selects_function_case(case_key, case, plan):
        return True
    forbidden = _as_text_list(case.get("forbidden_question_cues"))
    if forbidden and _mentions_any_text(question, forbidden):
        return False
    required = _as_text_list(case.get("required_question_cues"))
    if required and not all(_mentions_any_text(question, [cue]) for cue in required):
        return False
    direct_cues = _as_text_list(
        [
            case_key,
            case.get("display_name"),
            *_as_text_list(case.get("aliases")),
            *_as_text_list(case.get("question_cues")),
            *_as_text_list(case.get("activation_cues")),
        ]
    )
    if direct_cues and _mentions_any_text(question, direct_cues):
        return True
    if _source_has_required_columns(source_summary, _as_text_list(case.get("required_source_columns"))):
        return _question_looks_like_product_lookup(question, plan)
    token_columns = _as_text_list(case.get("token_columns")) + _as_text_list(case.get("candidate_columns"))
    if _source_column_overlap_count(source_summary, token_columns) >= 2:
        return _question_looks_like_product_lookup(question, plan)
    return False


def _plan_selects_function_case(case_key: str, case: dict[str, Any], plan: dict[str, Any]) -> bool:
    function_name = str(case.get("function_name") or "").strip()
    candidates: list[Any] = []
    for key in ("pandas_function_case", "function_case"):
        value = plan.get(key)
        if value not in (None, "", [], {}):
            candidates.append(value)
    for key in ("pandas_function_cases", "function_cases"):
        value = plan.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif value not in (None, "", [], {}):
            candidates.append(value)
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if isinstance(step, dict):
            candidates.append(step)

    for item in candidates:
        if isinstance(item, str):
            if item.strip() == case_key or (function_name and item.strip() == function_name):
                return True
            continue
        if not isinstance(item, dict):
            continue
        explicit_key = str(item.get("key") or item.get("case_key") or item.get("function_case_key") or "").strip()
        explicit_function = str(item.get("function_name") or "").strip()
        if explicit_key == case_key:
            return True
        if function_name and explicit_function == function_name:
            return True
    return False


def _compact_function_case(case_key: str, case: dict[str, Any]) -> dict[str, Any]:
    result = {"key": case_key, "source": "metadata.domain_items.pandas_function_cases"}
    for field in (
        "display_name",
        "function_name",
        "use_when",
        "input_text",
        "required_source_columns",
        "token_columns",
        "candidate_columns",
        "output_order",
        "output_columns",
        "calculation_rule",
        "function_code",
        "pandas_code_instructions",
        "example",
    ):
        value = case.get(field)
        if value not in (None, "", [], {}):
            result[field] = deepcopy(value)
    return result


def _extract_python_code_blocks(text: str) -> list[str]:
    if not text:
        return []
    fenced_blocks = re.findall(r"```(?:python|py)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    blocks = [_clean_text(block) for block in fenced_blocks if _clean_text(block)]
    if blocks:
        return blocks
    return [text] if "def " in text else []


def _defined_function_names_from_blocks(blocks: list[str]) -> set[str]:
    names: set[str] = set()
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                names.add(node.name)
    return names


def _function_case_code_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(line) for line in value)
    return str(value or "").strip()


def _source_has_required_columns(source_summary: dict[str, Any], required_columns: list[str]) -> bool:
    if not required_columns:
        return False
    available: set[str] = set()
    for summary in source_summary.values():
        if not isinstance(summary, dict):
            continue
        available.update(str(column) for column in summary.get("columns", []) if str(column or "").strip())
    return all(column in available for column in required_columns)


def _source_column_overlap_count(source_summary: dict[str, Any], candidate_columns: list[str]) -> int:
    if not candidate_columns:
        return 0
    available: set[str] = set()
    for summary in source_summary.values():
        if not isinstance(summary, dict):
            continue
        available.update(str(column).upper() for column in summary.get("columns", []) if str(column or "").strip())
    candidates = {str(column).upper() for column in candidate_columns if str(column or "").strip()}
    return len(available.intersection(candidates))


def _question_looks_like_product_lookup(question: str, plan: dict[str, Any]) -> bool:
    text = str(question or "")
    korean_product = chr(0xC81C) + chr(0xD488)
    korean_lookup = chr(0xC870) + chr(0xD68C)
    korean_find = chr(0xCC3E)
    korean_list = chr(0xB9AC) + chr(0xC2A4) + chr(0xD2B8)
    if _mentions_any_text(text, [korean_product, korean_lookup, korean_find, korean_list]):
        return True
    if _mentions_any_text(text, ["\uc81c\ud488", "\uc870\ud68c", "\ucc3e", "\ub9ac\uc2a4\ud2b8"]):
        return True
    if _mentions_any_text(text, ["제품", "조회", "찾", "리스트"]):
        return True
    if _mentions_any_text(text, ["product", "products", "lookup", "find", "list", "match", "token", "제품", "조회", "찾", "리스트"]):
        return True
    plan_text = json.dumps(plan, ensure_ascii=False, default=str)
    if _mentions_any_text(plan_text, [korean_product]):
        return True
    if _mentions_any_text(plan_text, ["\uc81c\ud488"]):
        return True
    if _mentions_any_text(plan_text, ["제품"]):
        return True
    return _mentions_any_text(plan_text, ["product_token_lookup", "component_token", "제품", "lookup"])


def _mentions_any_text(text: str, aliases: list[Any]) -> bool:
    upper = str(text or "").upper()
    compact = _compact_match_text(text)
    for alias in aliases:
        value = str(alias or "").strip()
        if not value:
            continue
        if value.upper() in upper:
            return True
        if _compact_match_text(value) and _compact_match_text(value) in compact:
            return True
    return False


def _compact_match_text(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in items:
        text = _clean_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        for key in ("text", "content", "value"):
            if data.get(key):
                return str(data[key]).strip()
    return str(value).strip()


def _analysis_instruction(plan: dict[str, Any]) -> str:
    function_case = plan.get("pandas_function_case") if isinstance(plan.get("pandas_function_case"), dict) else {}
    if function_case:
        function_name = str(function_case.get("function_name") or "").strip()
        input_text = str(function_case.get("input_text") or "").strip()
        steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
        later_steps = [
            step
            for step in steps[1:]
            if isinstance(step, dict) and str(step.get("operation") or "").strip() != "apply_pandas_function_case"
        ]
        if later_steps:
            return (
                f"먼저 선택된 pandas function case를 적용하세요. {function_name or 'the named helper'}를 "
                f"input_text={input_text!r}와 planned source DataFrame으로 호출합니다. matched row를 "
                "function-case step_id로 step_outputs에 저장하세요. 그 다음 remaining step_plan step을 순서대로 실행하고, "
                "downstream aggregation, ranking, detail output에는 step.input_step_id 또는 function-case output을 filtered input으로 사용하세요. "
                "최종 result_df는 helper output만이 아니라 전체 plan을 반영해야 합니다."
            )
        return (
            f"선택된 pandas function case를 helper {function_name or 'the named helper'}로 step_plan source_alias에 적용하세요. "
            f"helper 호출 시 input_text={input_text!r}를 사용하고, matched row를 result_df에 할당하세요."
        )
    kind = plan.get("analysis_kind")
    product_keys = plan.get("product_grain", [])
    if kind == "rank_wip_then_join_production":
        return (
            "step_plan[0].rank_groups로 user-facing group label을 만들고, 그 group label과 product_grain별로 WIP를 aggregate하세요. "
            "각 group label 안에서 별도로 rank하고 top_n을 유지한 뒤, ranked product key에 대해 PRODUCTION을 aggregate하고 left join하세요. "
            "이 질문은 multi-step입니다. 먼저 WIP에서 ranked product를 찾고, 그 product에 대한 production을 조회/aggregate합니다. "
            "plan.rank_group_output_column이 있으면 final group label column으로 사용하고, 없으면 RANK_GROUP을 사용하세요. "
            "raw rank_groups field는 label 할당과 filtering에만 사용합니다. analysis_output_columns에 명시되지 않았으면 final result에 포함하지 마세요. "
            f"최종 result_df column은 정확히 [group label, 'WIP_RANK'] + product_grain {product_keys} "
            "+ ['WIP', 'PRODUCTION']이어야 합니다. PRODUCTION_sum 또는 rank를 출력하지 마세요."
        )
    if kind == "detail_rows":
        return (
            "aggregation이나 groupby 없이 detail source row를 반환하세요. "
            "step_plan[0].source_aliases가 있으면 해당 alias들의 row를 반환하고 각 row의 출처가 보이도록 SOURCE_ALIAS를 추가하세요. "
            "그렇지 않으면 step_plan[0].source_alias에서 요청된 detail column을 반환하세요."
        )
    if kind == "rank_top_n":
        return (
            "먼저 step source DataFrame을 copy하고, plan['retrieval_jobs']의 해당 source_alias retrieval filter를 pandas mask로 적용하세요. "
            "그 다음 step_plan[0].metric을 "
            f"product_grain {product_keys}별로 aggregate하고 descending rank 후 top_n만 유지하세요."
        )
    if kind == "equipment_for_previous_products":
        return "product_grain을 사용해 plan.state_product_keys로 equipment row를 filter한 뒤 equipment detail column을 반환하세요."
    if kind == "equipment_count_for_previous_products":
        return (
            "product_grain을 사용해 plan.state_product_keys로 equipment row를 filter한 뒤 EQPID.nunique()로 EQP_COUNT를 계산하세요. "
            f"product_grain {product_keys}와 ['EQP_COUNT']를 반환하고, 이 계산에 lot_status를 사용하지 마세요."
        )
    if kind == "aggregate_join":
        return (
            "정확한 retrieval job source alias에서 PRODUCTION과 WIP를 aggregate하세요. "
            "product_grain/group_by가 비어 있으면 각 source에서 scalar total을 계산하고 pd.DataFrame([{...}])로 result row 하나를 직접 만드세요. "
            "scalar total DataFrame끼리 merge하지 마세요. product_grain/group_by가 있으면 각 metric을 해당 grain별로 aggregate하고 그 grain으로 outer join하세요."
        )
    if kind == "production_wip_target_rate":
        return (
            "PRODUCTION, WIP, OUT_PLAN을 product_grain별로 aggregate하고 join한 뒤 ACHIEVEMENT_RATE를 계산하세요. "
            f"최종 result_df column은 정확히 product_grain {product_keys}와 "
            "['WIP', 'PRODUCTION', 'OUT_PLAN', 'ACHIEVEMENT_RATE']이어야 합니다."
        )
    if kind == "low_output_vs_target":
        return (
            "PRODUCTION과 plan['target_column']을 product_grain별로 aggregate하세요. source column이 INPUT_PLAN 또는 OUT_PLAN이어도 "
            "최종 result에서는 선택된 target measure를 TARGET_QTY로 rename하세요. "
            "ACHIEVEMENT_RATE=PRODUCTION/TARGET_QTY, BALANCE=PRODUCTION-TARGET_QTY, "
            "LOW_OUTPUT_FLAG=ACHIEVEMENT_RATE < plan.get('threshold', 1.0)를 계산하세요. "
            "TARGET_QTY가 0이면 boolean mask로 ACHIEVEMENT_RATE를 0으로 설정하고, pd.inf, float('inf'), numpy, np.where를 사용하지 마세요. "
            f"최종 result_df column은 정확히 product_grain {product_keys}와 "
            "['PRODUCTION', 'TARGET_QTY', 'ACHIEVEMENT_RATE', 'BALANCE', 'LOW_OUTPUT_FLAG']이어야 합니다."
        )
    if kind == "lot_count_by_process":
        return "lot_status row를 OPER_SHORT_DESC별로 group하고 LOT_ID.nunique()로 LOT_COUNT를 계산하세요."
    if kind == "top_wip_process_hold_lot_in_tat":
        return (
            "이것은 sequential process-level analysis입니다. Step 1: WIP source에서 OPER_NAME별로 group하고 "
            "WIP를 sum한 뒤 descending sort, step_plan[0].top_n 유지, process output column을 OPER_SHORT_DESC로 rename하세요. "
            "Step 2: lot_status source에서는 OPER_SHORT_DESC/OPER_NAME이 top process에 포함된 row만 사용하세요. "
            "LOT_HOLD_STAT_CD가 HOLD/ONHOLD를 의미하는 row의 LOT_ID.nunique()로 HOLD_LOT_COUNT를 계산하고, "
            "선택된 process row의 IN_TAT numeric mean으로 AVG_IN_TAT를 계산하세요. Step 3: lot metric을 ranked WIP result에 "
            "left join하고 정확히 ['OPER_SHORT_DESC', 'WIP', 'HOLD_LOT_COUNT', 'AVG_IN_TAT']를 반환하세요."
        )
    if kind == "lot_quantity_summary":
        return (
            "LOT_COUNT=LOT_ID.nunique(), WF_QTY=sum(WF_QTY), DIE_QTY=sum(SUB_PROD_QTY)를 가진 row 하나를 반환하세요. "
            "최종 result_df column은 정확히 ['LOT_COUNT', 'WF_QTY', 'DIE_QTY']이어야 합니다."
        )
    if kind == "aggregate_wip_total":
        return "SCOPE=plan.scope_label 또는 ALL, WIP=sum(WIP)를 가진 row 하나를 반환하세요."
    if kind == "aggregate_previous_source":
        return (
            "새 retrieval이 아니라 restore된 previous runtime source row를 사용하세요. "
            "step_plan[0].source_alias가 있으면 그 row를 읽고, 없으면 사용 가능한 첫 source를 사용하세요. "
            "step_plan[0].group_by 또는 product_grain으로 group하고 plan.metric을 sum한 뒤 group column과 metric을 반환하세요. "
            "group_by가 비어 있으면 metric에 대한 total row 하나를 반환하세요."
        )
    if kind == "overall_production_wip_target":
        return (
            "PRODUCTION, WIP, OUT_PLAN을 각각 독립적으로 sum하고 row 하나를 반환하세요. "
            "OUT_PLAN을 TARGET으로 rename하지 마세요. 최종 result_df column에는 ['PRODUCTION', 'WIP', 'OUT_PLAN']이 포함되어야 합니다. "
            "SCOPE를 추가한다면 ALL로 설정하세요."
        )
    if kind == "date_split_production_plan_gap":
        return (
            "yesterday PRODUCTION과 today OUT_PLAN을 product_grain별로 aggregate하고 product_grain으로 join한 뒤 "
            "BALANCE=OUT_PLAN-PRODUCTION을 계산하세요. final result에서는 measure column 이름을 PRODUCTION, OUT_PLAN, "
            f"BALANCE로 유지하세요. 최종 result_df column은 정확히 product_grain {product_keys}와 "
            "['PRODUCTION', 'OUT_PLAN', 'BALANCE']이어야 합니다. yesterday_PRODUCTION 또는 today_OUT_PLAN 같은 이름을 사용하지 마세요."
        )
    if kind == "equipment_by_model":
        return (
            "equipment row를 EQP_MODEL별로 group하고 EQP_COUNT=EQPID.nunique(), PRESS_CNT=sum(PRESS_CNT)를 계산하세요. "
            "최종 result_df column은 정확히 ['EQP_MODEL', 'EQP_COUNT', 'PRESS_CNT']이어야 합니다. "
            "PRESS_CNT를 TOTAL_PRESS_CNT로 rename하지 말고 EQP_COUNT를 생략하지 마세요."
        )
    if _is_top_wip_product_oldest_lot_plan(plan):
        return (
            "이것은 sequential multi-source analysis입니다. 먼저 WIP source에서 WIP를 product_grain "
            f"{product_keys}별로 aggregate하고 WIP descending sort 후 top product를 유지하세요. 그 다음 lot_status row를 "
            "같은 product key로 filter하고 IN_TAT descending sort 후 가장 오래된 top 1 LOT만 유지하세요. product_grain과 "
            "['WIP', 'LOT_ID', 'IN_TAT']를 반환하세요. 실제 source row가 이 step 이후 비어 있는 경우가 아니면 empty contract DataFrame을 반환하지 마세요."
        )
    return (
        "제공된 source DataFrame에 대해 normalized intent plan과 step_plan을 사용해 요청된 pandas analysis를 수행하세요. "
        "plan을 적용한 뒤 실제 source row가 비어 있는 경우가 아니면 empty contract DataFrame을 만들지 마세요."
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
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(
            name="specialized_functions_text",
            display_name="Specialized Functions",
            value="",
            required=False,
        ),
    ]
    outputs = [
        Output(name="pandas_prompt", display_name="Pandas Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt(self) -> Message:
        prompt_payload = build_pandas_prompt_payload(
            getattr(self, "payload", None),
            getattr(self, "specialized_functions_text", ""),
        )

        self.status = {
            "prompt_type": prompt_payload.get("prompt_type", "pandas_code"),
            "chars": len(prompt_payload["prompt"]),
            "sources": list(prompt_payload.get("source_summary", {}).keys()),
            "function_cases": len(prompt_payload.get("pandas_function_cases", [])),
        }
        return Message(text=prompt_payload["prompt"])

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 의도 계획과 source preview를 바탕으로 pandas 코드 생성 LLM에 보낼 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt_payload(self) -> Data:
        return Data(
            data=build_pandas_prompt_payload(
                getattr(self, "payload", None),
                getattr(self, "specialized_functions_text", ""),
            )
        )
