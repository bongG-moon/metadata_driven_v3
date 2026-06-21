# 파일 설명: 00 Main Flow Filter Authoring Request Loader Langflow custom component 파일입니다.
# 흐름 역할: 자연어 main-flow-filter 등록 요청을 시작하고 필요하면 기존 filter item을 MongoDB에서 요약 로드합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DropdownInput, MessageTextInput, Output
from lfx.schema.data import Data


DEFAULT_COLLECTION_NAME = "agent_v3_main_flow_filters"
COLLECTION_ENV_KEY = "MONGODB_MAIN_FLOW_FILTER_COLLECTION"
LEGACY_COLLECTION_SUFFIX = "main_flow_filters"
DUPLICATE_ACTION_OPTIONS = ["ask", "merge", "replace", "skip", "create_new"]
LOAD_EXISTING_OPTIONS = ["true", "false"]


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 자연어 main-flow-filter 등록 요청을 시작하고 필요하면 기존 filter item을 MongoDB에서 요약 로드합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_main_flow_filter_authoring_request(
    raw_text: Any,
    mongo_uri: str = "",
    mongo_database: str = "",
    collection_prefix: str = "",
    collection_name: str = "",
    duplicate_action: str = "ask",
    load_existing: str = "true",
    load_limit: str = "200",
) -> dict[str, Any]:
    database = _clean(mongo_database or os.getenv("MONGODB_DATABASE") or "metadata_driven_agent_v3")
    collection = _resolve_collection_name(collection_name, collection_prefix)
    uri = _clean(mongo_uri or os.getenv("MONGODB_URI"))
    existing_items = []
    load_errors: list[str] = []
    if _as_bool(load_existing, True):
        existing_items, load_errors = _load_existing_filter_items(uri, database, collection, _safe_int(load_limit, 200))
    return {
        "metadata_type": "main_flow_filter",
        "raw_text": _clean(raw_text),
        "refined_text": "",
        "items": [],
        "existing_items": existing_items,
        "existing_matches": [],
        "conflict_warnings": [],
        "duplicate_decision": {"action": _action(duplicate_action), "requires_user_choice": False},
        "review": {},
        "write_result": {},
        "mongo_config": {
            "database": database,
            "collection": collection,
            "has_mongo_uri": bool(uri),
        },
        "errors": [f"existing_load: {item}" for item in load_errors],
        "warnings": [],
        "trace": {"loaded_at": datetime.now(timezone.utc).isoformat()},
    }


def _load_existing_filter_items(
    mongo_uri: str,
    database: str,
    collection: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not mongo_uri:
        return [], ["mongo_uri is empty, so existing main flow filter metadata was not loaded."]
    client = None
    try:
        mongo_client_cls = getattr(import_module("pymongo"), "MongoClient")
        client = mongo_client_cls(mongo_uri, serverSelectionTimeoutMS=5000)
        docs = list(client[database][collection].find({}).limit(limit))
        return [_compact_filter_doc(_json_ready(doc)) for doc in docs if _is_active(doc)], []
    except Exception as exc:
        return [], [str(exc)]
    finally:
        if client is not None:
            client.close()


def _compact_filter_doc(doc: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(doc.get("payload")) if isinstance(doc.get("payload"), dict) else {}
    filter_key = _clean(doc.get("filter_key") or doc.get("key") or doc.get("parameter_key"))
    return {
        "id": _clean(doc.get("_id") or f"main_flow_filter:{filter_key}"),
        "filter_key": filter_key,
        "display_name": _clean(payload.get("display_name")),
        "aliases": _as_list(payload.get("aliases")),
        "column_candidates": _as_list(payload.get("column_candidates")),
        "semantic_role": _clean(payload.get("semantic_role")),
        "value_type": _clean(payload.get("value_type")),
        "operator": _clean(payload.get("operator")),
    }


def _is_active(doc: dict[str, Any]) -> bool:
    status = _clean(doc.get("status")).lower()
    return not status or status in {"active", "enabled"}


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return str(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    result = []
    for item in value:
        text = _clean(item)
        if text and text not in result:
            result.append(text)
    return result


def _safe_int(value: Any, default: int) -> int:
    try:
        return max(1, int(str(value or "").strip()))
    except Exception:
        return default


def _as_bool(value: Any, default: bool) -> bool:
    text = _clean(value).lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def _action(value: Any) -> str:
    action = _clean(value).lower()
    return action if action in {"ask", "merge", "replace", "skip", "create_new"} else "ask"


def _resolve_collection_name(collection_name: str = "", collection_prefix: str = "") -> str:
    collection = _clean(collection_name or os.getenv(COLLECTION_ENV_KEY))
    if collection:
        return collection
    legacy_prefix = _clean(collection_prefix or os.getenv("MONGODB_COLLECTION_PREFIX"))
    if legacy_prefix:
        return f"{legacy_prefix}_{LEGACY_COLLECTION_SUFFIX}"
    return DEFAULT_COLLECTION_NAME


def _clean(value: Any) -> str:
    return str(value or "").strip()


# 컴포넌트 설명: 00 Main Flow Filter Authoring Request Loader
# Langflow 표시 설명: 자연어 main-flow-filter 등록 요청을 시작하고 필요하면 기존 filter item을 MongoDB에서 요약 로드합니다.
class MainFlowFilterAuthoringRequestLoader(Component):

    display_name = "00 Main Flow Filter Authoring Request Loader"
    description = "자연어 main-flow-filter 등록 요청을 시작하고 필요하면 기존 filter item을 MongoDB에서 요약 로드합니다."
    inputs = [
        MessageTextInput(name="raw_text", display_name="Natural Language Filter Description", required=True),
        MessageTextInput(name="mongo_uri", display_name="Mongo URI", value=""),
        MessageTextInput(name="mongo_database", display_name="Mongo Database", value="metadata_driven_agent_v3"),
        MessageTextInput(name="collection_name", display_name="Collection Name", value=DEFAULT_COLLECTION_NAME),
        DropdownInput(name="duplicate_action", display_name="Duplicate Action", options=DUPLICATE_ACTION_OPTIONS, value="ask", advanced=True),
        DropdownInput(name="load_existing", display_name="Load Existing Items", options=LOAD_EXISTING_OPTIONS, value="true", advanced=True),
        MessageTextInput(name="load_limit", display_name="Load Limit", value="200", advanced=True),

    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 자연어 main-flow-filter 등록 요청을 시작하고 필요하면 기존 filter item을 MongoDB에서 요약 로드합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = build_main_flow_filter_authoring_request(
            raw_text=getattr(self, "raw_text", ""),
            mongo_uri=getattr(self, "mongo_uri", ""),
            mongo_database=getattr(self, "mongo_database", ""),
            collection_prefix="",
            collection_name=getattr(self, "collection_name", DEFAULT_COLLECTION_NAME),
            duplicate_action=getattr(self, "duplicate_action", "ask"),
            load_existing=getattr(self, "load_existing", "true"),
            load_limit=getattr(self, "load_limit", "200"),
        )
        self.status = {
            "metadata_type": "main_flow_filter",
            "existing_items": len(result.get("existing_items", [])),
            "errors": len(result.get("errors", [])),
        }
        return Data(data=result)
