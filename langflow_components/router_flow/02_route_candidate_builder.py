from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


CATALOG_LIST_CUES = [
    "데이터 목록",
    "data list",
    "조회 가능한 data",
    "조회 가능한 데이터",
    "사용 가능한 데이터",
    "사용 가능한 data",
    "등록된 데이터",
    "데이터 리스트",
]
DATASET_QUERY_CUES = ["쿼리", "query", "sql", "조회문"]
DATASET_EXAMPLE_CUES = ["활용 예시", "예시 질문", "질문 예시", "어떤 질문", "무슨 질문", "뭘 물어"]
DATASET_DETAIL_CUES = ["데이터 정보", "dataset 정보", "상세 정보", "컬럼", "필터", "기준일", "source", "소스"]
DOMAIN_SEARCH_CUES = ["관련 등록 정보", "등록된 정보", "등록 정보", "도메인", "정의", "조건", "의미"]
HELP_CUES = ["도움말", "사용법", "뭐 할 수", "무엇을 할 수", "help", "기능"]
GREETING_WORDS = ["안녕", "안녕하세요", "하이", "hello", "hi"]
AMBIGUOUS_DATASET_USAGE_CUES = [
    "뭘 볼",
    "무엇을 볼",
    "볼 수 있",
    "볼수있",
    "어떻게 써",
    "어떻게 사용",
    "쓸 수 있",
    "쓸수있",
    "활용",
    "예시",
]

FAMILY_KEYWORDS = {
    "production": ["생산", "실적", "production"],
    "wip": ["재공", "wip"],
    "target": ["목표", "계획", "target"],
    "lot": ["lot", "롯", "작업대기", "작업중"],
    "hold": ["hold", "홀드"],
    "equipment": ["장비", "설비", "equipment", "eqp"],
    "capacity": ["capacity", "uph", "capa"],
}

ANALYSIS_CUES = [
    "production",
    "wip",
    "target",
    "lot",
    "hold",
    "equipment",
    "eqp",
    "capacity",
    "uph",
    "DA",
    "D/A",
    "WB",
    "W/B",
    "process",
    "rank",
    "top",
    "bottom",
    "count",
    "rate",
    "sum",
    "average",
    "생산",
    "재공",
    "목표",
    "계획",
    "달성률",
    "공정",
    "제품",
    "수량",
    "장비",
    "설비",
    "상위",
    "하위",
    "가장",
]


def route_metadata_question(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "").strip()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    datasets = _datasets(metadata)
    dataset_match = _match_dataset(question, datasets, metadata)

    action = ""
    confidence = "low"
    reason = "질문 유형 분류가 필요합니다. 작은 route classifier가 metadata 질문인지 실제 데이터 분석 질문인지 판단합니다."
    target_term = ""
    route = "data_analysis"
    route_llm_required = True

    if _is_greeting(question):
        route = "direct_answer"
        action = "greeting"
        confidence = "high"
        reason = "인사 또는 짧은 대화형 입력입니다."
        route_llm_required = False

    next_payload = deepcopy(payload)
    next_payload["metadata_route"] = {
        "route": route,
        "metadata_action": action,
        "target_dataset": "",
        "target_family": "",
        "target_term": target_term,
        "candidate_target_dataset": dataset_match.get("target_dataset", ""),
        "candidate_target_family": dataset_match.get("target_family", ""),
        "confidence": confidence,
        "route_confidence": confidence,
        "route_source": "rule",
        "route_llm_required": route_llm_required,
        "route_llm_used": False,
        "question_type_classifier_required": route_llm_required,
        "classifier_mode": "question_type",
        "reason": reason,
        "dataset_matches": dataset_match.get("matches", []),
        "allowed_routes": ["direct_answer", "metadata_qa", "data_analysis", "report_generation", "operations_diagnosis"],
        "allowed_metadata_actions": [
            "greeting",
            "help",
            "catalog_list",
            "dataset_examples",
            "dataset_detail",
            "dataset_query",
            "domain_search",
        ],
    }
    return next_payload


