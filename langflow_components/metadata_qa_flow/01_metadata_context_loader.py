# 파일 설명: 01 Metadata Context Loader Langflow custom component 파일입니다.
# 흐름 역할: MongoDB에서 domain, table catalog, main-flow-filter 메타데이터를 읽어 payload에 붙입니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


CORE_DOMAIN_SECTIONS = {
    "process_groups",
    "product_terms",
    "product_attribute_resolvers",
    "quantity_terms",
    "metric_terms",
    "status_terms",
    "analysis_recipes",
}

DEFAULT_COLLECTIONS = {
    "domain_items": "agent_v3_domain_items",
    "table_catalog": "agent_v3_table_catalog_items",
    "main_flow_filters": "agent_v3_main_flow_filters",
}

COLLECTION_ENV_KEYS = {
    "domain_items": "MONGODB_DOMAIN_COLLECTION",
    "table_catalog": "MONGODB_TABLE_CATALOG_COLLECTION",
    "main_flow_filters": "MONGODB_MAIN_FLOW_FILTER_COLLECTION",
}

# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: MongoDB에서 domain, table catalog, main-flow-filter 메타데이터를 읽어 payload에 붙입니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def load_metadata_payload(
    payload: dict[str, Any],
    mongo_uri: str = "",
    mongo_database: str = "",
    load_limit: str = "1000",
    domain_collection_name: str = "",
    table_catalog_collection_name: str = "",
    main_flow_filter_collection_name: str = "",
) -> dict[str, Any]:
    mongo_uri = _clean_text(mongo_uri or os.getenv("MONGODB_URI"))
    mongo_database = _clean_text(mongo_database or os.getenv("MONGODB_DATABASE") or "metadata_driven_agent_v3")
    collections = _metadata_collections(
        domain_collection_name,
        table_catalog_collection_name,
        main_flow_filter_collection_name,
    )
    limit = _safe_int(load_limit, default=1000)
    metadata, load_info = load_metadata_from_mongodb(mongo_uri, mongo_database, collections, limit)
    return _attach_metadata(payload, metadata, load_info)


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: MongoDB에서 domain, table catalog, main-flow-filter 메타데이터를 읽어 payload에 붙입니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def load_metadata_from_mongodb(
    mongo_uri: str,
    mongo_database: str,
    collections: dict[str, str],
    limit: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = _empty_metadata()
    errors: list[str] = []
    docs_by_kind: dict[str, list[dict[str, Any]]] = {
        "domain_items": [],
        "table_catalog": [],
        "main_flow_filters": [],
    }

    if not mongo_uri:
        errors.append("mongo_uri is empty. Set the input value or MONGODB_URI.")
    if not mongo_database:
        errors.append("mongo_database is empty. Set the input value or MONGODB_DATABASE.")
    missing_collections = [kind for kind, name in collections.items() if not _clean_text(name)]
    if missing_collections:
        errors.append("collection names are empty: " + ", ".join(missing_collections))
    if errors:
        return metadata, _load_info("mongodb", mongo_database, collections, metadata, errors)

    client = None
    try:
        mongo_client_cls = getattr(import_module("pymongo"), "MongoClient")
        client = mongo_client_cls(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[mongo_database]
        for kind, collection_name in collections.items():
            cursor = db[collection_name].find({}).limit(limit)
            docs_by_kind[kind] = [_json_ready(dict(item)) for item in cursor]
    except Exception as exc:
        errors.append(str(exc))
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()

    if not errors:
        metadata = _assemble_metadata_from_mongo_docs(
            docs_by_kind["domain_items"],
            docs_by_kind["table_catalog"],
            docs_by_kind["main_flow_filters"],
        )
    return metadata, _load_info("mongodb", mongo_database, collections, metadata, errors, docs_by_kind)


def _assemble_metadata_from_mongo_docs(
    domain_docs: list[dict[str, Any]],
    table_docs: list[dict[str, Any]],
    filter_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata = _empty_metadata()

    for doc in domain_docs:
        if not _is_active_doc(doc):
            continue
        section = _clean_text(doc.get("section") or doc.get("gbn"))
        key = _clean_text(doc.get("key") or doc.get("name"))
        payload = deepcopy(doc.get("payload")) if isinstance(doc.get("payload"), dict) else {}
        if section == "product_key_columns":
            columns = doc.get("columns") or payload.get("columns") or payload.get("product_key_columns") or payload
            metadata["domain_items"]["product_key_columns"] = _as_string_list(columns)
        elif section in CORE_DOMAIN_SECTIONS and key:
            metadata["domain_items"].setdefault(section, {})[key] = payload

    for doc in table_docs:
        if not _is_active_doc(doc):
            continue
        dataset_key = _clean_text(doc.get("dataset_key") or doc.get("key"))
        payload = deepcopy(doc.get("payload")) if isinstance(doc.get("payload"), dict) else {}
        if dataset_key:
            metadata["table_catalog"]["datasets"][dataset_key] = payload

    for doc in filter_docs:
        if not _is_active_doc(doc):
            continue
        filter_key = _clean_text(doc.get("filter_key") or doc.get("key") or doc.get("parameter_key"))
        payload = deepcopy(doc.get("payload")) if isinstance(doc.get("payload"), dict) else {}
        if filter_key:
            metadata["main_flow_filters"][filter_key] = payload

    return metadata


def _attach_metadata(payload: dict[str, Any], metadata: dict[str, Any], load_info: dict[str, Any]) -> dict[str, Any]:
    next_payload = dict(payload or {})
    next_payload["metadata"] = metadata
    next_payload["metadata_context"] = {
        "domain_refs": [],
        "table_refs": [],
        "filter_refs": [],
        "metadata_load": _compact_load_info(load_info),
    }
    warnings = list(next_payload.get("warnings", [])) if isinstance(next_payload.get("warnings"), list) else []
    for error in load_info.get("errors", []):
        warnings.append(f"metadata_load: {error}")
    if warnings:
        next_payload["warnings"] = warnings
    return next_payload


def _empty_metadata() -> dict[str, Any]:
    return {
        "domain_items": {
            "process_groups": {},
            "product_terms": {},
            "product_attribute_resolvers": {},
            "quantity_terms": {},
            "metric_terms": {},
            "status_terms": {},
            "analysis_recipes": {},
            "product_key_columns": [],
        },
        "table_catalog": {"datasets": {}},
        "main_flow_filters": {},
    }


def _metadata_counts(metadata: dict[str, Any]) -> dict[str, int]:
    domain = metadata.get("domain_items", {}) if isinstance(metadata.get("domain_items"), dict) else {}
    return {
        "process_groups": len(domain.get("process_groups", {})),
        "product_terms": len(domain.get("product_terms", {})),
        "product_attribute_resolvers": len(domain.get("product_attribute_resolvers", {})),
        "quantity_terms": len(domain.get("quantity_terms", {})),
        "metric_terms": len(domain.get("metric_terms", {})),
        "status_terms": len(domain.get("status_terms", {})),
        "analysis_recipes": len(domain.get("analysis_recipes", {})),
        "product_key_columns": len(domain.get("product_key_columns", [])),
        "datasets": len((metadata.get("table_catalog", {}) or {}).get("datasets", {})),
        "main_flow_filters": len(metadata.get("main_flow_filters", {})),
    }


def _metadata_collections(
    domain_collection_name: str = "",
    table_catalog_collection_name: str = "",
    main_flow_filter_collection_name: str = "",
) -> dict[str, str]:
    raw_inputs = {
        "domain_items": domain_collection_name,
        "table_catalog": table_catalog_collection_name,
        "main_flow_filters": main_flow_filter_collection_name,
    }
    collections: dict[str, str] = {}
    for kind, default_collection in DEFAULT_COLLECTIONS.items():
        explicit = _clean_text(raw_inputs.get(kind) or os.getenv(COLLECTION_ENV_KEYS[kind]))
        collections[kind] = explicit or default_collection
    return collections


def _load_info(
    source: str,
    database: str,
    collections: dict[str, str],
    metadata: dict[str, Any],
    errors: list[str],
    docs_by_kind: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    document_counts = {key: len(value) for key, value in (docs_by_kind or {}).items()}
    return {
        "source": source,
        "loaded_at": _now_iso(),
        "database": database,
        "collections": collections,
        "document_counts": document_counts,
        "counts": _metadata_counts(metadata),
        "errors": errors,
    }


def _compact_load_info(load_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": load_info.get("source"),
        "loaded_at": load_info.get("loaded_at"),
        "database": load_info.get("database"),
        "collections": load_info.get("collections", {}),
        "document_counts": load_info.get("document_counts", {}),
        "counts": load_info.get("counts", {}),
        "errors": load_info.get("errors", []),
    }


def _is_active_doc(doc: dict[str, Any]) -> bool:
    status = _clean_text(doc.get("status")).lower()
    return not status or status in {"active", "enabled"}


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("columns") or value.get("values") or []
    if not isinstance(value, list):
        value = [value]
    return [_clean_text(item) for item in value if _clean_text(item)]


def _safe_int(value: Any, default: int) -> int:
    try:
        return max(1, int(str(value or "").strip()))
    except Exception:
        return default


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return str(value)


# 컴포넌트 설명: 01 Metadata Context Loader
# Langflow 표시 설명: MongoDB에서 domain, table catalog, main-flow-filter 메타데이터를 읽어 payload에 붙입니다.
class MetadataContextLoader(Component):

    display_name = "01 Metadata Context Loader"
    description = "MongoDB에서 domain, table catalog, main-flow-filter 메타데이터를 읽어 payload에 붙입니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="mongo_uri", display_name="Mongo URI", value=""),
        MessageTextInput(name="mongo_database", display_name="Mongo Database", value="metadata_driven_agent_v3"),
        MessageTextInput(name="domain_collection_name", display_name="Domain Collection Name", value=DEFAULT_COLLECTIONS["domain_items"]),
        MessageTextInput(
            name="table_catalog_collection_name",
            display_name="Table Catalog Collection Name",
            value=DEFAULT_COLLECTIONS["table_catalog"],
        ),
        MessageTextInput(
            name="main_flow_filter_collection_name",
            display_name="Main Flow Filter Collection Name",

            value=DEFAULT_COLLECTIONS["main_flow_filters"],
        ),
        MessageTextInput(name="load_limit", display_name="Load Limit", value="1000", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: MongoDB에서 domain, table catalog, main-flow-filter 메타데이터를 읽어 payload에 붙입니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        payload = getattr(self.payload, "data", self.payload)
        result = load_metadata_payload(
            payload,
            getattr(self, "mongo_uri", ""),
            getattr(self, "mongo_database", ""),
            load_limit=getattr(self, "load_limit", "1000"),
            domain_collection_name=getattr(self, "domain_collection_name", ""),
            table_catalog_collection_name=getattr(self, "table_catalog_collection_name", ""),
            main_flow_filter_collection_name=getattr(self, "main_flow_filter_collection_name", ""),
        )
        load_info = result.get("metadata_context", {}).get("metadata_load", {})
        self.status = {
            "source": load_info.get("source"),
            "counts": load_info.get("counts", {}),
            "errors": len(load_info.get("errors", [])),
        }
        return Data(data=result)
