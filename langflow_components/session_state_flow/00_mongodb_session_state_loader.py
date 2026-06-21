# 파일 설명: 00 MongoDB Session State Loader Langflow custom component 파일입니다.
# 흐름 역할: 대화 session_id 기준으로 이전 compact state를 MongoDB에서 읽어 router 또는 subflow에 전달합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DropdownInput, MessageTextInput, Output
from lfx.schema.data import Data


DEFAULT_DATABASE = "metadata_driven_agent_v3"
DEFAULT_SESSION_COLLECTION = "agent_v3_session_states"
DEFAULT_STATE_PREVIEW_LIMIT = 5
ENABLED_OPTIONS = ["true", "false"]


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 대화 session_id 기준으로 이전 compact state를 MongoDB에서 읽어 router 또는 subflow에 전달합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def load_session_state_payload(
    question: Any = "",
    state: Any = None,
    mongo_uri: Any = "",
    mongo_database: Any = "",
    session_collection_name: Any = "",
    enabled: Any = "true",
    preview_row_limit: Any = "5",
) -> dict[str, Any]:
    explicit_state = _state_from_value(state)
    session = _session_id_from_value(question) or _session_id_from_state(explicit_state) or "demo-session"
    preview_limit = _positive_int(preview_row_limit, default=DEFAULT_STATE_PREVIEW_LIMIT, minimum=0)
    load_status: dict[str, Any] = {
        "enabled": _truthy(enabled),
        "loaded": False,
        "source": "empty",
        "session_id": session,
        "collection_name": _collection_name(session_collection_name),
        "errors": [],
    }

    if explicit_state:
        compact_state = _compact_state(explicit_state, preview_limit=preview_limit)
        load_status["source"] = "input_state"
        return _request_payload(question, session, compact_state, load_status)

    if not _truthy(enabled):
        load_status["source"] = "disabled"
        return _request_payload(question, session, {}, load_status)

    uri = _clean(mongo_uri) or os.getenv("MONGODB_URI", "") or os.getenv("MONGO_URI", "")
    database = _clean(mongo_database) or os.getenv("MONGODB_DATABASE", "") or os.getenv("MONGO_DB_NAME", "") or DEFAULT_DATABASE
    collection_name = _collection_name(session_collection_name)
    load_status["collection_name"] = collection_name
    missing = []
    if not uri:
        missing.append("Mongo URI is empty.")
    if not database:
        missing.append("Mongo database is empty.")
    if not collection_name:
        missing.append("Mongo session state collection name is empty.")
    if missing:
        load_status["errors"] = missing
        return _request_payload(question, session, {}, load_status)

    client = None
    try:
        client, collection = _connect_collection(uri, database, collection_name)
        document = collection.find_one({"_id": _document_id(session)}) or collection.find_one({"session_id": session})
        if not isinstance(document, dict):
            load_status["source"] = "mongodb_not_found"
            return _request_payload(question, session, {}, load_status)
        stored_state = document.get("state") if isinstance(document.get("state"), dict) else {}
        compact_state = _compact_state(stored_state, preview_limit=preview_limit)
        load_status.update(
            {
                "loaded": bool(compact_state),
                "source": "mongodb",
                "updated_at": document.get("updated_at", ""),
                "turn_count": document.get("turn_count", 0),
                "preview_row_limit": preview_limit,
            }
        )
        return _request_payload(question, session, compact_state, load_status)
    except Exception as exc:
        load_status["errors"] = [str(exc)]
        return _request_payload(question, session, {}, load_status)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _request_payload(question: Any, session_id: str, state: dict[str, Any], load_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "payload_version": "agent-v1",
        "status": "ok",
        "request": {
            "session_id": session_id,
            "question": _text_value(question),
            "timezone": "Asia/Seoul",
        },
        "state": state,
        "session_state_load": load_status,
        "info": [],
        "warnings": [],
        "errors": [],
    }


