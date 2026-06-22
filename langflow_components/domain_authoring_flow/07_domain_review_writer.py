# 파일 설명: 07 Domain Review Writer Langflow custom component 파일입니다.
# 흐름 역할: 최종 review JSON을 정규화하고 승인된 domain metadata를 MongoDB에 upsert합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


DEFAULT_COLLECTION_NAME = "agent_v3_domain_items"
COLLECTION_ENV_KEY = "MONGODB_DOMAIN_COLLECTION"
LEGACY_COLLECTION_SUFFIX = "domain_items"


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 최종 review JSON을 정규화하고 승인된 domain metadata를 MongoDB에 upsert합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def review_and_write_domain_payload(
    payload_value: Any,
    llm_response_value: Any,
    mongo_uri: str = "",
    mongo_database: str = "",
    collection_prefix: str = "",
    collection_name: str = "",
) -> dict[str, Any]:
    payload = _payload(payload_value)
    action = _action((payload.get("duplicate_decision") or {}).get("action") or "ask")
    review = _normalize_review(_text(llm_response_value), payload, action)
    config = payload.get("mongo_config") if isinstance(payload.get("mongo_config"), dict) else {}
    database = _clean(mongo_database or config.get("database") or os.getenv("MONGODB_DATABASE") or "metadata_driven_agent_v3")
    collection = _resolve_collection_name(collection_name or config.get("collection"), collection_prefix or config.get("collection_prefix"))
    uri = _clean(mongo_uri or os.getenv("MONGODB_URI"))

    write_result = {"status": "skipped", "saved_count": 0, "saved_items": [], "errors": [], "skipped_reason": ""}
    if action == "skip":
        write_result["skipped_reason"] = "사용자가 duplicate_action=skip을 선택했습니다."
    elif (payload.get("duplicate_decision") or {}).get("requires_user_choice") and action == "ask":
        write_result["skipped_reason"] = "비슷한 기존 정보가 있어 merge/replace/skip/create_new 중 선택이 필요합니다."
    elif not review.get("ready_to_save"):
        write_result["skipped_reason"] = "검증 결과 저장할 수 없는 상태입니다."
    elif not uri:
        write_result["status"] = "error"
        write_result["errors"].append("mongo_uri가 비어 있어 MongoDB에 저장하지 못했습니다.")
    else:
        write_result = _write_items(uri, database, collection, payload.get("items", []), action)

    next_payload = dict(payload)
    next_payload["duplicate_decision"] = _resolved_duplicate_decision(payload, action)
    next_payload["review"] = review
    next_payload["write_result"] = write_result
    next_payload.setdefault("trace", {})["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    return next_payload


def _normalize_review(text: str, payload: dict[str, Any], action: str = "ask") -> dict[str, Any]:
    parsed = _extract_json_object(text)
    duplicate_action_chosen = action in {"merge", "replace", "skip", "create_new"}
    duplicate_waiting_for_user = _duplicate_choice_required(payload) and action == "ask"
    supplement = []
    duplicate_supplement_count = 0
    for item in _as_list(parsed.get("supplement_requests")):
        if not duplicate_waiting_for_user and _is_duplicate_action_request(item):
            duplicate_supplement_count += 1
            continue
        if _is_resolved_metric_supplement_request(item, payload):
            continue
        supplement.append(item)
    if duplicate_waiting_for_user:
        supplement.append(
            {
                "field": "duplicate_action",
                "reason": "같은 key의 기존 domain 정보가 있어 저장 방식을 선택해야 합니다.",
                "example_user_input": "merge, replace, skip, create_new 중 하나를 선택해 주세요.",
            }
        )
    if not payload.get("items"):
        supplement.append({"field": "items", "reason": "저장할 domain item이 없습니다.", "example_user_input": "추가할 용어와 의미를 설명해 주세요."})
    errors = list(payload.get("errors", []))
    only_duplicate_blockers = duplicate_action_chosen and duplicate_supplement_count > 0 and not supplement
    blockers_clear = not supplement and not errors
    review_ready = bool(parsed.get("ready_to_save", False))
    ready = blockers_clear and (review_ready or only_duplicate_blockers or not _duplicate_choice_required(payload))
    return {
        "ready_to_save": ready,
        "summary": _clean(parsed.get("summary") or "검증 결과를 정리했습니다."),
        "supplement_requests": supplement,
        "item_reviews": _normalize_item_reviews(_as_list(parsed.get("item_reviews")), ready),
        "normalizer_errors": errors,
    }


def _write_items(mongo_uri: str, database: str, collection: str, items: list[Any], action: str) -> dict[str, Any]:
    result = {"status": "ok", "saved_count": 0, "saved_items": [], "errors": [], "skipped_reason": ""}
    client = None
    try:
        mongo_client_cls = getattr(import_module("pymongo"), "MongoClient")
        client = mongo_client_cls(mongo_uri, serverSelectionTimeoutMS=5000)
        coll = client[database][collection]
        for item in items:
            if not isinstance(item, dict):
                continue
            section = _clean(item.get("section"))
            key = _clean(item.get("key"))
            query = {"section": section, "key": key}
            existing = coll.find_one(query)
            if existing and action == "create_new":
                result["errors"].append(f"{section}/{key}는 이미 존재합니다. create_new를 쓰려면 새 key가 필요합니다.")
                continue
            doc = _domain_doc(item)
            if existing and action == "merge":
                doc = _deep_merge(_json_ready(existing), doc)
                doc["_id"] = existing.get("_id", doc["_id"])
            doc = _strip_storage_envelope(doc)
            coll.replace_one({"_id": doc["_id"]}, doc, upsert=True)
            result["saved_count"] += 1
            result["saved_items"].append({"section": section, "key": key, "_id": doc["_id"]})
    except Exception as exc:
        result["status"] = "error"
        result["errors"].append(str(exc))
    finally:
        if client is not None:
            client.close()
    if result["errors"] and result["saved_count"] == 0:
        result["status"] = "error"
    return result


def _domain_doc(item: dict[str, Any]) -> dict[str, Any]:
    section = _clean(item.get("section"))
    key = _clean(item.get("key"))
    payload = deepcopy(item.get("payload")) if isinstance(item.get("payload"), dict) else {}
    doc = {
        "_id": f"domain:{section}:{key}",
        "section": section,
        "key": key,
        "status": _clean(item.get("status") or "active"),
        "payload": payload,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if item.get("columns"):
        doc["columns"] = _as_text_list(item.get("columns"))
    return doc


def _strip_storage_envelope(doc: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(doc)
    for key in (
        "schema_version",
        "agent_version",
        "metadata_type",
        "namespace",
        "identity",
        "source",
        "_source_file",
        "_source_name",
        "payload_hash",
    ):
        cleaned.pop(key, None)
    return cleaned


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if key == "_id":
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = _dedupe(merged[key] + value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _dedupe(values: list[Any]) -> list[Any]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


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


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return str(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _as_text_list(value: Any) -> list[str]:
    return [_clean(item) for item in _as_list(value) if _clean(item)]


def _action(value: Any) -> str:
    action = _clean(value).lower()
    return action if action in {"ask", "merge", "replace", "skip", "create_new"} else "ask"


def _duplicate_choice_required(payload: dict[str, Any]) -> bool:
    return bool((payload.get("duplicate_decision") or {}).get("requires_user_choice"))


def _is_duplicate_action_request(item: Any) -> bool:
    if isinstance(item, dict):
        field = _clean(item.get("field")).lower()
        if field == "duplicate_action" or field.startswith("duplicate_decision"):
            return True
        text = " ".join(_clean(item.get(key)) for key in ("reason", "example_user_input"))
    else:
        text = _clean(item)
    lowered = text.lower()
    return "duplicate_action" in lowered or "merge" in lowered and "replace" in lowered and "skip" in lowered


def _is_resolved_metric_supplement_request(item: Any, payload: dict[str, Any]) -> bool:
    field = _supplement_field(item)
    if not field:
        return False
    field_lower = field.lower()
    if field_lower not in {"dataset_key", "dataset_family"} and "output_column" not in field_lower:
        return False
    for domain_item in _as_list(payload.get("items")):
        if not isinstance(domain_item, dict) or _clean(domain_item.get("section")) != "metric_terms":
            continue
        metric_payload = domain_item.get("payload") if isinstance(domain_item.get("payload"), dict) else {}
        if field_lower == "dataset_key" and _metric_has_dataset_scope(metric_payload):
            return True
        if field_lower == "dataset_family" and _metric_has_dataset_family(metric_payload):
            return True
        if "output_column" in field_lower and _metric_has_output_column(metric_payload, field):
            return True
    return False


def _metric_has_dataset_scope(payload: dict[str, Any]) -> bool:
    return bool(
        _clean(payload.get("dataset_key"))
        or _clean(payload.get("dataset_family"))
        or _as_text_list(payload.get("required_dataset_families"))
        or _as_text_list(payload.get("required_quantity_terms"))
    )


def _metric_has_dataset_family(payload: dict[str, Any]) -> bool:
    return bool(_clean(payload.get("dataset_family")) or _as_text_list(payload.get("required_dataset_families")))


def _metric_has_output_column(payload: dict[str, Any], field: str) -> bool:
    outputs = set(_as_text_list(payload.get("output_columns")))
    if _clean(payload.get("output_column")):
        outputs.add(_clean(payload.get("output_column")))
    if not outputs:
        return False
    field_upper = field.upper()
    if any(output.upper() in field_upper for output in outputs):
        return True
    return len(outputs) == 1 and field.lower() in {"output_column", "output_column_name"}


def _supplement_field(item: Any) -> str:
    if isinstance(item, dict):
        return _clean(item.get("field"))
    text = _clean(item)
    if ":" in text:
        return _clean(text.split(":", 1)[0])
    return ""


def _normalize_item_reviews(item_reviews: list[Any], ready_to_save: bool) -> list[Any]:
    if not ready_to_save:
        return item_reviews
    normalized = []
    for item in item_reviews:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        next_item = dict(item)
        next_item["decision"] = "pass"
        if _clean(item.get("decision")) != "pass":
            next_item["reason"] = "저장 차단 요인이 없어 저장 가능한 상태로 처리했습니다."
        normalized.append(next_item)
    return normalized


def _resolved_duplicate_decision(payload: dict[str, Any], action: str) -> dict[str, Any]:
    decision = deepcopy(payload.get("duplicate_decision")) if isinstance(payload.get("duplicate_decision"), dict) else {}
    decision["action"] = action
    if action in {"merge", "replace", "skip", "create_new"}:
        decision["requires_user_choice"] = False
        decision["message"] = ""
    return decision


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


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _resolve_collection_name(collection_name: Any = "", collection_prefix: Any = "") -> str:
    collection = _clean(collection_name or os.getenv(COLLECTION_ENV_KEY))
    if collection:
        return collection
    legacy_prefix = _clean(collection_prefix or os.getenv("MONGODB_COLLECTION_PREFIX"))
    if legacy_prefix:
        return f"{legacy_prefix}_{LEGACY_COLLECTION_SUFFIX}"
    return DEFAULT_COLLECTION_NAME


# 컴포넌트 설명: 07 Domain Review Writer
# Langflow 표시 설명: 최종 review JSON을 정규화하고 승인된 domain metadata를 MongoDB에 upsert합니다.
class DomainReviewWriter(Component):

    display_name = "07 Domain Review Writer"
    description = "최종 review JSON을 정규화하고 승인된 domain metadata를 MongoDB에 upsert합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="Review LLM Response", required=True),
        MessageTextInput(name="mongo_uri", display_name="Mongo URI", value="", advanced=True),
        MessageTextInput(name="mongo_database", display_name="Mongo Database", value="", advanced=True),
        MessageTextInput(name="collection_name", display_name="Collection Name", value="", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]


    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 최종 review JSON을 정규화하고 승인된 domain metadata를 MongoDB에 upsert합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = review_and_write_domain_payload(
            getattr(self, "payload", None),
            getattr(self, "llm_response", ""),
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            "",
            getattr(self, "collection_name", ""),
        )
        self.status = {
            "ready": (result.get("review") or {}).get("ready_to_save", False),
            "write_status": (result.get("write_result") or {}).get("status"),
            "saved": (result.get("write_result") or {}).get("saved_count", 0),
        }
        return Data(data=result)
