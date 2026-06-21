# 파일 설명: 05 MongoDB Data Loader Langflow custom component 파일입니다.
# 흐름 역할: MongoDB data_ref가 가리키는 저장 결과를 preview 또는 full rows 형태로 복원합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import os
from copy import deepcopy
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, MessageTextInput, Output
from lfx.schema.data import Data


DEFAULT_RESULT_COLLECTION = "agent_v3_result_store"
ENABLED_OPTIONS = ["true", "false"]
RESTORE_MODE_OPTIONS = ["auto", "preview", "full"]


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: MongoDB data_ref가 가리키는 저장 결과를 preview 또는 full rows 형태로 복원합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def load_payload_from_mongodb(
    payload_value: Any,
    mongo_uri: Any = "",
    mongo_database: Any = "",
    result_collection_name: Any = "",
    enabled: Any = "true",
    restore_mode: Any = "preview",
    preview_row_limit: Any = "5",
) -> dict[str, Any]:
    payload = _payload(payload_value)
    if not payload:
        return {"mongo_data_load": {"enabled": False, "loaded": False, "ref_count": 0, "errors": ["empty payload"]}}

    if not _truthy(enabled):
        return {**payload, "mongo_data_load": {"enabled": False, "loaded": False, "ref_count": 0, "errors": []}}

    uri = _clean(mongo_uri) or os.getenv("MONGODB_URI", "")
    database = _clean(mongo_database) or os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v3")
    collection_name = _clean(result_collection_name) or os.getenv("MONGODB_RESULT_COLLECTION", DEFAULT_RESULT_COLLECTION)
    requested_mode = _restore_mode(restore_mode)
    mode = _resolve_restore_mode(requested_mode, payload)
    preview_limit = _positive_int(preview_row_limit, default=5, minimum=0)
    missing = []
    if not uri:
        missing.append("Mongo URI is empty.")
    if not database:
        missing.append("Mongo database is empty.")
    if not collection_name:
        missing.append("Mongo result collection name is empty.")
    if missing:
        return {**payload, "mongo_data_load": {"enabled": True, "loaded": False, "ref_count": 0, "errors": missing}}

    client = None
    loaded: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    cache: dict[str, dict[str, Any]] = {}
    try:
        client, collection = _connect_collection(uri, database, collection_name)
        restored = _restore_refs(
            payload,
            collection,
            loaded,
            skipped,
            cache,
            path="",
            restore_mode=mode,
            preview_limit=preview_limit,
        )
        restored["mongo_data_load"] = {
            "enabled": True,
            "loaded": bool(loaded),
            "restore_mode": mode,
            "requested_restore_mode": requested_mode,
            "preview_row_limit": preview_limit,
            "ref_count": len(loaded),
            "unique_ref_count": len(cache),
            "loaded_refs": loaded,
            "skipped_refs": skipped,
            "result_collection_name": collection_name,
            "errors": [],
        }
        return restored
    except Exception as exc:
        return {**payload, "mongo_data_load": {"enabled": True, "loaded": False, "ref_count": 0, "errors": [str(exc)]}}
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _restore_refs(
    value: Any,
    collection: Any,
    loaded: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    cache: dict[str, dict[str, Any]],
    path: str,
    restore_mode: str,
    preview_limit: int,
) -> Any:
    if isinstance(value, dict):
        if _metadata_only_path(path):
            return deepcopy(value)

        result = {
            key: _restore_refs(
                item,
                collection,
                loaded,
                skipped,
                cache,
                f"{path}.{key}" if path else key,
                restore_mode=restore_mode,
                preview_limit=preview_limit,
            )
            for key, item in value.items()
        }

        runtime_refs = result.get("runtime_source_refs") if isinstance(result.get("runtime_source_refs"), dict) else {}
        if runtime_refs:
            if restore_mode == "full":
                runtime_sources = result.get("runtime_sources") if isinstance(result.get("runtime_sources"), dict) else {}
                runtime_sources = deepcopy(runtime_sources)
                for alias, data_ref in runtime_refs.items():
                    if not _is_mongo_ref(data_ref):
                        continue
                    loaded_rows = _load_rows(collection, data_ref, cache, row_limit=None)
                    rows = loaded_rows["rows"]
                    if rows:
                        alias_text = str(alias)
                        runtime_sources[alias_text] = _json_ready(rows)
                        loaded.append(
                            {
                                "path": f"{path}.runtime_sources.{alias_text}" if path else f"runtime_sources.{alias_text}",
                                "ref_id": data_ref.get("ref_id"),
                                "row_count": len(rows),
                                "cache_hit": loaded_rows["cache_hit"],
                                "mode": "full",
                            }
                        )
                result["runtime_sources"] = runtime_sources
                result["runtime_sources_are_preview"] = False
            else:
                for alias, data_ref in runtime_refs.items():
                    if _is_mongo_ref(data_ref):
                        skipped.append(
                            {
                                "path": f"{path}.runtime_sources.{alias}" if path else f"runtime_sources.{alias}",
                                "ref_id": data_ref.get("ref_id"),
                                "reason": "preview_mode_runtime_source",
                            }
                        )

        if path == "" and restore_mode == "full":
            _restore_followup_source_results(result, collection, loaded, cache)

        data_ref = result.get("data_ref") if isinstance(result.get("data_ref"), dict) else {}
        if _is_mongo_ref(data_ref):
            if not _should_restore_ref(path):
                skipped.append({"path": path, "ref_id": data_ref.get("ref_id"), "reason": "metadata_only"})
                return result
            target_key = _row_target_key(result, path)
            if restore_mode != "full":
                existing_rows = result.get(target_key)
                if isinstance(existing_rows, list):
                    _mark_preview_ref(result, data_ref, existing_rows, target_key, preview_limit)
                    skipped.append({"path": path, "ref_id": data_ref.get("ref_id"), "reason": "preview_rows_already_present"})
                    return result
                loaded_rows = _load_rows(collection, data_ref, cache, row_limit=preview_limit)
                rows = loaded_rows["rows"]
                if rows or preview_limit == 0:
                    result[target_key] = _json_ready(rows)
                    result["row_count"] = int(data_ref.get("row_count") or loaded_rows.get("row_count") or len(rows))
                    result["columns"] = list(data_ref.get("columns") or loaded_rows.get("columns") or _rows_columns(rows))
                    result["data_ref_preview_loaded"] = True
                    result["data_ref_loaded"] = False
                    result["data_ref_load_mode"] = "preview"
                    result["data_is_preview"] = True
                    loaded.append(
                        {
                            "path": path,
                            "ref_id": data_ref.get("ref_id"),
                            "row_count": len(rows),
                            "cache_hit": loaded_rows["cache_hit"],
                            "mode": "preview",
                        }
                    )
                return result
            loaded_rows = _load_rows(collection, data_ref, cache, row_limit=None)
            rows = loaded_rows["rows"]
            if rows:
                result[target_key] = _json_ready(rows)
                result["row_count"] = len(rows)
                result["columns"] = list(data_ref.get("columns") or loaded_rows.get("columns") or _rows_columns(rows))
                result["data_ref_loaded"] = True
                result["data_ref_load_mode"] = "full"
                result["data_is_preview"] = False
                loaded.append(
                    {
                        "path": path,
                        "ref_id": data_ref.get("ref_id"),
                        "row_count": len(rows),
                        "cache_hit": loaded_rows["cache_hit"],
                        "mode": "full",
                    }
                )
        return result
    if isinstance(value, list):
        return [
            _restore_refs(
                item,
                collection,
                loaded,
                skipped,
                cache,
                f"{path}[{index}]",
                restore_mode=restore_mode,
                preview_limit=preview_limit,
            )
            for index, item in enumerate(value)
        ]
    return deepcopy(value)


