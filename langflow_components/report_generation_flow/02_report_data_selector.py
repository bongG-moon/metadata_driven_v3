# 파일 설명: 02 Report Data Selector Langflow custom component 파일입니다.
# 흐름 역할: 리포트 작성에 사용할 수 있는 이전 분석 결과와 data_ref 후보를 선택합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 리포트 작성에 사용할 수 있는 이전 분석 결과와 data_ref 후보를 선택합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def select_report_data(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    data_refs = []
    if isinstance(current_data.get("data_ref"), dict):
        data_refs.append(deepcopy(current_data["data_ref"]))
    if isinstance(state.get("followup_source_results"), list):
        for item in state["followup_source_results"]:
            if isinstance(item, dict) and isinstance(item.get("data_ref"), dict):
                data_refs.append(deepcopy(item["data_ref"]))

    report = deepcopy(payload.get("report")) if isinstance(payload.get("report"), dict) else {}
    report["data_selection"] = {
        "mode": "previous_state" if current_data else "needs_analysis_source",
        "columns": list(current_data.get("columns", [])) if isinstance(current_data.get("columns"), list) else [],
        "row_count": int(current_data.get("row_count") or 0),
        "data_refs": data_refs,
    }
    result = deepcopy(payload)
    result["report"] = report
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 02 Report Data Selector
# Langflow 표시 설명: 리포트 작성에 사용할 수 있는 이전 분석 결과와 data_ref 후보를 선택합니다.
class ReportDataSelector(Component):

    display_name = "02 Report Data Selector"
    description = "리포트 작성에 사용할 수 있는 이전 분석 결과와 data_ref 후보를 선택합니다."
    icon = "Database"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 리포트 작성에 사용할 수 있는 이전 분석 결과와 data_ref 후보를 선택합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = select_report_data(getattr(self, "payload", None))
        self.status = (result.get("report") or {}).get("data_selection", {})
        return Data(data=result)