def _compact_state(state: Any, preview_limit: int = DEFAULT_STATE_PREVIEW_LIMIT) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    result = deepcopy(state)
    result.pop("runtime_sources", None)
    result["chat_history"] = list(result.get("chat_history", []))[-10:] if isinstance(result.get("chat_history"), list) else []
    result["context"] = dict(result.get("context", {})) if isinstance(result.get("context"), dict) else {}
    result["current_data"] = _compact_current_data(result.get("current_data"), preview_limit=preview_limit)
    result["followup_source_results"] = [
        _compact_source_result(item, preview_limit=preview_limit)
        for item in result.get("followup_source_results", [])
        if isinstance(item, dict)
    ]
    if not isinstance(result.get("runtime_source_refs"), dict):
        result.pop("runtime_source_refs", None)
    return _json_ready(result)


def _compact_current_data(current_data: Any, preview_limit: int = DEFAULT_STATE_PREVIEW_LIMIT) -> dict[str, Any]:
    if not isinstance(current_data, dict):
        return {}
    result = deepcopy(current_data)
    rows = _rows_from(result)
    row_count = _positive_int(result.get("row_count"), default=len(rows), minimum=0)
    if rows:
        result["rows"] = deepcopy(rows[:preview_limit])
        result.pop("data", None)
        result["data_is_preview"] = row_count > len(result["rows"])
        if isinstance(result.get("data_ref"), dict):
            result.setdefault("data_ref_loaded", False)
            result.setdefault("data_ref_load_mode", "preview")
    result["row_count"] = row_count
    columns = result.get("columns") if isinstance(result.get("columns"), list) else []
    if not columns:
        columns = _rows_columns(rows)
    result["columns"] = columns
    product_key_columns = [str(item) for item in result.get("product_key_columns", []) if str(item or "").strip()] if isinstance(result.get("product_key_columns"), list) else []
    result["product_key_columns"] = product_key_columns
    product_key_values = result.get("product_key_values") if isinstance(result.get("product_key_values"), list) else []
    if not product_key_values and product_key_columns:
        product_key_values = _product_key_values(_rows_from(result), product_key_columns)
    result["product_key_values"] = deepcopy(product_key_values)
    result["product_key_count"] = _positive_int(result.get("product_key_count"), default=len(product_key_values), minimum=0)
    if not isinstance(result.get("source_dataset_keys"), list):
        result["source_dataset_keys"] = []
    if not isinstance(result.get("source_aliases"), list):
        result["source_aliases"] = []
    return result


def _compact_source_result(source: dict[str, Any], preview_limit: int = DEFAULT_STATE_PREVIEW_LIMIT) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "source_alias",
        "dataset_key",
        "source_type",
        "columns",
        "data_ref",
        "row_count",
        "data_is_reference",
        "data_is_preview",
        "applied_params",
        "applied_filters",
    ):
        if source.get(key) not in (None, "", [], {}):
            result[key] = deepcopy(source[key])
    rows = _rows_from(source)
    if rows and not isinstance(result.get("data_ref"), dict):
        result["rows"] = deepcopy(rows[:preview_limit])
        result["row_count"] = _positive_int(result.get("row_count"), default=len(rows), minimum=0)
        result["data_is_preview"] = len(rows) > preview_limit
    return result