def _restore_followup_source_results(
    payload: dict[str, Any],
    collection: Any,
    loaded: list[dict[str, Any]],
    cache: dict[str, dict[str, Any]],
) -> None:
    refs_by_alias = _followup_source_refs(payload)
    if not refs_by_alias:
        return

    runtime_sources = payload.get("runtime_sources") if isinstance(payload.get("runtime_sources"), dict) else {}
    runtime_sources = deepcopy(runtime_sources)
    runtime_source_refs = payload.get("runtime_source_refs") if isinstance(payload.get("runtime_source_refs"), dict) else {}
    runtime_source_refs = deepcopy(runtime_source_refs)
    restored_any = False

    for alias, data_ref in refs_by_alias.items():
        loaded_rows = _load_rows(collection, data_ref, cache, row_limit=None)
        rows = loaded_rows["rows"]
        if not rows:
            continue
        runtime_sources[alias] = _json_ready(rows)
        runtime_source_refs[alias] = deepcopy(data_ref)
        restored_any = True
        loaded.append(
            {
                "path": f"runtime_sources.{alias}",
                "ref_id": data_ref.get("ref_id"),
                "row_count": len(rows),
                "cache_hit": loaded_rows["cache_hit"],
                "mode": "full",
                "source": "followup_source_results",
            }
        )

    if restored_any:
        payload["runtime_sources"] = runtime_sources
        payload["runtime_source_refs"] = runtime_source_refs
        payload["runtime_sources_are_preview"] = False


