# 파일 설명: 16A Pandas Repair Payload Builder Langflow custom component 파일입니다.
# 흐름 역할: pandas 실행 실패가 LLM repair 대상인지 판단하고 repair용 payload를 구성합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, Output
from lfx.schema.data import Data


PANDAS_WARNING_PREFIX = "pandas_executor:"
DEFAULT_REPAIR_MAX_ATTEMPTS = 1
REPAIR_ATTEMPT_OPTIONS = ["0", "1", "2"]


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: pandas 실행 실패가 LLM repair 대상인지 판단하고 repair용 payload를 구성합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_pandas_repair_payload(payload_value: Any, max_attempts: Any = DEFAULT_REPAIR_MAX_ATTEMPTS) -> dict[str, Any]:
    payload = _payload(payload_value)
    decision = _pandas_repair_decision(payload, max_attempts)
    next_payload = deepcopy(payload)
    next_payload["pandas_repair"] = decision
    next_payload["pandas_execution_branch"] = {
        "route": decision["route"],
        "repair_required": decision["required"],
        "reason": decision["reason"],
    }
    if decision["required"]:
        next_payload["warnings"] = _without_pandas_executor_warnings(next_payload.get("warnings", []))
        next_payload["pandas_retry_attempt"] = decision["attempt"]
    return next_payload


def _pandas_repair_decision(payload: dict[str, Any], max_attempts: Any = DEFAULT_REPAIR_MAX_ATTEMPTS) -> dict[str, Any]:
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    errors = _as_text_list(analysis.get("errors"))
    attempt = _positive_int(payload.get("pandas_retry_attempt"), default=0, minimum=0) + 1
    max_count = _positive_int(max_attempts, default=DEFAULT_REPAIR_MAX_ATTEMPTS, minimum=0)
    required = bool(errors) and attempt <= max_count
    if not errors:
        reason = "Pandas execution succeeded; repair is not required."
    elif attempt > max_count:
        reason = f"Pandas repair max attempts exceeded: {max_count}."
    else:
        reason = "Pandas execution failed; repair prompt should be generated from the failed code and error context."
    route = "repair" if required else ("success" if not errors else "failed")
    return {
        "required": required,
        "route": route,
        "attempt": attempt,
        "max_attempts": max_count,
        "errors": errors,
        "reason": reason,
        "context": _pandas_repair_context(payload),
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


def _without_pandas_executor_warnings(warnings: Any) -> list[Any]:
    result = []
    for item in warnings if isinstance(warnings, list) else []:
        if str(item).startswith(PANDAS_WARNING_PREFIX):
            continue
        result.append(item)
    return result


def _as_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item) for item in value if str(item or "").strip()]


def _positive_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, parsed)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 16A Pandas Repair Payload Builder
# Langflow 표시 설명: pandas 실행 실패가 LLM repair 대상인지 판단하고 repair용 payload를 구성합니다.
class PandasRepairPayloadBuilder(Component):

    display_name = "16A Pandas Repair Payload Builder"
    description = "pandas 실행 실패가 LLM repair 대상인지 판단하고 repair용 payload를 구성합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        DropdownInput(
            name="max_attempts",
            display_name="Max Repair Attempts",
            options=REPAIR_ATTEMPT_OPTIONS,
            value=str(DEFAULT_REPAIR_MAX_ATTEMPTS),
            advanced=True,

        ),
    ]
    outputs = [
        Output(name="payload_out", display_name="Repair Payload", method="build_payload"),
    ]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: pandas 실행 실패가 LLM repair 대상인지 판단하고 repair용 payload를 구성합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = build_pandas_repair_payload(
            getattr(self, "payload", None),
            getattr(self, "max_attempts", DEFAULT_REPAIR_MAX_ATTEMPTS),
        )
        repair = result.get("pandas_repair") if isinstance(result.get("pandas_repair"), dict) else {}
        self.status = {
            "route": repair.get("route", ""),
            "repair_required": repair.get("required", False),
            "attempt": repair.get("attempt", 0),
            "max_attempts": repair.get("max_attempts", DEFAULT_REPAIR_MAX_ATTEMPTS),
            "errors": len(repair.get("errors", [])),
        }
        return Data(data=result)
