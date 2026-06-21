# 파일 설명: 02 Table Catalog Text Refinement Normalizer Langflow custom component 파일입니다.
# 흐름 역할: table catalog 설명 정제 LLM JSON을 compact table catalog payload에 반영합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: table catalog 설명 정제 LLM JSON을 compact table catalog payload에 반영합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def normalize_table_catalog_refinement(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    llm_text = _text(llm_response_value)
    parsed = _extract_json_object(llm_text)
    if not parsed:
        parsed = {
            "refined_text": str(payload.get("raw_text") or ""),
            "needs_more_input": True,
            "missing_information": [{"field": "llm_json", "reason": "정제 LLM 응답에서 JSON을 찾지 못했습니다.", "example_user_input": ""}],
            "assumptions": [],
            "remaining_questions": [],
        }
    next_payload = dict(payload)
    next_payload["refined_text"] = str(parsed.get("refined_text") or payload.get("raw_text") or "").strip()
    next_payload["refinement"] = {
        "needs_more_input": bool(parsed.get("needs_more_input", False)),
        "missing_information": _as_list(parsed.get("missing_information")),
        "assumptions": _as_list(parsed.get("assumptions")),
        "remaining_questions": _as_list(parsed.get("remaining_questions")),
    }
    next_payload.setdefault("trace", {})["refinement_preview"] = llm_text[:1000]
    return next_payload


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        for key in ("llm_text", "text", "content", "response"):
            if data.get(key):
                return str(data[key])
    for attr in ("text", "content"):
        if getattr(value, attr, None):
            return str(getattr(value, attr))
    return str(value)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 02 Table Catalog Text Refinement Normalizer
# Langflow 표시 설명: table catalog 설명 정제 LLM JSON을 compact table catalog payload에 반영합니다.
class TableCatalogTextRefinementNormalizer(Component):

    display_name = "02 Table Catalog Text Refinement Normalizer"
    description = "table catalog 설명 정제 LLM JSON을 compact table catalog payload에 반영합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: table catalog 설명 정제 LLM JSON을 compact table catalog payload에 반영합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = normalize_table_catalog_refinement(getattr(self, "payload", None), getattr(self, "llm_response", ""))

        self.status = {
            "needs_more_input": (result.get("refinement") or {}).get("needs_more_input", False),
            "missing": len((result.get("refinement") or {}).get("missing_information", [])),
        }
        return Data(data=result)
