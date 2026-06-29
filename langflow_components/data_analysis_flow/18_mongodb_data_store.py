# 파일 설명: 18 MongoDB Data Store Langflow custom component 파일입니다.
# 흐름 역할: 큰 결과 row list를 MongoDB result collection에 저장하고 payload에는 compact data_ref만 남깁니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, MessageTextInput, Output
from lfx.schema.data import Data


DEFAULT_RESULT_COLLECTION = "agent_v3_result_store"
ENABLED_OPTIONS = ["true", "false"]
SOURCE_METADATA_KEYS = (
    "dataset_key",
    "dataset_label",
    "source_alias",
    "source_type",
    "job_id",
    "purpose",
    "applied_params",
    "applied_filters",
)


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 큰 결과 row list를 MongoDB result collection에 저장하고 payload에는 compact data_ref만 남깁니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def store_payload_in_mongodb(
    payload_value: Any,
    mongo_uri: Any = "",
    mongo_database: Any = "",
    result_collection_name: Any = "",
    enabled: Any = "true",
    preview_row_limit: Any = "5",
    min_rows: Any = "1",
) -> dict[str, Any]:
    payload = _payload(payload_value)
    if not payload:
        return {"mongo_data_store": {"enabled": False, "stored": False, "ref_count": 0, "errors": ["empty payload"]}}
    if payload.get("direct_response_ready"):
        return {**payload, "mongo_data_store": {"enabled": False, "stored": False, "ref_count": 0, "errors": [], "reason": "direct_response_ready"}}

    if not _truthy(enabled):
        return {**payload, "mongo_data_store": {"enabled": False, "stored": False, "ref_count": 0, "errors": []}}

    preview_limit = _positive_int(preview_row_limit, default=5, minimum=0)
    min_row_count = _positive_int(min_rows, default=1, minimum=1)
    uri = _clean(mongo_uri) or os.getenv("MONGODB_URI", "")
    database = _clean(mongo_database) or os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v3")
    collection_name = _clean(result_collection_name) or os.getenv("MONGODB_RESULT_COLLECTION", DEFAULT_RESULT_COLLECTION)
    missing = []
    if not uri:
        missing.append("Mongo URI is empty.")
    if not database:
        missing.append("Mongo database is empty.")
    if not collection_name:
        missing.append("Mongo result collection name is empty.")
    if missing:
        return {**payload, "mongo_data_store": {"enabled": True, "stored": False, "ref_count": 0, "errors": missing}}

    client = None
    refs: list[dict[str, Any]] = []
    try:
        client, collection = _connect_collection(uri, database, collection_name)
        session_id = _find_session_id(payload) or "default"
        compacted = _compact_with_refs(
            payload,
            collection=collection,
            session_id=session_id,
            database=database,
            collection_name=collection_name,
            preview_limit=preview_limit,
            min_rows=min_row_count,
            path="",
            refs=refs,
        )
        compacted["data_refs"] = refs
        compacted["mongo_data_store"] = {
            "enabled": True,
            "stored": bool(refs),
            "ref_count": len(refs),
            "result_collection_name": collection_name,
            "errors": [],
        }
        return compacted
    except Exception as exc:
        return {**payload, "mongo_data_store": {"enabled": True, "stored": False, "ref_count": 0, "errors": [str(exc)]}}
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _compact_with_refs(
    value: Any,
    collection: Any,
    session_id: str,
    database: str,
    collection_name: str,
    preview_limit: int,
    min_rows: int,
    path: str,
    refs: list[dict[str, Any]],
) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        runtime_ref_map: dict[str, dict[str, Any]] = {}
        source_results = value.get("source_results") if isinstance(value.get("source_results"), list) else []
        source_by_alias = _source_results_by_alias(source_results)

        for key, item in value.items():
            current_path = f"{path}.{key}" if path else key
            if key == "data_ref" and result.get("data_is_reference") and isinstance(result.get("data_ref"), dict):
                continue
            if key == "runtime_sources" and isinstance(item, dict):
                compact_sources, runtime_ref_map = _compact_runtime_sources(
                    item,
                    source_by_alias=source_by_alias,
                    collection=collection,
                    session_id=session_id,
                    database=database,
                    collection_name=collection_name,
                    preview_limit=preview_limit,
                    min_rows=min_rows,
                    path=current_path,
                    refs=refs,
                )
                result[key] = compact_sources
                if runtime_ref_map:
                    existing_refs = value.get("runtime_source_refs") if isinstance(value.get("runtime_source_refs"), dict) else {}
                    result["runtime_source_refs"] = {**deepcopy(existing_refs), **runtime_ref_map}
                    result["runtime_sources_are_preview"] = True
                continue

            if key in {"data", "rows"} and _is_row_list(item):
                existing_ref = value.get("data_ref") if isinstance(value.get("data_ref"), dict) else {}
                if existing_ref.get("store") == "mongodb":
                    result[key] = _preview_rows(item, preview_limit)
                    result.setdefault("data_ref", deepcopy(existing_ref))
                    result["row_count"] = int(existing_ref.get("row_count") or len(item))
                    result["columns"] = list(existing_ref.get("columns") or _rows_columns(item))
                    result["data_is_reference"] = True
                    result["data_is_preview"] = len(item) > preview_limit
                    continue
                if len(item) >= min_rows:
                    data_ref = _store_rows(
                        collection=collection,
                        rows=item,
                        session_id=session_id,
                        path=current_path,
                        database=database,
                        collection_name=collection_name,
                        metadata=_source_ref_metadata(value),
                    )
                    refs.append(data_ref)
                    result[key] = _preview_rows(item, preview_limit)
                    result["data_ref"] = data_ref
                    result["row_count"] = len(item)
                    result["columns"] = _rows_columns(item)
                    result["data_is_reference"] = True
                    result["data_is_preview"] = len(item) > preview_limit
                    continue

            result[key] = _compact_with_refs(
                item,
                collection=collection,
                session_id=session_id,
                database=database,
                collection_name=collection_name,
                preview_limit=preview_limit,
                min_rows=min_rows,
                path=current_path,
                refs=refs,
            )

        if runtime_ref_map:
            result["source_results"] = _apply_runtime_refs_to_source_results(result.get("source_results", []), runtime_ref_map)
        return result
    if isinstance(value, list):
        return [
            _compact_with_refs(
                item,
                collection=collection,
                session_id=session_id,
                database=database,
                collection_name=collection_name,
                preview_limit=preview_limit,
                min_rows=min_rows,
                path=f"{path}[{index}]",
                refs=refs,
            )
            for index, item in enumerate(value)
        ]
    return deepcopy(value)


