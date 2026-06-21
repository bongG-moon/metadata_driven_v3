# 파일 설명: 04 Route Classifier Normalizer Langflow custom component 파일입니다.
# 흐름 역할: 선택적 route LLM 응답을 정규화해 metadata QA, data analysis, report, diagnosis 중 하나로 확정합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


ALLOWED_ROUTES = {"direct_answer", "metadata_qa", "data_analysis", "report_generation", "operations_diagnosis"}
FLOW_BY_ROUTE = {
    "direct_answer": "metadata_qa_flow",
    "metadata_qa": "metadata_qa_flow",
    "data_analysis": "data_analysis_flow",
    "report_generation": "report_generation_flow",
    "operations_diagnosis": "operations_diagnosis_flow",
}
DIRECT_ACTIONS = {"greeting", "help"}
METADATA_ACTIONS = {"catalog_list", "dataset_examples", "dataset_detail", "dataset_query", "domain_search"}
ALL_ACTIONS = DIRECT_ACTIONS | METADATA_ACTIONS


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 선택적 route LLM 응답을 정규화해 metadata QA, data analysis, report, diagnosis 중 하나로 확정합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def normalize_route_classifier_payload(payload_value: Any, llm_response_value: Any = "") -> dict[str, Any]:
    payload = _payload(payload_value)
    metadata_route = deepcopy(payload.get("metadata_route")) if isinstance(payload.get("metadata_route"), dict) else {}
    if not metadata_route:
        metadata_route = {
            "route": "data_analysis",
            "metadata_action": "",
            "confidence": "low",
            "route_confidence": "low",
            "route_source": "rule",
            "route_llm_required": True,
            "reason": "No route candidate context was provided.",
        }

    if not metadata_route.get("route_llm_required"):
        next_payload = deepcopy(payload)
        metadata_route["route_llm_used"] = False
        metadata_route.setdefault("route_source", "rule")
        metadata_route.setdefault("route_confidence", metadata_route.get("confidence", "high"))
        next_payload["metadata_route"] = metadata_route
        return next_payload

    llm_text = _text(llm_response_value)
    llm_json = _extract_json_object(llm_text)
    normalized, error = _normalize_llm_route(llm_json, metadata_route, payload)
    next_payload = deepcopy(payload)
    if error:
        warnings = list(next_payload.get("warnings", [])) if isinstance(next_payload.get("warnings"), list) else []
        warnings.append(f"route_classifier: {error}; using provisional route candidate.")
        next_payload["warnings"] = warnings
    normalized["route_llm_required"] = True
    normalized["route_llm_used"] = bool(not error)
    normalized["llm_route_json"] = llm_json
    normalized["llm_text_preview"] = llm_text[:1200]
    next_payload["metadata_route"] = normalized
    return next_payload