def _rows_from(value: dict[str, Any]) -> list[dict[str, Any]]:
    rows = value.get("rows")
    if not isinstance(rows, list):
        rows = value.get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _rows_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _product_key_values(rows: list[dict[str, Any]], product_key_columns: list[str]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in rows:
        product = {key: row.get(key) for key in product_key_columns if row.get(key) not in {None, ""}}
        if product and product not in values:
            values.append(product)
    return values


def _state_from_value(value: Any) -> dict[str, Any]:
    payload = _payload(value)
    if not payload:
        return {}
    if isinstance(payload.get("state"), dict):
        return deepcopy(payload["state"])
    if isinstance(payload.get("previous_state"), dict):
        previous = payload["previous_state"]
        nested = previous.get("state") if isinstance(previous.get("state"), dict) else previous
        return deepcopy(nested)
    if any(key in payload for key in ("chat_history", "context", "current_data", "followup_source_results")):
        return deepcopy(payload)
    return {}


def _payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
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
            return {}
        return deepcopy(parsed) if isinstance(parsed, dict) else {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return deepcopy(parsed) if isinstance(parsed, dict) else {}
    return {}


def _connect_collection(uri: str, database: str, collection_name: str) -> tuple[Any, Any]:
    pymongo = import_module("pymongo")
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client, client[database][collection_name]


def _collection_name(value: Any) -> str:
    return _clean(value) or os.getenv("MONGODB_SESSION_STATE_COLLECTION", "") or DEFAULT_SESSION_COLLECTION


def _document_id(session_id: str) -> str:
    return f"session_state:{session_id}"


def _session_id_from_state(state: dict[str, Any]) -> str:
    for key in ("session_id", "conversation_id", "chat_id"):
        if state.get(key) not in (None, ""):
            return str(state[key]).strip()
    return ""


def _session_id_from_value(value: Any) -> str:
    for attr in ("session_id", "conversation_id", "chat_id"):
        text = str(getattr(value, attr, "") or "").strip()
        if text:
            return text
    payload = _payload(value)
    if payload:
        return _session_id_from_state(payload)
    return ""


def _text_value(value: Any) -> str:
    for attr in ("text", "content"):
        text = getattr(value, attr, None)
        if isinstance(text, str):
            return text
    get_text = getattr(value, "get_text", None)
    if callable(get_text):
        try:
            text = get_text()
            if isinstance(text, str):
                return text
        except Exception:
            pass
    if isinstance(value, str):
        return value
    return str(value or "")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"", "0", "false", "no", "n", "off", "disabled"}


def _positive_int(value: Any, default: int, minimum: int = 0) -> int:
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
        return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# 컴포넌트 설명: 00 MongoDB Session State Loader
# Langflow 표시 설명: 대화 session_id 기준으로 이전 compact state를 MongoDB에서 읽어 router 또는 subflow에 전달합니다.
class MongoDBSessionStateLoader(Component):

    display_name = "00 MongoDB Session State Loader"
    description = "대화 session_id 기준으로 이전 compact state를 MongoDB에서 읽어 router 또는 subflow에 전달합니다."
    icon = "Database"
    name = "MongoDBSessionStateLoader"

    inputs = [
        MessageTextInput(name="question", display_name="Question", required=True),
        MessageTextInput(name="mongo_uri", display_name="Mongo URI", value="", advanced=True),
        MessageTextInput(name="mongo_database", display_name="Mongo Database", value=DEFAULT_DATABASE, advanced=True),
        MessageTextInput(name="session_collection_name", display_name="Session State Collection", value=DEFAULT_SESSION_COLLECTION, advanced=True),

        DropdownInput(name="enabled", display_name="Enabled", options=ENABLED_OPTIONS, value="true", advanced=True),
        MessageTextInput(name="preview_row_limit", display_name="Preview Row Limit", value=str(DEFAULT_STATE_PREVIEW_LIMIT), advanced=True),
    ]
    outputs = [Output(name="loaded_state", display_name="Loaded State", method="build_state", types=["Data"])]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 대화 session_id 기준으로 이전 compact state를 MongoDB에서 읽어 router 또는 subflow에 전달합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def _result(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_session_state_payload", None)
        if isinstance(cached, dict):
            return cached
        result = load_session_state_payload(
            getattr(self, "question", ""),
            None,
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            getattr(self, "session_collection_name", ""),
            getattr(self, "enabled", "true"),
            getattr(self, "preview_row_limit", str(DEFAULT_STATE_PREVIEW_LIMIT)),
        )
        self._cached_session_state_payload = result
        self.status = result.get("session_state_load", {})
        return result

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 대화 session_id 기준으로 이전 compact state를 MongoDB에서 읽어 router 또는 subflow에 전달합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_state(self) -> Data:
        return Data(data=deepcopy(self._result().get("state", {})))