def _compact_runtime_sources(
    runtime_sources: dict[str, Any],
    source_by_alias: dict[str, dict[str, Any]],
    collection: Any,
    session_id: str,
    database: str,
    collection_name: str,
    preview_limit: int,
    min_rows: int,
    path: str,
    refs: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    compact_sources: dict[str, Any] = {}
    ref_map: dict[str, dict[str, Any]] = {}
    for alias, rows in runtime_sources.items():
        alias_text = str(alias)
        current_path = f"{path}.{alias_text}" if path else alias_text
        if not _is_row_list(rows) or len(rows) < min_rows:
            compact_sources[alias_text] = deepcopy(rows)
            continue
        metadata = _source_ref_metadata(source_by_alias.get(alias_text, {"source_alias": alias_text}))
        metadata.setdefault("source_alias", alias_text)
        data_ref = _store_rows(
            collection=collection,
            rows=rows,
            session_id=session_id,
            path=current_path,
            database=database,
            collection_name=collection_name,
            metadata=metadata,
        )
        refs.append(data_ref)
        ref_map[alias_text] = data_ref
        compact_sources[alias_text] = _preview_rows(rows, preview_limit)
    return compact_sources, ref_map


def _apply_runtime_refs_to_source_results(source_results: Any, ref_map: dict[str, dict[str, Any]]) -> list[Any]:
    if not isinstance(source_results, list):
        return []
    compact_results = []
    for item in source_results:
        if not isinstance(item, dict):
            compact_results.append(deepcopy(item))
            continue
        result = deepcopy(item)
        alias = str(result.get("source_alias") or result.get("dataset_key") or "")
        data_ref = ref_map.get(alias)
        if data_ref:
            result["data_ref"] = deepcopy(data_ref)
            result["row_count"] = data_ref.get("row_count", result.get("row_count"))
            result["columns"] = deepcopy(data_ref.get("columns", result.get("columns", [])))
            result["data_is_reference"] = True
            result["data_is_preview"] = True
        compact_results.append(result)
    return compact_results


def _store_rows(
    collection: Any,
    rows: list[dict[str, Any]],
    session_id: str,
    path: str,
    database: str,
    collection_name: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ref_id = uuid.uuid4().hex
    columns = _rows_columns(rows)
    safe_metadata = _json_ready(metadata or {})
    doc = {
        "ref_id": ref_id,
        "session_id": session_id or "default",
        "path": path,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "columns": columns,
        "rows": _json_ready(rows),
        "metadata": safe_metadata,
    }
    if isinstance(safe_metadata, dict):
        doc.update(safe_metadata)
    collection.replace_one({"ref_id": ref_id}, doc, upsert=True)
    data_ref = {
        "store": "mongodb",
        "ref_id": ref_id,
        "database": database,
        "db_name": database,
        "collection_name": collection_name,
        "row_count": len(rows),
        "columns": columns,
        "path": path,
    }
    if isinstance(safe_metadata, dict):
        data_ref.update(safe_metadata)
    return data_ref


def _connect_collection(mongo_uri: str, database: str, collection_name: str) -> tuple[Any, Any]:
    mongo_client_cls = getattr(import_module("pymongo"), "MongoClient")
    client = mongo_client_cls(mongo_uri, serverSelectionTimeoutMS=5000)
    return client, client[database][collection_name]


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return deepcopy(data)
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
        except Exception:
            return {"text": text}
        return parsed if isinstance(parsed, dict) else {"text": text}
    return {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() not in {"", "0", "false", "no", "off", "none", "null"}


def _positive_int(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, parsed)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _json_ready(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _is_row_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(row, dict) for row in value)


def _preview_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return deepcopy(rows[:limit]) if limit > 0 else []


def _rows_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _source_ref_metadata(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    metadata: dict[str, Any] = {}
    for key in SOURCE_METADATA_KEYS:
        value = source.get(key)
        if value not in (None, "", [], {}):
            metadata[key] = deepcopy(value)
    return metadata


def _source_results_by_alias(source_results: list[Any]) -> dict[str, dict[str, Any]]:
    by_alias: dict[str, dict[str, Any]] = {}
    for item in source_results:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("source_alias") or item.get("dataset_key") or "")
        if alias:
            by_alias[alias] = item
    return by_alias


def _find_session_id(value: Any) -> str:
    if isinstance(value, dict):
        request = value.get("request") if isinstance(value.get("request"), dict) else {}
        if request.get("session_id"):
            return str(request["session_id"])
        if value.get("session_id"):
            return str(value["session_id"])
        for item in value.values():
            session_id = _find_session_id(item)
            if session_id:
                return session_id
    if isinstance(value, list):
        for item in value:
            session_id = _find_session_id(item)
            if session_id:
                return session_id
    return ""


# 컴포넌트 설명: 18 MongoDB Data Store
# Langflow 표시 설명: 큰 결과 row list를 MongoDB result collection에 저장하고 payload에는 compact data_ref만 남깁니다.
class MongoDBDataStore(Component):

    display_name = "18 MongoDB Data Store"
    description = "큰 결과 row list를 MongoDB result collection에 저장하고 payload에는 compact data_ref만 남깁니다."
    icon = "Database"
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="mongo_uri", display_name="Mongo URI", value="", advanced=True),
        MessageTextInput(name="mongo_database", display_name="Mongo Database", value="", advanced=True),
        MessageTextInput(
            name="result_collection_name",
            display_name="Result Collection Full Name",

            value=DEFAULT_RESULT_COLLECTION,
            advanced=True,
        ),
        DropdownInput(name="enabled", display_name="Enabled", options=ENABLED_OPTIONS, value="true", advanced=True),
        MessageTextInput(name="preview_row_limit", display_name="Preview Row Limit", value="5", advanced=True),
        MessageTextInput(name="min_rows", display_name="Min Rows To Store", value="1", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 큰 결과 row list를 MongoDB result collection에 저장하고 payload에는 compact data_ref만 남깁니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = store_payload_in_mongodb(
            getattr(self, "payload", None),
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            getattr(self, "result_collection_name", ""),
            getattr(self, "enabled", "true"),
            getattr(self, "preview_row_limit", "5"),
            getattr(self, "min_rows", "1"),
        )
        meta = result.get("mongo_data_store", {}) if isinstance(result, dict) else {}
        self.status = {
            "stored": meta.get("stored", False),
            "ref_count": meta.get("ref_count", 0),
            "errors": len(meta.get("errors", [])) if isinstance(meta.get("errors"), list) else 0,
        }
        return Data(data=result)
