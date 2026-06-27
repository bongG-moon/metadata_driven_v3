# 파일 설명: 04 Previous Result Restore Router Langflow custom component 파일입니다.
# 흐름 역할: 이전 결과 data_ref를 지금 질문에서 복원해야 하는지 판단하고 복원 branch payload를 분리합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data

# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 이전 결과 data_ref를 지금 질문에서 복원해야 하는지 판단하고 복원 branch payload를 분리합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def route_previous_result_restore(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    data_ref = current_data.get("data_ref") if isinstance(current_data.get("data_ref"), dict) else {}
    result_ref_count = 1 if _is_mongo_ref(data_ref) else 0
    source_ref_count = _source_ref_count(state)
    restore_ref_count = result_ref_count + source_ref_count

    requested_mode = _restore_mode(payload, plan)
    required = requested_mode == "full" and restore_ref_count > 0
    decision = {
        "required": required,
        "branch": "restore_full_previous_rows" if required else "skip_restore",
        "restore_mode": "full" if required else "summary",
        "loader_mode": "full" if required else "preview",
        "requested_mode": requested_mode,
        "reason": _reason(required, requested_mode, current_data, data_ref, source_ref_count),
        "data_ref": deepcopy(data_ref) if _is_mongo_ref(data_ref) else {},
        "source_ref_count": source_ref_count,
        "restore_ref_count": restore_ref_count,
        "row_count": _int_value(current_data.get("row_count"), 0),
        "preview_row_count": len(current_data.get("rows", [])) if isinstance(current_data.get("rows"), list) else 0,
    }

    main_payload = deepcopy(payload)
    main_payload["previous_result_restore"] = deepcopy(decision)

    if required:
        restore_payload = deepcopy(payload)
        restore_payload["previous_result_restore"] = deepcopy(decision)
        restore_payload["previous_result_restore_mode"] = "full"
        restore_payload["restore_previous_result_mode"] = "full"
    else:
        restore_payload = {
            "previous_result_restore": deepcopy(decision),
            "previous_result_restore_mode": "summary",
            "restore_previous_result_mode": "summary",
        }

    return {
        "payload": main_payload,
        "restore_payload": restore_payload,
        "restore_decision": decision,
    }


def _restore_mode(payload: dict[str, Any], plan: dict[str, Any]) -> str:
    values = [
        plan.get("previous_result_restore_mode"),
        plan.get("restore_previous_result_mode"),
        plan.get("restore_mode"),
        payload.get("previous_result_restore_mode"),
        payload.get("restore_previous_result_mode"),
        payload.get("restore_mode"),
    ]
    if _truthy(plan.get("requires_full_previous_result_restore")):
        return "full"
    if _truthy(payload.get("requires_full_previous_result_restore")):
        return "full"
    for value in values:
        text = str(value or "").strip().lower()
        if text in {"full", "all", "rows", "restore_full", "restore_full"}:
            return "full"
        if text in {"summary", "preview", "metadata", "none", "skip"}:
            return "summary"
    followup = plan.get("followup") if isinstance(plan.get("followup"), dict) else {}
    if _truthy(followup.get("requires_previous_rows")) or _truthy(followup.get("needs_full_previous_data")):
        return "full"
    return "summary"


def _reason(
    required: bool,
    requested_mode: str,
    current_data: dict[str, Any],
    data_ref: dict[str, Any],
    source_ref_count: int,
) -> str:
    if required:
        if _is_mongo_ref(data_ref) and source_ref_count:
            return "후속 분석에서 이전 결과와 이전 조회 원본 전체 row가 필요하므로 MongoDB data_ref를 전체 복원합니다."
        if _is_mongo_ref(data_ref):
            return "후속 분석에서 이전 결과 전체 row가 필요하므로 MongoDB data_ref에서 이전 결과를 전체 복원합니다."
        return "후속 분석에서 이전 조회 원본 전체 row가 필요하므로 MongoDB source data_ref를 전체 복원합니다."
    if requested_mode != "full":
        return "현재 분석 계획은 이전 결과의 key/preview/summary만으로 충분하므로 전체 복원을 건너뜁니다."
    if not _is_mongo_ref(data_ref) and source_ref_count <= 0:
        return "전체 복원 요청은 있었지만 이전 state에 MongoDB data_ref가 없어 복원하지 않습니다."
    if not current_data:
        return "이전 current_data가 없어 복원하지 않습니다."
    return "이전 결과 복원 조건을 충족하지 않아 전체 복원을 건너뜁니다."


def _source_ref_count(state: dict[str, Any]) -> int:
    seen: set[str] = set()
    source_results = state.get("followup_source_results")
    if isinstance(source_results, list):
        for item in source_results:
            if isinstance(item, dict):
                _add_ref_id(seen, item.get("data_ref"))
    runtime_source_refs = state.get("runtime_source_refs") if isinstance(state.get("runtime_source_refs"), dict) else {}
    for data_ref in runtime_source_refs.values():
        _add_ref_id(seen, data_ref)
    return len(seen)


def _add_ref_id(seen: set[str], data_ref: Any) -> None:
    if _is_mongo_ref(data_ref):
        seen.add(str(data_ref.get("ref_id")))


def _is_mongo_ref(value: Any) -> bool:
    return isinstance(value, dict) and value.get("store") == "mongodb" and bool(value.get("ref_id"))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "full", "required"}


def _int_value(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 04 Previous Result Restore Router
# Langflow 표시 설명: 이전 결과 data_ref를 지금 질문에서 복원해야 하는지 판단하고 복원 branch payload를 분리합니다.
class PreviousResultRestoreRouter(Component):

    display_name = "04 Previous Result Restore Router"
    description = "이전 결과 data_ref를 지금 질문에서 복원해야 하는지 판단하고 복원 branch payload를 분리합니다."
    icon = "GitBranch"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="payload_out", display_name="Payload", method="build_payload"),
        Output(name="restore_payload", display_name="Restore Payload", method="build_restore_payload"),
        Output(name="restore_decision", display_name="Restore Decision", method="build_restore_decision"),
    ]


    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 이전 결과 data_ref를 지금 질문에서 복원해야 하는지 판단하고 복원 branch payload를 분리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def _result(self) -> dict[str, Any]:
        return route_previous_result_restore(getattr(self, "payload", None))

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 이전 결과 data_ref를 지금 질문에서 복원해야 하는지 판단하고 복원 branch payload를 분리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = self._result()
        self.status = result.get("restore_decision", {})
        return Data(data=result["payload"])

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 이전 결과 data_ref를 지금 질문에서 복원해야 하는지 판단하고 복원 branch payload를 분리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_restore_payload(self) -> Data:
        return Data(data=self._result()["restore_payload"])

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 이전 결과 data_ref를 지금 질문에서 복원해야 하는지 판단하고 복원 branch payload를 분리합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_restore_decision(self) -> Data:
        return Data(data=self._result()["restore_decision"])