def _match_dataset(question: str, datasets: dict[str, dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    q_lower = question.lower()
    q_norm = _normalize(question)
    matches: list[dict[str, Any]] = []
    for key, item in datasets.items():
        display = str(item.get("display_name") or "")
        candidates = [key, display]
        for candidate in candidates:
            text = str(candidate or "")
            if not text:
                continue
            if text.lower() in q_lower or _normalize(text) in q_norm:
                matches.append({"dataset_key": key, "display_name": display, "match_type": "dataset"})
                break
    target_dataset = matches[0]["dataset_key"] if matches else ""
    target_family = ""

    if not target_dataset:
        quantity_match = _match_quantity_term(question, metadata)
        if quantity_match:
            family = str(quantity_match.get("dataset_family") or "")
            dataset_key = str(quantity_match.get("dataset_key") or "")
            if dataset_key and dataset_key in datasets:
                target_dataset = dataset_key
                target_family = str(datasets[target_dataset].get("dataset_family") or family)
                matches.append(
                    {
                        "dataset_key": target_dataset,
                        "dataset_family": target_family,
                        "quantity_term": quantity_match.get("term_key", ""),
                        "match_type": "quantity_term",
                    }
                )
            elif family:
                preferred = _preferred_dataset_for_family(family, datasets, question)
                if preferred:
                    target_dataset = preferred
                    target_family = str(datasets[target_dataset].get("dataset_family") or family)
                    matches.append(
                        {
                            "dataset_key": target_dataset,
                            "dataset_family": target_family,
                            "quantity_term": quantity_match.get("term_key", ""),
                            "match_type": "quantity_term_family",
                        }
                    )
                else:
                    target_family = family
                    matches.append(
                        {
                            "dataset_family": target_family,
                            "quantity_term": quantity_match.get("term_key", ""),
                            "match_type": "quantity_term_family",
                        }
                    )

    if not target_dataset:
        for family, keywords in FAMILY_KEYWORDS.items():
            if _contains_any(question, keywords):
                target_family = family
                preferred = _preferred_dataset_for_family(family, datasets, question)
                if preferred:
                    target_dataset = preferred
                    target_family = str(datasets[target_dataset].get("dataset_family") or family)
                    matches.append({"dataset_key": target_dataset, "dataset_family": target_family, "match_type": "family"})
                else:
                    matches.append({"dataset_family": family, "match_type": "family"})
                break
    elif isinstance(datasets.get(target_dataset), dict):
        target_family = str(datasets[target_dataset].get("dataset_family") or "")

    return {"target_dataset": target_dataset, "target_family": target_family, "matches": matches[:5]}


def _match_quantity_term(question: str, metadata: dict[str, Any]) -> dict[str, Any]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    quantity_terms = domain.get("quantity_terms") if isinstance(domain.get("quantity_terms"), dict) else {}
    best_match: dict[str, Any] = {}
    best_score = -1
    for term_key, item in quantity_terms.items():
        if not isinstance(item, dict):
            continue
        aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
        candidates = [term_key, item.get("display_name"), *aliases, item.get("output_column"), item.get("quantity_column")]
        flat_candidates = _flatten_candidates(candidates)
        matched_aliases = [alias for alias in flat_candidates if _contains_any(question, [alias])]
        if not matched_aliases:
            continue
        score = max(len(_normalize(alias)) for alias in matched_aliases)
        if score <= best_score:
            continue
        best_score = score
        best_match = {
            "term_key": str(term_key),
            "dataset_key": str(item.get("dataset_key") or ""),
            "dataset_family": str(item.get("dataset_family") or ""),
            "matched_aliases": matched_aliases[:3],
        }
    return best_match


def _preferred_dataset_for_family(family: str, datasets: dict[str, dict[str, Any]], question: str) -> str:
    candidates = [(key, item) for key, item in datasets.items() if isinstance(item, dict) and str(item.get("dataset_family") or "") == family]
    if not candidates:
        return ""
    prefer_history = _contains_any(question, ["이력", "히스토리", "history", "과거", "기간"])
    sorted_candidates = sorted(
        candidates,
        key=lambda pair: (
            _scope_rank(str(pair[1].get("date_scope") or ""), prefer_history),
            0 if str(pair[0]).endswith("_today") else 1,
            pair[0],
        ),
    )
    return sorted_candidates[0][0]


def _scope_rank(date_scope: str, prefer_history: bool) -> int:
    normalized = date_scope.lower()
    if prefer_history:
        return 0 if normalized == "history" else 1
    if normalized in {"current_day", "today", "daily"}:
        return 0
    if normalized == "history":
        return 1
    return 2


def _flatten_candidates(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, list):
            result.extend(_flatten_candidates(value))
        elif value not in (None, "", [], {}):
            result.append(str(value))
    return result


def _extract_domain_term(question: str, dataset_match: dict[str, Any]) -> str:
    text = question
    for match in dataset_match.get("matches", []):
        for key in ("dataset_key", "display_name", "dataset_family"):
            value = str(match.get(key) or "")
            if value:
                text = re.sub(re.escape(value), " ", text, flags=re.IGNORECASE)
    replace_terms = [
        "관련해서",
        "관련된",
        "관련",
        "등록된",
        "등록",
        "정보",
        "알려줘",
        "보여줘",
        "도메인",
        "정의",
        "조건",
        "의미",
        "에 대해",
        "대해",
        "와",
        "과",
        "은",
        "는",
        "이",
        "가",
        "?",
    ]
    for term in replace_terms:
        text = text.replace(term, " ")
    return " ".join(part for part in re.split(r"\s+", text.strip()) if part)[:80]


def _is_greeting(question: str) -> bool:
    cleaned = re.sub(r"[\s!?.,~]+", "", question.strip().lower())
    if not cleaned:
        return False
    return cleaned in {word.lower() for word in GREETING_WORDS} or (
        len(cleaned) <= 8 and any(cleaned.startswith(word.lower()) for word in GREETING_WORDS)
    )


def _contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    normalized = _normalize(text)
    for needle in needles:
        needle_text = str(needle or "")
        if not needle_text:
            continue
        if needle_text.lower() in lower or _normalize(needle_text) in normalized:
            return True
    return False


def _is_clear_analysis_question(question: str, dataset_match: dict[str, Any]) -> bool:
    if dataset_match.get("target_dataset") and _contains_any(question, AMBIGUOUS_DATASET_USAGE_CUES):
        return False
    if _contains_any(question, ANALYSIS_CUES):
        return True
    return bool(
        dataset_match.get("target_family")
        and _contains_any(
            question,
            [
                "show",
                "list",
                "compare",
                "calculate",
                "trend",
                "group",
                "by",
                "보여줘",
                "알려줘",
                "비교",
                "계산",
                "집계",
                "순위",
            ],
        )
    )


def _requires_route_llm(route: str, action: str, confidence: str) -> bool:
    if confidence == "high":
        return False
    if route in {"metadata_qa", "direct_answer"} and action:
        return False
    return True


def _normalize(text: Any) -> str:
    return re.sub(r"[\s\-_/.]+", "", str(text or "").lower())


def _datasets(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = table_catalog.get("datasets") if isinstance(table_catalog.get("datasets"), dict) else {}
    return {str(key): item for key, item in datasets.items() if isinstance(item, dict)}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class RouteCandidateBuilder(Component):
    display_name = "02 Route Candidate Builder"
    description = "Adds metadata-backed route candidates before the small LLM question-type classifier."
    icon = "Route"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = route_metadata_question(getattr(self, "payload", None))
        route = result.get("metadata_route", {})
        self.status = {
            "route": route.get("route"),
            "metadata_action": route.get("metadata_action"),
            "target_dataset": route.get("target_dataset"),
            "confidence": route.get("confidence"),
        }
        return Data(data=result)