def _normalize_llm_route(
    llm_json: dict[str, Any],
    rule_route: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    if not isinstance(llm_json, dict) or not llm_json:
        fallback = deepcopy(rule_route)
        fallback.setdefault("route", "data_analysis")
        fallback.setdefault("metadata_action", "")
        fallback["route_source"] = "rule"
        fallback["route_confidence"] = fallback.get("confidence", "low")
        return fallback, "LLM route response did not contain a JSON object"

    route = str(llm_json.get("route") or "").strip()
    if route not in ALLOWED_ROUTES:
        fallback = deepcopy(rule_route)
        fallback["route_source"] = "rule"
        fallback["route_confidence"] = fallback.get("confidence", "low")
        return fallback, f"unsupported route '{route}'"

    action = str(
        llm_json.get("metadata_action")
        or llm_json.get("metadata_question_type")
        or llm_json.get("question_type")
        or llm_json.get("action")
        or ""
    ).strip()
    if route == "direct_answer":
        action = action if action in DIRECT_ACTIONS else "help"
    elif route == "metadata_qa":
        if action not in METADATA_ACTIONS:
            fallback = deepcopy(rule_route)
            fallback["route_source"] = "rule"
            fallback["route_confidence"] = fallback.get("confidence", "low")
            return fallback, f"unsupported metadata action '{action}'"
    else:
        action = ""

    datasets = _datasets(payload)
    raw_target_dataset = str(llm_json.get("target_dataset") or "").strip()
    if route == "metadata_qa" and not raw_target_dataset:
        raw_target_dataset = str(rule_route.get("candidate_target_dataset") or rule_route.get("target_dataset") or "").strip()
    target_dataset = _resolve_dataset(raw_target_dataset, datasets)
    target_family = str(llm_json.get("target_family") or "").strip()
    if target_dataset and isinstance(datasets.get(target_dataset), dict):
        target_family = str(datasets[target_dataset].get("dataset_family") or target_family)
    elif target_family and target_family not in _dataset_families(datasets):
        target_family = ""
    if route == "metadata_qa" and not target_family:
        target_family = str(rule_route.get("candidate_target_family") or rule_route.get("target_family") or "").strip()
        if target_family not in _dataset_families(datasets):
            target_family = ""
    if route == "metadata_qa" and not target_dataset and target_family:
        target_dataset = _preferred_dataset_for_family(target_family, datasets)

    confidence = str(llm_json.get("confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    selected_flow = _clean(llm_json.get("selected_flow")) or _clean(rule_route.get("selected_flow")) or FLOW_BY_ROUTE.get(route, "")
    api_url = _clean(llm_json.get("api_url") or llm_json.get("target_api_url") or rule_route.get("api_url"))
    flow_id = _clean(llm_json.get("flow_id") or rule_route.get("flow_id"))

    normalized = deepcopy(rule_route)
    normalized.update(
        {
            "route": route,
            "selected_flow": selected_flow,
            "api_url": api_url,
            "flow_id": flow_id,
            "metadata_action": action,
            "metadata_question_type": action if route == "metadata_qa" else "",
            "target_dataset": target_dataset,
            "target_family": target_family,
            "target_term": str(llm_json.get("target_term") or rule_route.get("target_term") or "").strip(),
            "confidence": confidence,
            "route_confidence": confidence,
            "route_source": "llm",
            "reason": str(llm_json.get("reason") or "Route selected by the lightweight LLM route classifier.").strip(),
            "rule_route": deepcopy(rule_route),
        }
    )
    return normalized, ""


def _resolve_dataset(value: str, datasets: dict[str, dict[str, Any]]) -> str:
    text = value.strip()
    if not text:
        return ""
    if text in datasets:
        return text
    normalized = _normalize(text)
    for key, item in datasets.items():
        display = str(item.get("display_name") or "")
        if normalized in {_normalize(key), _normalize(display)}:
            return key
    return ""


def _dataset_families(datasets: dict[str, dict[str, Any]]) -> set[str]:
    return {str(item.get("dataset_family") or "") for item in datasets.values() if isinstance(item, dict)}


def _preferred_dataset_for_family(family: str, datasets: dict[str, dict[str, Any]]) -> str:
    candidates = [(key, item) for key, item in datasets.items() if isinstance(item, dict) and str(item.get("dataset_family") or "") == family]
    if not candidates:
        return ""
    sorted_candidates = sorted(
        candidates,
        key=lambda pair: (
            0 if str(pair[1].get("date_scope") or "").lower() in {"current_day", "today", "daily"} else 1,
            0 if str(pair[0]).endswith("_today") else 1,
            pair[0],
        ),
    )
    return sorted_candidates[0][0]


def _datasets(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = table_catalog.get("datasets") if isinstance(table_catalog.get("datasets"), dict) else {}
    return {str(key): item for key, item in datasets.items() if isinstance(item, dict)}


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = _strip_markdown_fence(text)
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _strip_markdown_fence(text: str) -> str:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _normalize(text: Any) -> str:
    return re.sub(r"[\s\-_/.]+", "", str(text or "").lower())


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"none", "null", "n/a", "na"}:
        return ""
    if text.startswith("<") and text.endswith(">"):
        return ""
    return text


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if isinstance(text, str):
        return text
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    return str(value or "")


# 컴포넌트 설명: 04 Route Classifier Normalizer
# Langflow 표시 설명: 선택적 route LLM 응답을 정규화해 metadata QA, data analysis, report, diagnosis 중 하나로 확정합니다.
class RouteClassifierNormalizer(Component):

    display_name = "04 Route Classifier Normalizer"
    description = "선택적 route LLM 응답을 정규화해 metadata QA, data analysis, report, diagnosis 중 하나로 확정합니다."
    icon = "Route"
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="Route LLM Response", required=False),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 선택적 route LLM 응답을 정규화해 metadata QA, data analysis, report, diagnosis 중 하나로 확정합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:

        result = normalize_route_classifier_payload(getattr(self, "payload", None), getattr(self, "llm_response", ""))
        route = result.get("metadata_route", {}) if isinstance(result, dict) else {}
        self.status = {
            "route": route.get("route"),
            "action": route.get("metadata_action"),
            "route_source": route.get("route_source"),
            "llm_used": route.get("route_llm_used", False),
        }
        return Data(data=result)
