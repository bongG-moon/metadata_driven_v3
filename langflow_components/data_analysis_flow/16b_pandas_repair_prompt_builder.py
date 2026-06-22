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
        reason = str(repair.get("reason") or "Pandas repair is not required.")
        prompt = "\n".join(
            [
                "Pandas repair is not required for this payload.",
                f"Repair route: {route}",
                f"Reason: {reason}",
                "Do not generate pandas code for this branch.",
                "The downstream repair executor should pass through the existing payload unchanged.",
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
    prompt = "\n".join(
        [
            "You repair failed pandas code for a Langflow manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Generate corrected Python pandas code that uses only the provided variables: pd, sources, plan, state.",
            "sources is a dict mapping source_alias to pandas DataFrame.",
            "plan and state are Python dicts. Use plan['key'], plan.get('key'), state.get('key'); never use plan.key or state.key.",
            "The code must assign the final pandas DataFrame to result_df.",
            "Do not import modules. Do not read/write files. Do not use network, OS, eval, exec, open, subprocess, numpy, np, or np.where.",
            "Do not use pd.inf, float('inf'), or infinity replacement. Avoid division by zero with boolean masks before dividing.",
            "Fix the failed code using the same intent plan and available source DataFrames. Keep result columns aligned to the requested output contract.",
            "",
            "Failed execution context:",
            json.dumps(context, ensure_ascii=False, indent=2),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "code": "Corrected Python code. It must set result_df.",
                    "output_columns": ["column names expected in result_df"],
                    "reasoning_steps": ["short explanation of the repair"],
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
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}
    return {
        "request": deepcopy(request),
        "intent_plan": deepcopy(payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}),
        "payload_summary": _payload_summary(payload),
        "runtime_source_summary": _runtime_source_summary(runtime_sources),
        "state_summary": _state_summary(state),
        "failed_pandas_code_json": deepcopy(
            analysis.get("pandas_code_json") if isinstance(analysis.get("pandas_code_json"), dict) else {}
        ),
        "executed_code": str(analysis.get("analysis_code") or ""),
        "errors": _as_text_list(analysis.get("errors")),
        "analysis_columns": _as_text_list(analysis.get("columns")),
        "analysis_row_count": analysis.get("row_count", 0),
        "llm_text_preview": str(analysis.get("llm_text_preview") or "")[:1200],
    }


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
