# 파일 설명: 06 Previous Result Restore Merger Langflow custom component 파일입니다.
# 흐름 역할: 선택적으로 복원된 이전 결과를 원래 데이터 분석 payload에 다시 병합합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 선택적으로 복원된 이전 결과를 원래 데이터 분석 payload에 다시 병합합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def merge_previous_result_restore(main_payload_value: Any, restored_payload_value: Any = None) -> dict[str, Any]:
    main_payload = _payload(main_payload_value)
    restored_payload = _payload(restored_payload_value)
    decision = main_payload.get("previous_result_restore") if isinstance(main_payload.get("previous_result_restore"), dict) else {}
    required = bool(decision.get("required"))

    if required and restored_payload:
        result = deepcopy(restored_payload)
        merged = deepcopy(result.get("previous_result_restore")) if isinstance(result.get("previous_result_restore"), dict) else deepcopy(decision)
        merged["used_loader_payload"] = True
        merged.setdefault("branch", "restore_full_previous_rows")
        result["previous_result_restore"] = merged
        return result

    result = deepcopy(main_payload)
    merged = deepcopy(decision)
    merged["used_loader_payload"] = False
    if not merged.get("branch"):
        merged["branch"] = "skip_restore"
    result["previous_result_restore"] = merged
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 06 Previous Result Restore Merger
# Langflow 표시 설명: 선택적으로 복원된 이전 결과를 원래 데이터 분석 payload에 다시 병합합니다.
class PreviousResultRestoreMerger(Component):

    display_name = "06 Previous Result Restore Merger"
    description = "선택적으로 복원된 이전 결과를 원래 데이터 분석 payload에 다시 병합합니다."
    icon = "GitMerge"
    inputs = [
        DataInput(name="main_payload", display_name="Main Payload", required=True),
        DataInput(name="restored_payload", display_name="Restored Payload", required=False),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 선택적으로 복원된 이전 결과를 원래 데이터 분석 payload에 다시 병합합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:

        result = merge_previous_result_restore(getattr(self, "main_payload", None), getattr(self, "restored_payload", None))
        self.status = result.get("previous_result_restore", {})
        return Data(data=result)
