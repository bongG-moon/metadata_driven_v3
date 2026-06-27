# 파일 설명: 12 Source Retrieval Merger Langflow custom component 파일입니다.
# 흐름 역할: Dummy, Oracle, H-API, Datalake, Goodocs 조회 branch 결과를 하나의 source payload로 병합합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations
from copy import deepcopy
from typing import Any
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: Dummy, Oracle, H-API, Datalake, Goodocs 조회 branch 결과를 하나의 source payload로 병합합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def merge_source_retrieval_payloads(*payload_values: Any) -> dict[str, Any]:
    merged_results = []
    for value in payload_values:
        payload = _payload(value)
        retrieval = payload.get("retrieval_payload") if isinstance(payload.get("retrieval_payload"), dict) else payload
        if retrieval.get("skipped"):
            continue
        for item in retrieval.get("source_results", []):
            if isinstance(item, dict):
                merged_results.append(deepcopy(item))
    return {"retrieval_payload": {"source_results": merged_results}}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 12 Source Retrieval Merger
# Langflow 표시 설명: Dummy, Oracle, H-API, Datalake, Goodocs 조회 branch 결과를 하나의 source payload로 병합합니다.
class SourceRetrievalMerger(Component):

    display_name = "12 Source Retrieval Merger"
    description = "Dummy, Oracle, H-API, Datalake, Goodocs 조회 branch 결과를 하나의 source payload로 병합합니다."
    inputs = [
        DataInput(name="dummy_retrieval", display_name="Dummy Retrieval", required=False),
        DataInput(name="oracle_retrieval", display_name="Oracle Retrieval", required=False),
        DataInput(name="h_api_retrieval", display_name="H-API Retrieval", required=False),
        DataInput(name="datalake_retrieval", display_name="Datalake Retrieval", required=False),
        DataInput(name="goodocs_retrieval", display_name="Goodocs Retrieval", required=False),
    ]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]


    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: Dummy, Oracle, H-API, Datalake, Goodocs 조회 branch 결과를 하나의 source payload로 병합합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        return Data(
            data=merge_source_retrieval_payloads(
                getattr(self, "dummy_retrieval", None),
                getattr(self, "oracle_retrieval", None),
                getattr(self, "h_api_retrieval", None),
                getattr(self, "datalake_retrieval", None),
                getattr(self, "goodocs_retrieval", None),
            )
        )
