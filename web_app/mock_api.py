from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from reference_runtime.agent import run_agent


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSION_STATE = {"chat_history": [], "context": {}, "current_data": {}}
DEFAULT_REQUEST_DATE = "20260612"
PREVIEW_ROW_LIMIT = 20


class MockApiClient:
    """Python-only stand-in for Langflow Run APIs while API URLs are unavailable."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else PROJECT_ROOT
        self.sessions: dict[str, dict[str, Any]] = {}
        self.result_store: dict[str, list[dict[str, Any]]] = {}
        self.pending_authoring: dict[str, dict[str, Any]] = {}

    def run_query(self, question: str, session_id: str = "demo-session", state: dict[str, Any] | None = None) -> dict[str, Any]:
        text = str(question or "").strip()
        if not text:
            raise ValueError("question is empty")
        session = str(session_id or "demo-session")
        previous_state = deepcopy(state if state is not None else self.sessions.get(session, DEFAULT_SESSION_STATE))
        metadata_qa = self._try_metadata_qa_query(text, session, previous_state)
        if metadata_qa:
            self.sessions[session] = deepcopy(metadata_qa.get("state") or DEFAULT_SESSION_STATE)
            return metadata_qa
        payload = run_agent(text, state=previous_state, session_id=session, root=str(self.root), request_date=DEFAULT_REQUEST_DATE)
        compacted = self._compact_query_payload(payload, session)
        self.sessions[session] = deepcopy(compacted.get("state") or DEFAULT_SESSION_STATE)
        return compacted

    def get_rows(self, data_ref: dict[str, Any] | str) -> list[dict[str, Any]]:
        ref_id = data_ref if isinstance(data_ref, str) else (data_ref or {}).get("ref_id")
        return deepcopy(self.result_store.get(str(ref_id or ""), []))

    def list_metadata(self, metadata_type: str) -> list[dict[str, Any]]:
        kind = _normalize_metadata_type(metadata_type)
        if kind == "domain":
            domain = _load_json(self.root / "metadata" / "domain_items.json")
            rows: list[dict[str, Any]] = []
            for section, values in domain.items():
                if isinstance(values, dict):
                    for key, payload in values.items():
                        rows.append(
                            {
                                "type": "domain",
                                "section": section,
                                "key": key,
                                "status": "active",
                                "display_name": _payload_display_name(payload, key),
                                "aliases": _payload_aliases(payload),
                                "payload": payload,
                            }
                        )
                elif isinstance(values, list):
                    rows.append(
                        {
                            "type": "domain",
                            "section": section,
                            "key": section,
                            "status": "active",
                            "display_name": section,
                            "aliases": [],
                            "payload": {"values": values},
                        }
                    )
            return rows
        if kind == "table_catalog":
            catalog = _load_json(self.root / "metadata" / "table_catalog.json").get("datasets", {})
            return [
                {
                    "type": "table_catalog",
                    "dataset_key": key,
                    "status": "active",
                    "display_name": value.get("display_name", key) if isinstance(value, dict) else key,
                    "dataset_family": value.get("dataset_family", "") if isinstance(value, dict) else "",
                    "source_type": value.get("source_type", "") if isinstance(value, dict) else "",
                    "payload": value,
                }
                for key, value in catalog.items()
            ]
        filters = _load_json(self.root / "metadata" / "main_flow_filters.json")
        return [
            {
                "type": "main_flow_filter",
                "filter_key": key,
                "status": "active",
                "display_name": value.get("description", key) if isinstance(value, dict) else key,
                "column_candidates": value.get("column_candidates", []) if isinstance(value, dict) else [],
                "semantic_role": _guess_semantic_role(key),
                "payload": value,
            }
            for key, value in filters.items()
        ]

    def run_authoring(
        self,
        metadata_type: str,
        raw_text: str,
        duplicate_action: str = "ask",
        session_id: str = "demo-session",
    ) -> dict[str, Any]:
        kind = _normalize_metadata_type(metadata_type)
        action = _normalize_duplicate_action(duplicate_action)
        text = str(raw_text or "").strip()
        items = _build_authoring_items(kind, text)
        missing = _missing_information(kind, text, items)
        existing_matches, conflict_warnings = self._find_existing_matches(kind, items)
        requires_choice = action == "ask" and bool(existing_matches) and not missing

        review = {
            "ready_to_save": bool(items) and not missing and not requires_choice and action != "skip",
            "supplement_requests": missing,
            "review_summary": _review_summary(kind, missing, requires_choice),
        }
        write_result = _write_result_for(action, review, items, existing_matches)
        duplicate_decision = {"action": action, "requires_user_choice": requires_choice}
        response = {
            "status": write_result["status"],
            "message": _authoring_message(kind, write_result, missing, existing_matches, conflict_warnings),
            "metadata_type": kind,
            "items": items,
            "existing_matches": existing_matches,
            "conflict_warnings": conflict_warnings,
            "review": review,
            "write_result": write_result,
            "trace": {
                "raw_text": text,
                "refined_text": _refined_text(kind, text),
                "duplicate_decision": duplicate_decision,
                "api_mode": "python_mock",
            },
            "ui_status": _ui_status(write_result, missing, requires_choice, conflict_warnings),
        }
        if requires_choice:
            pending_id = f"pending-{uuid.uuid4().hex[:10]}"
            self.pending_authoring[pending_id] = {
                "metadata_type": kind,
                "raw_text": text,
                "last_response": deepcopy(response),
                "session_id": session_id,
            }
            response["pending_authoring_id"] = pending_id
        return response

    def validation_questions(self) -> list[dict[str, Any]]:
        return _load_json(self.root / "metadata" / "regression_questions.json")

    def validate_question(
        self,
        question: str,
        expected_datasets: list[str] | None = None,
        session_id: str = "validation-session",
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.run_query(question, session_id=session_id, state=state)
        actual = set((result.get("applied_scope") or {}).get("datasets") or [])
        expected = set(expected_datasets or [])
        passed = expected.issubset(actual) if expected else bool(result.get("answer_message"))
        return {
            "passed": passed,
            "expected_datasets": sorted(expected),
            "actual_datasets": sorted(actual),
            "result": result,
        }

    def _try_metadata_qa_query(self, question: str, session_id: str, previous_state: dict[str, Any]) -> dict[str, Any] | None:
        catalog = _load_json(self.root / "metadata" / "table_catalog.json").get("datasets", {})
        domain = _load_json(self.root / "metadata" / "domain_items.json")
        route = _mock_metadata_route(question, catalog)
        if route["route"] == "data_analysis":
            return None
        data, answer = _mock_metadata_qa_answer(route, catalog, domain)
        metadata_qa = {
            "handled": True,
            "route": route["route"],
            "metadata_action": route["metadata_action"],
            "target_dataset": route.get("target_dataset", ""),
            "target_family": route.get("target_family", ""),
            "target_term": route.get("target_term", ""),
            "confidence": route.get("confidence", "medium"),
            "reason": route.get("reason", ""),
        }
        datasets = _scope_datasets(data)
        applied_scope = {
            "intent_type": "metadata_lookup" if route["route"] == "metadata_qa" else "direct_answer",
            "analysis_kind": route["metadata_action"] or "none",
            "datasets": datasets,
            "source_aliases": [],
            "step_ids": [],
            "filters_by_source": {},
            "params_by_source": {},
            "metadata_refs": {"api_mode": "python_mock"},
        }
        intent_plan = {
            "route": route["route"],
            "intent_type": applied_scope["intent_type"],
            "analysis_kind": applied_scope["analysis_kind"],
            "datasets": datasets,
            "source_aliases": [],
            "metadata_action": route["metadata_action"],
            "target_dataset": route.get("target_dataset", ""),
            "target_family": route.get("target_family", ""),
            "target_term": route.get("target_term", ""),
            "step_plan": [],
            "reasoning_steps": [route.get("reason") or "Python mock metadata QA route"],
        }
        result = {
            "status": "ok",
            "success": True,
            "response_type": "metadata_qa",
            "direct_response_ready": True,
            "answer_message": answer,
            "data": data,
            "applied_scope": applied_scope,
            "intent_plan": intent_plan,
            "metadata_route": route,
            "metadata_qa": metadata_qa,
            "analysis": {
                "status": "ok",
                "analysis_kind": applied_scope["analysis_kind"],
                "columns": data.get("columns", []),
                "rows": data.get("rows", []),
                "row_count": data.get("row_count", 0),
                "reasoning_steps": intent_plan["reasoning_steps"],
                "safety_passed": True,
                "executed": False,
                "errors": [],
            },
            "state": _metadata_qa_state(previous_state, question, answer, metadata_qa),
            "warnings": [],
            "errors": [],
            "api_mode": "python_mock",
            "result_collection_name": "agent_v3_result_store",
        }
        return result

    def _compact_query_payload(self, payload: dict[str, Any], session_id: str) -> dict[str, Any]:
        result = deepcopy(payload)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        rows = list(data.get("rows") or [])
        if rows:
            data_ref = self._store_rows(rows, session_id, "data")
            data["rows"] = rows[:PREVIEW_ROW_LIMIT]
            data["data_ref"] = data_ref
            data["rows_are_preview"] = len(rows) > PREVIEW_ROW_LIMIT
            result["data"] = data
            current_data = ((result.get("state") or {}).get("current_data") or {}) if isinstance(result.get("state"), dict) else {}
            if isinstance(current_data, dict):
                current_data["rows"] = rows[:PREVIEW_ROW_LIMIT]
                current_data["data_ref"] = data_ref
                current_data["rows_are_preview"] = len(rows) > PREVIEW_ROW_LIMIT
                result.setdefault("state", {})["current_data"] = current_data
        result["api_mode"] = "python_mock"
        result["result_collection_name"] = "agent_v3_result_store"
        return result

    def _store_rows(self, rows: list[dict[str, Any]], session_id: str, path: str) -> dict[str, Any]:
        ref_id = f"mock-{uuid.uuid4().hex[:12]}"
        self.result_store[ref_id] = deepcopy(rows)
        return {
            "store": "python_mock",
            "collection_name": "agent_v3_result_store",
            "ref_id": ref_id,
            "session_id": session_id,
            "path": path,
            "row_count": len(rows),
        }

    def _find_existing_matches(self, metadata_type: str, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        existing = self.list_metadata(metadata_type)
        matches: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for item in items:
            new_key = _item_key(metadata_type, item)
            new_aliases = set(_payload_aliases(item.get("payload", {})))
            for old in existing:
                old_key = _item_key(metadata_type, old)
                old_aliases = set(old.get("aliases", []) or _payload_aliases(old.get("payload", {})))
                if new_key and old_key and str(new_key).lower() == str(old_key).lower():
                    matches.append(
                        {
                            "match_type": "same_key",
                            "similarity_level": "high",
                            "new_key": new_key,
                            "existing_key": old_key,
                            "reason": f"같은 key `{old_key}`가 이미 등록되어 있습니다.",
                            "recommended_action": "merge",
                            "existing": old,
                        }
                    )
                elif new_aliases and old_aliases and new_aliases.intersection(old_aliases):
                    warnings.append(
                        {
                            "warning_type": "alias_overlap",
                            "severity": "warning",
                            "new_key": new_key,
                            "existing_key": old_key,
                            "reason": "alias가 일부 겹칩니다. 같은 의미인지 확인하세요.",
                            "existing": old,
                        }
                    )
        return matches[:5], warnings[:5]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_metadata_type(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"domain", "domains"}:
        return "domain"
    if text in {"table", "table_catalog", "catalog", "data_catalog"}:
        return "table_catalog"
    return "main_flow_filter"


def _normalize_duplicate_action(value: str) -> str:
    text = str(value or "ask").strip().lower()
    return text if text in {"ask", "merge", "replace", "skip", "create_new"} else "ask"


CATALOG_LIST_CUES = ("데이터 목록", "data list", "조회 가능한 data", "조회 가능한 데이터", "사용 가능한 데이터", "등록된 데이터")
DATASET_QUERY_CUES = ("쿼리", "query", "sql", "조회문")
DATASET_EXAMPLE_CUES = ("활용 예시", "예시 질문", "질문 예시", "어떤 질문", "무슨 질문", "뭘 물어")
DATASET_DETAIL_CUES = ("데이터 정보", "dataset 정보", "상세 정보", "컬럼", "필터", "기준일", "source", "소스")
DOMAIN_SEARCH_CUES = ("관련 등록 정보", "등록된 정보", "등록 정보", "도메인", "정의", "조건", "의미")
HELP_CUES = ("도움말", "사용법", "뭐 할 수", "무엇을 할 수", "help", "기능")
GREETING_WORDS = ("안녕", "안녕하세요", "하이", "hello", "hi")


def _mock_metadata_route(question: str, catalog: dict[str, Any]) -> dict[str, Any]:
    dataset_match = _match_dataset(question, catalog)
    route = "data_analysis"
    action = ""
    confidence = "medium"
    reason = "일반 데이터 분석 질문으로 판단했습니다."
    target_term = ""
    if _is_greeting(question):
        route, action, confidence, reason = "direct_answer", "greeting", "high", "인사 또는 짧은 대화형 입력입니다."
    elif _contains_any(question, CATALOG_LIST_CUES):
        route, action, confidence, reason = "metadata_qa", "catalog_list", "high", "등록된 데이터 목록을 요청했습니다."
    elif _contains_any(question, DATASET_QUERY_CUES):
        route, action = "metadata_qa", "dataset_query"
        confidence = "high" if dataset_match.get("target_dataset") else "medium"
        reason = "특정 데이터셋의 조회 쿼리/SQL 정보를 요청했습니다."
    elif _contains_any(question, DATASET_EXAMPLE_CUES):
        route, action = "metadata_qa", "dataset_examples"
        confidence = "high" if dataset_match.get("target_dataset") or dataset_match.get("target_family") else "medium"
        reason = "데이터셋별 활용 예시 질문을 요청했습니다."
    elif dataset_match.get("target_dataset") and _contains_any(question, DATASET_DETAIL_CUES):
        route, action, confidence, reason = "metadata_qa", "dataset_detail", "high", "특정 데이터셋의 등록 상세 정보를 요청했습니다."
    elif _contains_any(question, HELP_CUES) and not dataset_match.get("target_dataset"):
        route, action, confidence, reason = "direct_answer", "help", "high", "에이전트 사용법 또는 기능 안내를 요청했습니다."
    elif _contains_any(question, DOMAIN_SEARCH_CUES):
        route, action = "metadata_qa", "domain_search"
        reason = "도메인 메타데이터에서 관련 등록 정보를 찾아야 하는 질문입니다."
        target_term = _extract_domain_term(question, dataset_match)
    elif dataset_match.get("target_dataset") and _contains_any(question, ("정보", "상세")):
        route, action, reason = "metadata_qa", "dataset_detail", "특정 데이터셋 정보 확인 질문으로 판단했습니다."
    return {
        "route": route,
        "metadata_action": action,
        "target_dataset": dataset_match.get("target_dataset", ""),
        "target_family": dataset_match.get("target_family", ""),
        "target_term": target_term,
        "confidence": confidence,
        "reason": reason,
        "dataset_matches": dataset_match.get("matches", []),
    }


def _mock_metadata_qa_answer(route: dict[str, Any], catalog: dict[str, Any], domain: dict[str, Any]) -> tuple[dict[str, Any], str]:
    action = route.get("metadata_action")
    selected = _select_datasets(route, catalog)
    if action == "catalog_list":
        rows = [_catalog_row(key, item) for key, item in sorted(catalog.items()) if isinstance(item, dict)]
        answer = f"현재 등록된 조회 가능 데이터는 {len(rows)}개입니다. 특정 데이터의 활용 예시는 `production_today 활용 예시 알려줘`처럼 물어보면 됩니다."
        return _metadata_table(rows), answer
    if action == "dataset_query":
        if not selected:
            rows = [{"DATASET_KEY": key, "DISPLAY_NAME": item.get("display_name", "")} for key, item in sorted(catalog.items()) if isinstance(item, dict)]
            return _metadata_table(rows), "어떤 데이터셋의 조회 쿼리문이 필요한지 dataset_key를 함께 알려주세요."
        rows = []
        sections = []
        for key, item in selected:
            source_config = item.get("source_config") if isinstance(item.get("source_config"), dict) else {}
            query = str(source_config.get("query_template") or "")
            rows.append({"DATASET_KEY": key, "DB_KEY": source_config.get("db_key", ""), "SOURCE_TYPE": item.get("source_type", ""), "QUERY_TEMPLATE": query})
            sections.append(f"### {key}\n```sql\n{query}\n```")
        return _metadata_table(rows), "\n\n".join(sections)
    if action == "dataset_examples":
        if not selected:
            rows = [{"DATASET_KEY": key, "DISPLAY_NAME": item.get("display_name", "")} for key, item in sorted(catalog.items()) if isinstance(item, dict)]
            return _metadata_table(rows), "어떤 데이터의 활용 예시가 필요한지 dataset_key를 함께 알려주세요."
        rows = []
        for key, item in selected:
            for example in _examples_for_dataset(key, item):
                rows.append({"DATASET_KEY": key, "EXAMPLE_QUESTION": example})
        return _metadata_table(rows), f"{selected[0][0]} 활용 예시는 아래처럼 물어볼 수 있습니다."
    if action == "dataset_detail":
        if not selected:
            rows = [{"DATASET_KEY": key, "DISPLAY_NAME": item.get("display_name", "")} for key, item in sorted(catalog.items()) if isinstance(item, dict)]
            return _metadata_table(rows), "어떤 데이터셋의 상세 정보가 필요한지 dataset_key를 함께 알려주세요."
        rows = [_catalog_row(key, item) for key, item in selected]
        return _metadata_table(rows), f"{selected[0][0]} 등록 정보입니다."
    if action == "domain_search":
        rows = _domain_search_rows(domain, route.get("target_term") or route.get("reason") or "")
        if rows:
            return _metadata_table(rows), f"도메인 metadata에서 {len(rows)}개 관련 정보를 찾았습니다."
        return _metadata_table([]), "관련 domain metadata를 찾지 못했습니다. 다른 표현이나 key로 다시 검색해 주세요."
    rows = [{"QUESTION_TYPE": "metadata", "EXAMPLE": item} for item in ("현재 조회 가능한 DATA LIST 알려줘", "production_today 활용 예시 알려줘", "AUTO향 관련 등록 정보 알려줘")]
    intro = "안녕하세요. 제조 데이터 분석과 등록된 메타데이터 조회를 도와드릴 수 있습니다." if action == "greeting" else "사용 가능한 질문 유형을 안내드릴게요."
    return _metadata_table(rows), intro


def _metadata_qa_state(previous_state: dict[str, Any], question: str, answer: str, metadata_qa: dict[str, Any]) -> dict[str, Any]:
    state = deepcopy(previous_state if isinstance(previous_state, dict) else DEFAULT_SESSION_STATE)
    history = list(state.get("chat_history", [])) if isinstance(state.get("chat_history"), list) else []
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    state["chat_history"] = history[-10:]
    context = deepcopy(state.get("context", {})) if isinstance(state.get("context"), dict) else {}
    context["last_route"] = "metadata_qa"
    context["last_metadata_action"] = metadata_qa.get("metadata_action")
    if metadata_qa.get("target_dataset"):
        context["last_metadata_dataset"] = metadata_qa["target_dataset"]
    if metadata_qa.get("target_term"):
        context["last_metadata_term"] = metadata_qa["target_term"]
    state["context"] = context
    state.setdefault("current_data", {})
    return state


def _match_dataset(question: str, catalog: dict[str, Any]) -> dict[str, Any]:
    q_lower = question.lower()
    q_norm = _normalize_text(question)
    matches: list[dict[str, Any]] = []
    for key, item in catalog.items():
        if not isinstance(item, dict):
            continue
        display = str(item.get("display_name") or "")
        if str(key).lower() in q_lower or _normalize_text(key) in q_norm or (display and (display.lower() in q_lower or _normalize_text(display) in q_norm)):
            matches.append({"dataset_key": key, "display_name": display, "match_type": "dataset"})
    target_dataset = matches[0]["dataset_key"] if matches else ""
    target_family = str((catalog.get(target_dataset) or {}).get("dataset_family") or "") if target_dataset else ""
    if not target_family:
        for family, keywords in {
            "production": ("생산", "실적", "production"),
            "wip": ("재공", "wip"),
            "target": ("목표", "계획", "target"),
            "lot": ("lot", "롯"),
            "equipment": ("장비", "설비", "equipment", "eqp"),
        }.items():
            if _contains_any(question, keywords):
                target_family = family
                matches.append({"dataset_family": family, "match_type": "family"})
                break
    return {"target_dataset": target_dataset, "target_family": target_family, "matches": matches[:5]}


def _select_datasets(route: dict[str, Any], catalog: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    target_dataset = str(route.get("target_dataset") or "")
    target_family = str(route.get("target_family") or "")
    if target_dataset and isinstance(catalog.get(target_dataset), dict):
        return [(target_dataset, catalog[target_dataset])]
    if target_family:
        return [(key, item) for key, item in sorted(catalog.items()) if isinstance(item, dict) and item.get("dataset_family") == target_family]
    return []


def _catalog_row(key: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "DATASET_KEY": key,
        "DISPLAY_NAME": item.get("display_name", ""),
        "DATASET_FAMILY": item.get("dataset_family", ""),
        "SOURCE_TYPE": item.get("source_type", ""),
        "DATE_SCOPE": item.get("date_scope", ""),
        "QUANTITY_COLUMN": item.get("primary_quantity_column", ""),
        "REQUIRED_PARAMS": ", ".join(str(value) for value in item.get("required_params", []) if str(value or "").strip()) if isinstance(item.get("required_params"), list) else "",
    }


def _examples_for_dataset(key: str, item: dict[str, Any]) -> list[str]:
    family = str(item.get("dataset_family") or "")
    quantity = str(item.get("primary_quantity_column") or "수량")
    if family == "production":
        return [f"오늘 DA공정 {quantity}을 제품별로 보여줘", f"{key}에서 생산 상위 5개 제품 알려줘", f"WB공정 {key} 실적을 보여줘"]
    if family == "wip":
        return [f"현재 DA에서 재공이 가장 많은 제품 알려줘", f"{key} 재공 상위 10개 알려줘", f"WB공정 재공을 제품별로 보여줘"]
    return [f"{key} 데이터로 주요 현황 보여줘", f"{key} 상세 정보 알려줘", f"{key} 활용 예시 알려줘"]


def _domain_search_rows(domain: dict[str, Any], term: str) -> list[dict[str, Any]]:
    needle = _normalize_text(term)
    rows: list[dict[str, Any]] = []
    for section, values in domain.items():
        if not isinstance(values, dict):
            continue
        for key, payload in values.items():
            haystack = _normalize_text(json.dumps({"section": section, "key": key, "payload": payload}, ensure_ascii=False, default=str))
            if needle and needle not in haystack and not any(_normalize_text(alias) in haystack for alias in str(term).split()):
                continue
            rows.append(
                {
                    "SECTION": section,
                    "KEY": key,
                    "DISPLAY_NAME": _payload_display_name(payload, key),
                    "ALIASES": ", ".join(_payload_aliases(payload)[:6]),
                    "PAYLOAD": json.dumps(payload, ensure_ascii=False, default=str),
                }
            )
    return rows[:20]


def _metadata_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned_rows = [{str(key): _compact_metadata_value(value) for key, value in row.items()} for row in rows]
    columns: list[str] = []
    for row in cleaned_rows:
        for key in row:
            if key not in columns:
                columns.append(str(key))
    return {"columns": columns, "rows": cleaned_rows, "row_count": len(cleaned_rows), "data_ref": {}}


def _compact_metadata_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _scope_datasets(data: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for row in data.get("rows", []) if isinstance(data.get("rows"), list) else []:
        key = row.get("DATASET_KEY") if isinstance(row, dict) else None
        if key and str(key) not in result:
            result.append(str(key))
    return result


def _extract_domain_term(question: str, dataset_match: dict[str, Any]) -> str:
    text = question
    for match in dataset_match.get("matches", []):
        for key in ("dataset_key", "display_name", "dataset_family"):
            value = str(match.get(key) or "")
            if value:
                text = re.sub(re.escape(value), " ", text, flags=re.IGNORECASE)
    for term in ("관련해서", "관련된", "관련", "등록된", "등록", "정보", "알려줘", "보여줘", "도메인", "정의", "조건", "의미", "에 대해", "대해", "와", "과", "은", "는", "이", "가", "?"):
        text = text.replace(term, " ")
    return " ".join(part for part in re.split(r"\s+", text.strip()) if part)[:80]


def _is_greeting(question: str) -> bool:
    cleaned = re.sub(r"[\s!?.,~]+", "", question.strip().lower())
    return bool(cleaned) and (cleaned in GREETING_WORDS or (len(cleaned) <= 8 and any(cleaned.startswith(word) for word in GREETING_WORDS)))


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lower = text.lower()
    normalized = _normalize_text(text)
    return any(str(needle).lower() in lower or _normalize_text(needle) in normalized for needle in needles if str(needle or "").strip())


def _normalize_text(text: Any) -> str:
    return re.sub(r"[\s\-_/.]+", "", str(text or "").lower())


def _build_authoring_items(metadata_type: str, text: str) -> list[dict[str, Any]]:
    upper = text.upper()
    if metadata_type == "domain":
        if "COUNT_DISTINCT" in upper or "LOT" in upper:
            return [
                {
                    "section": "quantity_terms",
                    "key": "lot_count",
                    "status": "active",
                    "payload": {
                        "aliases": ["Lot 수량", "LOT 수량", "lot count"],
                        "dataset_key": "lot_status",
                        "quantity_column": "LOT_ID",
                        "aggregation": "nunique",
                        "output_column": "LOT_COUNT",
                    },
                }
            ]
        key = "WB" if "W/B" in upper or "WB" in upper else "DA"
        processes = [f"{'W/B' if key == 'WB' else 'D/A'}{index}" for index in range(1, 7)]
        return [
            {
                "section": "process_groups",
                "key": key,
                "status": "active",
                "payload": {
                    "display_name": "W/B" if key == "WB" else "D/A",
                    "aliases": [key, "W/B" if key == "WB" else "D/A"],
                    "processes": processes,
                },
            }
        ]
    if metadata_type == "table_catalog":
        dataset_key = "wip_today" if "WIP" in upper or "재공" in text else "production_today"
        quantity = "WIP" if dataset_key == "wip_today" else "PRODUCTION"
        query_template = _extract_query_template(text) or f"SELECT WORK_DT, OPER_NAME, {quantity} FROM MOCK_{dataset_key.upper()} WHERE WORK_DT = {{DATE}}"
        return [
            {
                "dataset_key": dataset_key,
                "status": "active",
                "payload": {
                    "display_name": "WIP Today" if dataset_key == "wip_today" else "Production Today",
                    "dataset_family": "wip" if dataset_key == "wip_today" else "production",
                    "date_scope": "current_day",
                    "source_type": "oracle",
                    "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": query_template},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["WORK_DT"]},
                    "filter_mappings": {"DATE": ["WORK_DT"], "OPER_NAME": ["OPER_NAME"]},
                    "columns": ["WORK_DT", "OPER_NAME", quantity],
                    "primary_quantity_column": quantity,
                },
            }
        ]
    key = "DATE" if any(token in text for token in ("날짜", "기준일", "오늘", "금일", "DATE")) else "OPER_NAME"
    return [
        {
            "filter_key": key,
            "status": "active",
            "payload": {
                "display_name": "기준일" if key == "DATE" else "공정명",
                "aliases": ["오늘", "금일", "작업일"] if key == "DATE" else ["공정", "작업공정", "operation"],
                "column_candidates": ["WORK_DT", "DATE", "BASE_DT"] if key == "DATE" else ["OPER_NAME", "OPER_SHORT_DESC"],
                "semantic_role": "date" if key == "DATE" else "process_name",
                "value_type": "date" if key == "DATE" else "string",
                "value_shape": "scalar",
                "operator": "eq",
            },
        }
    ]


def _missing_information(metadata_type: str, text: str, items: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not text:
        return [{"field": "raw_text", "reason": "등록할 자연어 설명이 비어 있습니다.", "example_user_input": "DA는 D/A1부터 D/A6까지입니다."}]
    if not items:
        return [{"field": "items", "reason": "생성 가능한 metadata item을 찾지 못했습니다.", "example_user_input": "등록할 key와 의미를 설명해 주세요."}]
    if metadata_type == "table_catalog" and "SELECT" not in text.upper() and "DOC_ID" not in text.upper() and "API_URL" not in text.upper():
        return [
            {
                "field": "source_config.query_template",
                "reason": "운영 dataset 등록에는 source 조회 정보가 필요합니다.",
                "example_user_input": "wip_today는 SELECT ... WHERE WORK_DT = {DATE}로 조회합니다.",
            }
        ]
    return []


def _write_result_for(action: str, review: dict[str, Any], items: list[dict[str, Any]], matches: list[dict[str, Any]]) -> dict[str, Any]:
    base = {"status": "skipped", "saved_count": 0, "saved_items": [], "errors": [], "skipped_reason": ""}
    if action == "skip":
        base["skipped_reason"] = "사용자가 저장하지 않음을 선택했습니다."
        return base
    if matches and action == "ask":
        base["skipped_reason"] = "비슷한 기존 정보가 있어 merge/replace/skip/create_new 중 선택이 필요합니다."
        return base
    if not review.get("ready_to_save") and action not in {"merge", "replace", "create_new"}:
        base["skipped_reason"] = "검증 결과 저장할 수 없는 상태입니다."
        return base
    if review.get("supplement_requests"):
        base["skipped_reason"] = "필수 정보가 부족해 저장하지 않았습니다."
        return base
    return {
        "status": "ok",
        "saved_count": len(items),
        "saved_items": [_saved_item_summary(item) for item in items],
        "errors": [],
        "skipped_reason": "",
        "operation": action if action != "ask" else "insert",
    }


def _authoring_message(
    metadata_type: str,
    write_result: dict[str, Any],
    missing: list[dict[str, str]],
    matches: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> str:
    label = {"domain": "Domain", "table_catalog": "Table catalog", "main_flow_filter": "Main flow filter"}[metadata_type]
    if write_result.get("status") == "ok":
        return f"{label} metadata {write_result.get('saved_count', 0)}건을 mock 저장했습니다."
    if missing:
        return "아직 저장하지 않았습니다. 부족한 정보를 보완해 주세요."
    if matches:
        return "비슷한 기존 정보가 있어 처리 방식을 선택해야 합니다."
    if warnings:
        return "저장 전 확인할 경고가 있습니다."
    return write_result.get("skipped_reason") or "저장하지 않았습니다."


def _ui_status(write_result: dict[str, Any], missing: list[Any], requires_choice: bool, warnings: list[Any]) -> str:
    if write_result.get("status") == "ok" and warnings:
        return "warning"
    if write_result.get("status") == "ok":
        return "saved"
    if requires_choice:
        return "duplicate_choice_required"
    if missing:
        return "needs_more_input"
    if write_result.get("status") == "error":
        return "error"
    return "skipped"


def _refined_text(metadata_type: str, text: str) -> str:
    return f"[{metadata_type}] {text.strip()}" if text.strip() else ""


def _review_summary(metadata_type: str, missing: list[Any], requires_choice: bool) -> str:
    if missing:
        return "필수 정보가 부족합니다."
    if requires_choice:
        return "기존 metadata와 같은 key가 있어 사용자 선택이 필요합니다."
    return f"{metadata_type} item을 저장할 수 있는 mock 검토 상태입니다."


def _extract_query_template(text: str) -> str:
    marker = "SELECT "
    upper = text.upper()
    index = upper.find(marker)
    if index < 0:
        return ""
    return text[index:].strip()


def _item_key(metadata_type: str, item: dict[str, Any]) -> str:
    if metadata_type == "domain":
        return f"{item.get('section')}/{item.get('key')}"
    if metadata_type == "table_catalog":
        return str(item.get("dataset_key") or "")
    return str(item.get("filter_key") or "")


def _payload_display_name(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        return str(payload.get("display_name") or fallback)
    return str(fallback)


def _payload_aliases(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    aliases = payload.get("aliases")
    return [str(item) for item in aliases] if isinstance(aliases, list) else []


def _saved_item_summary(item: dict[str, Any]) -> dict[str, Any]:
    result = {key: item.get(key) for key in ("section", "key", "dataset_key", "filter_key") if item.get(key)}
    result["_id"] = ":".join(str(value) for value in result.values())
    return result


def _guess_semantic_role(key: str) -> str:
    if key == "DATE":
        return "date"
    if key == "OPER_NAME":
        return "process_name"
    if key.startswith("LOT"):
        return "lot"
    if key.startswith("EQP"):
        return "equipment"
    return "product_attribute"
