from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


# python tools\upload_json_to_mongodb.py `
#   --domain-registration-trace-json metadata\domain_items_with_registration_trace.json `
#   --table-registration-trace-json metadata\table_catalog_with_registration_trace.json `
#   --main-filter-registration-trace-json metadata\main_flow_filters_with_registration_trace.json



PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOMAIN_COLLECTION = "agent_v3_domain_items"
DEFAULT_TABLE_CATALOG_COLLECTION = "agent_v3_table_catalog_items"
DEFAULT_MAIN_FLOW_FILTER_COLLECTION = "agent_v3_main_flow_filters"
LEGACY_PREFIXES = {"agent_v1", "agent_v2", "agent_v3", "agent_v4"}
CORE_METADATA_KINDS = ("domain_items", "table_catalog", "main_flow_filters")
METADATA_KIND_ALIASES = {
    "domain": "domain_items",
    "domain_item": "domain_items",
    "domain_items": "domain_items",
    "table": "table_catalog",
    "table_catalog": "table_catalog",
    "table_catalog_items": "table_catalog",
    "data_catalog": "table_catalog",
    "catalog": "table_catalog",
    "filter": "main_flow_filters",
    "filters": "main_flow_filters",
    "main_filter": "main_flow_filters",
    "main_flow_filter": "main_flow_filters",
    "main_flow_filters": "main_flow_filters",
}


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Upload local JSON metadata/sample files to MongoDB.")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="Project root that contains metadata/ and sample_data/.")
    parser.add_argument("--mongo-uri", default=os.getenv("MONGODB_URI"), help="MongoDB URI. Defaults to MONGODB_URI.")
    parser.add_argument("--database", default=os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v3"))
    parser.add_argument("--domain-collection", default=os.getenv("MONGODB_DOMAIN_COLLECTION", ""))
    parser.add_argument("--table-catalog-collection", default=os.getenv("MONGODB_TABLE_CATALOG_COLLECTION", ""))
    parser.add_argument("--main-flow-filter-collection", default=os.getenv("MONGODB_MAIN_FLOW_FILTER_COLLECTION", ""))
    parser.add_argument(
        "--collection-prefix",
        default=os.getenv("MONGODB_COLLECTION_PREFIX", ""),
        help="Deprecated fallback for older automation and optional fixture collections.",
    )
    parser.add_argument(
        "--include-regression",
        action="store_true",
        help="Also upload regression_questions.json. Default uploads only the 3 core metadata collections.",
    )
    parser.add_argument(
        "--include-sample-data",
        action="store_true",
        help="Also upload sample_data/*.json collections. Use only for local validation fixtures.",
    )
    parser.add_argument(
        "--metadata-kind",
        "--kind",
        action="append",
        default=[],
        help=(
            "Core metadata kind to upload. Repeat or comma-separate values. "
            "Values: all, domain, table-catalog, main-flow-filter. Default uploads all core metadata."
        ),
    )
    parser.add_argument(
        "--domain-registration-trace-json",
        default="",
        help=(
            "Optional domain document export JSON that includes registration_trace. "
            "Use metadata/domain_items_with_registration_trace.json to upload domain payloads with registration input text."
        ),
    )
    parser.add_argument(
        "--table-registration-trace-json",
        default="",
        help=(
            "Optional table catalog document export JSON that includes registration_trace. "
            "Use metadata/table_catalog_with_registration_trace.json to upload table catalog payloads with registration input text."
        ),
    )
    parser.add_argument(
        "--main-filter-registration-trace-json",
        default="",
        help=(
            "Optional main flow filter document export JSON that includes registration_trace. "
            "Use metadata/main_flow_filters_with_registration_trace.json to upload filter payloads with registration input text."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Print upload plan without connecting to MongoDB.")
    parser.add_argument(
        "--mode",
        choices=["upsert", "replace"],
        default="upsert",
        help="upsert updates by deterministic _id. replace drops target collections before inserting.",
    )
    args = parser.parse_args()

    try:
        metadata_kinds = _normalize_metadata_kinds(args.metadata_kind)
    except ValueError as exc:
        parser.error(str(exc))

    root = Path(args.root).resolve()
    batches = build_upload_batches(
        root,
        domain_collection_name=args.domain_collection,
        table_catalog_collection_name=args.table_catalog_collection,
        main_flow_filter_collection_name=args.main_flow_filter_collection,
        include_regression=args.include_regression,
        include_sample_data=args.include_sample_data,
        collection_prefix=args.collection_prefix,
        metadata_kinds=metadata_kinds,
        domain_registration_trace_json=args.domain_registration_trace_json,
        table_registration_trace_json=args.table_registration_trace_json,
        main_filter_registration_trace_json=args.main_filter_registration_trace_json,
    )
    if args.dry_run:
        print_upload_plan(batches, database=args.database)
        return 0

    if not args.mongo_uri:
        print("Missing --mongo-uri or MONGODB_URI.", file=sys.stderr)
        return 2

    upload_batches(args.mongo_uri, args.database, batches, mode=args.mode)
    return 0


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def build_upload_batches(
    root: Path,
    domain_collection_name: str = "",
    table_catalog_collection_name: str = "",
    main_flow_filter_collection_name: str = "",
    include_regression: bool = False,
    include_sample_data: bool = False,
    collection_prefix: str = "",
    metadata_kinds: Any = None,
    domain_registration_trace_json: str = "",
    table_registration_trace_json: str = "",
    main_filter_registration_trace_json: str = "",
) -> dict[str, list[dict[str, Any]]]:
    metadata_dir = root / "metadata"
    sample_dir = root / "sample_data"
    collections = _resolve_metadata_collections(
        domain_collection_name,
        table_catalog_collection_name,
        main_flow_filter_collection_name,
        collection_prefix,
    )
    auxiliary_prefix = _resolve_auxiliary_prefix(collection_prefix, collections["domain_items"])

    selected_kinds = set(_normalize_metadata_kinds(metadata_kinds))
    domain_registration_trace_path = _optional_path(root, domain_registration_trace_json)
    table_registration_trace_path = _optional_path(root, table_registration_trace_json)
    main_filter_registration_trace_path = _optional_path(root, main_filter_registration_trace_json)
    metadata_doc_builders = {
        "domain_items": lambda: _domain_registration_trace_docs(domain_registration_trace_path)
        if domain_registration_trace_path
        else _domain_item_docs(metadata_dir / "domain_items.json"),
        "table_catalog": lambda: _metadata_document_export_docs(table_registration_trace_path, "table_catalog:")
        if table_registration_trace_path
        else _table_catalog_docs(metadata_dir / "table_catalog.json"),
        "main_flow_filters": lambda: _metadata_document_export_docs(main_filter_registration_trace_path, "main_flow_filter:")
        if main_filter_registration_trace_path
        else _main_flow_filter_docs(metadata_dir / "main_flow_filters.json"),
    }
    batches: dict[str, list[dict[str, Any]]] = {}
    for kind in CORE_METADATA_KINDS:
        if kind in selected_kinds:
            batches[collections[kind]] = metadata_doc_builders[kind]()

    if include_regression:
        batches[f"{auxiliary_prefix}_regression_questions"] = _regression_question_docs(metadata_dir / "regression_questions.json")

    if include_sample_data:
        for path in sorted(sample_dir.glob("*.json")):
            batches[f"{auxiliary_prefix}_sample_{path.stem}"] = _sample_row_docs(path)

    return batches


def _normalize_metadata_kinds(values: Any = None) -> list[str]:
    if values in (None, "", []):
        return list(CORE_METADATA_KINDS)
    if isinstance(values, str):
        values = [values]

    requested: list[str] = []
    invalid: list[str] = []
    for value in values:
        for raw_token in str(value or "").replace(";", ",").split(","):
            token = raw_token.strip()
            if not token:
                continue
            normalized = token.lower().replace("-", "_").replace(" ", "_")
            if normalized in {"all", "*"}:
                return list(CORE_METADATA_KINDS)
            kind = METADATA_KIND_ALIASES.get(normalized)
            if not kind:
                invalid.append(token)
                continue
            if kind not in requested:
                requested.append(kind)

    if invalid:
        valid_values = "all, domain, table-catalog, main-flow-filter"
        raise ValueError(f"Invalid --metadata-kind value(s): {', '.join(invalid)}. Valid values: {valid_values}.")
    return requested or list(CORE_METADATA_KINDS)


def _resolve_metadata_collections(
    domain_collection_name: str = "",
    table_catalog_collection_name: str = "",
    main_flow_filter_collection_name: str = "",
    collection_prefix: str = "",
) -> dict[str, str]:
    legacy_prefix = _clean(collection_prefix)
    if domain_collection_name and not table_catalog_collection_name and not main_flow_filter_collection_name and not legacy_prefix:
        if _clean(domain_collection_name) in LEGACY_PREFIXES:
            legacy_prefix = _clean(domain_collection_name)
            domain_collection_name = ""

    if legacy_prefix:
        return {
            "domain_items": _clean(domain_collection_name) or f"{legacy_prefix}_domain_items",
            "table_catalog": _clean(table_catalog_collection_name) or f"{legacy_prefix}_table_catalog_items",
            "main_flow_filters": _clean(main_flow_filter_collection_name) or f"{legacy_prefix}_main_flow_filters",
        }

    return {
        "domain_items": _clean(domain_collection_name) or DEFAULT_DOMAIN_COLLECTION,
        "table_catalog": _clean(table_catalog_collection_name) or DEFAULT_TABLE_CATALOG_COLLECTION,
        "main_flow_filters": _clean(main_flow_filter_collection_name) or DEFAULT_MAIN_FLOW_FILTER_COLLECTION,
    }


def _resolve_auxiliary_prefix(collection_prefix: str, domain_collection_name: str) -> str:
    prefix = _clean(collection_prefix)
    if prefix:
        return prefix
    suffix = "_domain_items"
    collection = _clean(domain_collection_name)
    if collection.endswith(suffix):
        return collection[: -len(suffix)]
    return "agent_v3"


def upload_batches(mongo_uri: str, database: str, batches: dict[str, list[dict[str, Any]]], mode: str) -> None:
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise SystemExit("pymongo is required. Install with: python -m pip install pymongo") from exc

    client = MongoClient(mongo_uri)
    db = client[database]
    for collection_name, docs in batches.items():
        collection = db[collection_name]
        if mode == "replace":
            collection.drop()
        upserted = 0
        modified = 0
        for doc in docs:
            result = collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)
            upserted += 1 if result.upserted_id is not None else 0
            modified += result.modified_count
        print(f"{database}.{collection_name}: docs={len(docs)}, upserted={upserted}, modified={modified}")


def print_upload_plan(batches: dict[str, list[dict[str, Any]]], database: str) -> None:
    print(f"database: {database}")
    for collection_name, docs in batches.items():
        preview_ids = [doc["_id"] for doc in docs[:3]]
        print(f"- {collection_name}: {len(docs)} docs, preview_ids={preview_ids}")


def _domain_item_docs(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    docs: list[dict[str, Any]] = []
    for section in [
        "process_groups",
        "product_terms",
        "quantity_terms",
        "metric_terms",
        "analysis_recipes",
        "pandas_function_cases",
        "status_terms",
    ]:
        for key, payload in data.get(section, {}).items():
            docs.append(_doc(f"domain:{section}:{key}", path, {"section": section, "key": key, "payload": payload}))
    product_key_columns = data.get("product_key_columns", [])
    docs.append(
        _doc(
            "domain:product_key_columns:DEFAULT_PRODUCT_JOIN_KEYS",
            path,
            {
                "section": "product_key_columns",
                "key": "DEFAULT_PRODUCT_JOIN_KEYS",
                "payload": {"columns": product_key_columns, "product_key_columns": product_key_columns},
                "columns": product_key_columns,
            },
        )
    )
    return docs


def _domain_registration_trace_docs(path: Path) -> list[dict[str, Any]]:
    return _metadata_document_export_docs(path, "domain:")


def _metadata_document_export_docs(path: Path, id_prefix: str) -> list[dict[str, Any]]:
    data = _read_json(path)
    if isinstance(data, dict) and isinstance(data.get("documents"), list):
        docs = [_metadata_document_export_doc(item) for item in data["documents"] if isinstance(item, dict)]
        matching_docs = [doc for doc in docs if str(doc.get("_id") or "").startswith(id_prefix)]
        if not matching_docs:
            raise ValueError(f"{path} does not contain {id_prefix} documents.")
        return matching_docs
    if id_prefix == "domain:" and isinstance(data, dict):
        return _domain_item_docs(path)
    raise ValueError(f"{path} must be a metadata document export JSON object.")


def _metadata_document_export_doc(item: dict[str, Any]) -> dict[str, Any]:
    doc = {str(key): _json_ready(value) for key, value in item.items() if str(key) not in {"_class"}}
    doc_id = _clean(doc.pop("_id", "") or doc.pop("id", ""))
    if not doc_id:
        raise ValueError("Metadata document export item is missing id/_id.")
    doc["_id"] = doc_id
    if "registration_trace" not in doc and isinstance(doc.get("authoring_trace"), dict):
        doc["registration_trace"] = doc.pop("authoring_trace")
    else:
        doc.pop("authoring_trace", None)
    doc.setdefault("status", "active")
    return doc


def _table_catalog_docs(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    docs = []
    for dataset_key, payload in data.get("datasets", {}).items():
        docs.append(_doc(f"table_catalog:{dataset_key}", path, {"dataset_key": dataset_key, "key": dataset_key, "payload": payload}))
    return docs


def _main_flow_filter_docs(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    return [_doc(f"main_flow_filter:{key}", path, {"filter_key": key, "key": key, "payload": payload}) for key, payload in data.items()]


def _regression_question_docs(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    return [_doc(f"regression_question:{item['id']}", path, item) for item in data]


def _sample_row_docs(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    docs = []
    for index, row in enumerate(data):
        row_hash = _stable_hash(row)
        docs.append(
            _doc(
                f"sample:{path.stem}:{index}:{row_hash}",
                path,
                {"dataset_key": path.stem, "row_index": index, "row_hash": row_hash, **row},
            )
        )
    return docs


def _doc(doc_id: str, _source_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    doc = {
        "_id": doc_id,
        **payload,
    }
    doc.setdefault("status", "active")
    return doc


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _optional_path(root: Path, value: str) -> Path | None:
    text = _clean(value)
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else root / path


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return str(value)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


if __name__ == "__main__":
    raise SystemExit(main())
