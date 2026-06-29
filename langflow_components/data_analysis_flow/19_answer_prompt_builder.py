# 파일 설명: 19 Answer Prompt Builder Langflow custom component 파일입니다.
# 흐름 역할: 분석 결과, 의도, 적용 필터를 바탕으로 최종 답변 작성 LLM에 보낼 프롬프트를 만듭니다.
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
# 처리 역할: 분석 결과, 의도, 적용 필터를 바탕으로 최종 답변 작성 LLM에 보낼 프롬프트를 만듭니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_answer_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    if payload.get("direct_response_ready"):
        prompt = json.dumps(
            {"answer_message": payload.get("answer_message", "")},
            ensure_ascii=False,
        )
        return {
            "prompt": prompt,
            "payload": _compact_prompt_payload(payload),
            "prompt_type": "direct_response_skip",
            "answer_context": {
                "question": (payload.get("request") or {}).get("question", "") if isinstance(payload.get("request"), dict) else "",
                "data": payload.get("data", {}),
                "metadata_qa": payload.get("metadata_qa", {}),
            },
        }
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    source_results = payload.get("source_results") if isinstance(payload.get("source_results"), list) else []
    metadata_context = payload.get("metadata_context") if isinstance(payload.get("metadata_context"), dict) else {}

    answer_context = {
        "question": request.get("question", ""),
        "intent_type": plan.get("intent_type"),
        "analysis_kind": plan.get("analysis_kind"),
        "reasoning_steps": plan.get("reasoning_steps", []),
        "pandas_reasoning_steps": analysis.get("reasoning_steps", []),
        "function_case_trace": analysis.get("function_case_trace", {}),
        "data": {
            "columns": analysis.get("columns", []),
            "rows": analysis.get("rows", [])[:50],
            "row_count": analysis.get("row_count", 0),
        },
        "source_results": _compact_source_results(source_results),
        "column_standardization": _column_standardization_context(plan),
        "metadata_context": metadata_context,
        "info": payload.get("info", []),
        "warnings": payload.get("warnings", []),
        "errors": payload.get("errors", []) + analysis.get("errors", []),
    }
    prompt = "\n".join(
        [
            "당신은 Langflow 제조 데이터 에이전트의 최종 답변 작성 노드입니다.",
            "한국어로 답변하세요.",
            "제공된 result data와 metadata context만 사용하세요. 숫자를 임의로 만들지 마세요.",
            "간결하게 답하되 적용 조건, 사용 dataset, 중요한 caveat는 포함하세요.",
            "answer_message 안에는 Markdown table, tab-separated table, plain text table, row-by-row result listing을 포함하지 마세요.",
            "downstream Answer Message Adapter가 data.rows에서 result table을 deterministic하게 렌더링합니다. answer_message는 narrative text만 포함해야 합니다.",
            "컬럼명 규칙: column_standardization이 physical source column을 standard analysis column으로 매핑했다면, 그 physical-vs-standard 차이를 metadata 문제로 설명하지 마세요.",
            "예를 들어 PKG1/PKG2/MCPSALENO가 PKG_TYPE1/PKG_TYPE2/MCP_NO로 매핑되었다면 standard column 기준으로 join을 설명하고, source가 physical name을 썼다는 이유만으로 사용자에게 metadata 수정을 요청하지 마세요.",
            "INPUT 계획과 INPUT계획, OUT 계획과 OUT계획처럼 공백만 다른 수량 컬럼명 차이는 source 컬럼 오류나 사용자 수정 요청으로 설명하지 마세요. metadata/source summary에 보이는 실제 컬럼명을 기준으로 처리된 것으로 설명하세요.",
            "error가 있으면 무엇이 실패했는지와 사용자가 무엇을 다시 시도할 수 있는지 설명하세요.",
            "",
            "plain Korean text 또는 아래 schema의 엄격한 JSON object 하나만 반환하세요:",
            json.dumps({"answer_message": "result table이 없는 한국어 서술형 답변 텍스트"}, ensure_ascii=False, indent=2),
            "",
            "답변 context:",
            json.dumps(answer_context, ensure_ascii=False, indent=2),
        ]
    )
    return {"prompt": prompt, "payload": _compact_prompt_payload(payload), "prompt_type": "final_answer", "answer_context": answer_context}


def _compact_source_results(source_results: list[Any]) -> list[dict[str, Any]]:
    compact = []
    for result in source_results:
        if not isinstance(result, dict):
            continue
        compact.append(
            {
                "source_alias": result.get("source_alias"),
                "dataset_key": result.get("dataset_key"),
                "source_type": result.get("source_type"),
                "row_count": result.get("row_count"),
                "columns": result.get("columns", []),
                "applied_params": result.get("applied_params", {}),
                "applied_filters": result.get("applied_filters", []),
                "data_ref": result.get("data_ref"),
            }
        )
    return compact


def _compact_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: deepcopy(value)
        for key, value in payload.items()
        if key not in {"metadata", "runtime_sources", "state"}
    }
    if isinstance(compact.get("source_results"), list):
        compact["source_results"] = _compact_source_results(compact["source_results"])
    if isinstance(compact.get("analysis"), dict):
        compact["analysis"] = {
            key: deepcopy(value)
            for key, value in compact["analysis"].items()
            if key not in {"rows", "analysis_code", "pandas_code_json"}
        }
    if isinstance(compact.get("data"), dict):
        compact["data"] = {key: deepcopy(value) for key, value in compact["data"].items() if key != "rows"}
    return compact


def _column_standardization_context(plan: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    context: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        mappings: dict[str, Any] = {}
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mapping = job.get(field) if isinstance(job.get(field), dict) else {}
            for standard, candidates in mapping.items():
                standard_text = str(standard or "").strip()
                if not standard_text:
                    continue
                values = candidates if isinstance(candidates, list) else [candidates]
                clean_values = [str(item) for item in values if str(item or "").strip() and str(item) != standard_text]
                if clean_values:
                    mappings.setdefault(standard_text, [])
                    mappings[standard_text].extend(clean_values)
        if mappings:
            context.append(
                {
                    "source_alias": job.get("source_alias") or job.get("dataset_key"),
                    "dataset_key": job.get("dataset_key"),
                    "standardize_columns": True,
                    "mappings": {key: _unique(values) for key, values in mappings.items()},
                }
            )
    return context


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 19 Answer Prompt Builder
# Langflow 표시 설명: 분석 결과, 의도, 적용 필터를 바탕으로 최종 답변 작성 LLM에 보낼 프롬프트를 만듭니다.
class AnswerPromptBuilder(Component):

    display_name = "19 Answer Prompt Builder"
    description = "분석 결과, 의도, 적용 필터를 바탕으로 최종 답변 작성 LLM에 보낼 프롬프트를 만듭니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="answer_prompt", display_name="Answer Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 분석 결과, 의도, 적용 필터를 바탕으로 최종 답변 작성 LLM에 보낼 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt(self) -> Message:
        prompt_payload = build_answer_prompt_payload(getattr(self, "payload", None))

        context = prompt_payload.get("answer_context", {})
        self.status = {
            "prompt_type": prompt_payload.get("prompt_type", "final_answer"),
            "chars": len(prompt_payload["prompt"]),
            "rows": (context.get("data") or {}).get("row_count", 0),
        }
        return Message(text=prompt_payload["prompt"])

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 분석 결과, 의도, 적용 필터를 바탕으로 최종 답변 작성 LLM에 보낼 프롬프트를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_prompt_payload(self) -> Data:
        return Data(data=build_answer_prompt_payload(getattr(self, "payload", None)))