def _followup_source_refs(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    refs: dict[str, dict[str, Any]] = {}
    source_results = state.get("followup_source_results")
    if isinstance(source_results, list):
        for index, item in enumerate(source_results):
            if not isinstance(item, dict):
                continue
            data_ref = item.get("data_ref")
            if not _is_mongo_ref(data_ref):
                continue
            alias = _source_alias(item, index)
            refs.setdefault(alias, deepcopy(data_ref))

    state_refs = state.get("runtime_source_refs") if isinstance(state.get("runtime_source_refs"), dict) else {}
    for alias, data_ref in state_refs.items():
        if _is_mongo_ref(data_ref):
            refs.setdefault(str(alias), deepcopy(data_ref))
    return refs


def _source_alias(item: dict[str, Any], index: int) -> str:
    for key in ("source_alias", "alias", "dataset_key"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return f"previous_source_{index + 1}"


def _load_rows(
    collection: Any,
    data_ref: dict[str, Any],
    cache: dict[str, dict[str, Any]],
    row_limit: int | None,
) -> dict[str, Any]:
    ref_id = str(data_ref.get("ref_id") or data_ref.get("id") or "").strip()
    if not ref_id:
        return {"rows": [], "cache_hit": False, "row_count": 0, "columns": []}
    ref_collection = _collection_for_ref(collection, data_ref)
    cache_prefix = _ref_cache_key(data_ref)
    cache_key = f"{cache_prefix}:full" if row_limit is None else f"{cache_prefix}:preview:{row_limit}"
    if cache_key in cache:
        cached = deepcopy(cache[cache_key])
        cached["cache_hit"] = True
        return cached
    doc = _find_ref_doc(ref_collection, ref_id, row_limit)
    if not isinstance(doc, dict):
        return {"rows": [], "cache_hit": False, "row_count": 0, "columns": []}
    rows = doc.get("rows") if isinstance(doc.get("rows"), list) else doc.get("data")
    clean_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    if row_limit is not None:
        clean_rows = clean_rows[:row_limit]
    row_count = int(doc.get("row_count") or data_ref.get("row_count") or len(clean_rows))
    columns = list(doc.get("columns") or data_ref.get("columns") or _rows_columns(clean_rows))
    result = {"rows": clean_rows, "cache_hit": False, "row_count": row_count, "columns": columns}
    cache[cache_key] = deepcopy(result)
    return result


def _collection_for_ref(collection: Any, data_ref: dict[str, Any]) -> Any:
    ref_collection_name = _clean(data_ref.get("collection_name"))
    ref_database_name = _clean(data_ref.get("database") or data_ref.get("db_name"))
    if not ref_collection_name:
        return collection
    current_collection_name = _clean(getattr(collection, "name", ""))
    current_database = getattr(collection, "database", None)
    current_database_name = _clean(getattr(current_database, "name", ""))
    if ref_collection_name == current_collection_name and (not ref_database_name or ref_database_name == current_database_name):
        return collection
    if current_database is not None:
        if ref_database_name and ref_database_name != current_database_name:
            client = getattr(current_database, "client", None)
            if client is not None:
                try:
                    return client[ref_database_name][ref_collection_name]
                except Exception:
                    pass
        try:
            return current_database[ref_collection_name]
        except Exception:
            pass
    return collection


def _ref_cache_key(data_ref: dict[str, Any]) -> str:
    return "|".join(
        str(data_ref.get(key) or "")
        for key in ("database", "db_name", "collection_name", "ref_id", "id")
    )


def _find_ref_doc(collection: Any, ref_id: str, row_limit: int | None) -> dict[str, Any] | None:
    if row_limit is None:
        return collection.find_one({"ref_id": ref_id})
    projection = {
        "ref_id": 1,
        "row_count": 1,
        "columns": 1,
        "rows": {"$slice": row_limit},
        "data": {"$slice": row_limit},
    }
    try:
        return collection.find_one({"ref_id": ref_id}, projection)
    except TypeError:
        return collection.find_one({"ref_id": ref_id})


def _connect_collection(mongo_uri: str, database: str, collection_name: str) -> tuple[Any, Any]:
    mongo_client_cls = getattr(import_module("pymongo"), "MongoClient")
    client = mongo_client_cls(mongo_uri, serverSelectionTimeoutMS=5000)
    return client, client[database][collection_name]


def _metadata_only_path(path: str) -> bool:
    normalized = f".{path.lower()}"
    return any(
        segment in normalized
        for segment in (
            ".data_refs",
            ".runtime_source_refs",
            ".source_results",
            ".followup_source_results",
            ".metadata_context",
            ".mongo_data_store",
            ".mongo_data_load",
        )
    )


def _should_restore_ref(path: str) -> bool:
    normalized = path.lower()
    return bool(
        normalized.endswith("data")
        or normalized.endswith("analysis")
        or normalized.endswith("current_data")
        or ".state.current_data" in normalized
    )


def _row_target_key(value: dict[str, Any], path: str) -> str:
    if isinstance(value.get("rows"), list):
        return "rows"
    if isinstance(value.get("data"), list):
        return "data"
    if path.lower().endswith("data") or path.lower().endswith("current_data"):
        return "rows"
    return "data"


def _mark_preview_ref(result: dict[str, Any], data_ref: dict[str, Any], rows: list[Any], target_key: str, preview_limit: int) -> None:
    result["row_count"] = int(data_ref.get("row_count") or result.get("row_count") or len(rows))
    result["columns"] = list(data_ref.get("columns") or result.get("columns") or _rows_columns([row for row in rows if isinstance(row, dict)]))
    result["data_ref_loaded"] = False
    result["data_ref_load_mode"] = "preview"
    result["data_is_preview"] = bool(result.get("row_count", 0) > len(rows) or len(rows) >= preview_limit)
    result[target_key] = deepcopy(rows)


def _is_mongo_ref(value: Any) -> bool:
    return isinstance(value, dict) and str(value.get("store") or "").lower() == "mongodb" and bool(value.get("ref_id"))


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


def _restore_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"auto", "conditional"}:
        return "auto"
    if text in {"full", "all", "rows", "restore_full"}:
        return "full"
    return "preview"


def _resolve_restore_mode(mode: str, payload: dict[str, Any]) -> str:
    if mode != "auto":
        return mode
    return "full" if _requires_full_previous_result_restore(payload) else "preview"


def _requires_full_previous_result_restore(payload: dict[str, Any]) -> bool:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    if _truthy(plan.get("requires_full_previous_result_restore")):
        return True
    restore_mode = str(plan.get("previous_result_restore_mode") or "").strip().lower()
    return restore_mode in {"full", "all", "rows", "restore_full"}


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


# 컴포넌트 설명: 05 MongoDB Data Loader
# Langflow 표시 설명: MongoDB data_ref가 가리키는 저장 결과를 preview 또는 full rows 형태로 복원합니다.
class MongoDBDataLoader(Component):

    display_name = "05 MongoDB Data Loader"
    description = "MongoDB data_ref가 가리키는 저장 결과를 preview 또는 full rows 형태로 복원합니다."
    icon = "DatabaseZap"
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
        DropdownInput(name="restore_mode", display_name="Restore Mode", options=RESTORE_MODE_OPTIONS, value="auto", advanced=True),
        MessageTextInput(name="preview_row_limit", display_name="Preview Row Limit", value="5", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: MongoDB data_ref가 가리키는 저장 결과를 preview 또는 full rows 형태로 복원합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = load_payload_from_mongodb(
            getattr(self, "payload", None),
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            getattr(self, "result_collection_name", ""),
            getattr(self, "enabled", "true"),
            getattr(self, "restore_mode", "preview"),
            getattr(self, "preview_row_limit", "5"),
        )
        meta = result.get("mongo_data_load", {}) if isinstance(result, dict) else {}
        self.status = {
            "loaded": meta.get("loaded", False),
            "restore_mode": meta.get("restore_mode"),
            "ref_count": meta.get("ref_count", 0),
            "errors": len(meta.get("errors", [])) if isinstance(meta.get("errors"), list) else 0,
        }
        return Data(data=result)
