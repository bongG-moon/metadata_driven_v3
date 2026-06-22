from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOMAIN_COLLECTION = "agent_v3_domain_items"
DEFAULT_TABLE_CATALOG_COLLECTION = "agent_v3_table_catalog_items"
DEFAULT_MAIN_FLOW_FILTER_COLLECTION = "agent_v3_main_flow_filters"
LEGACY_PREFIXES = {"agent_v1", "agent_v2", "agent_v3", "agent_v4"}


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
    parser.add_argument("--dry-run", action="store_true", help="Print upload plan without connecting to MongoDB.")
    parser.add_argument(
        "--mode",
        choices=["upsert", "replace"],
        default="upsert",
        help="upsert updates by deterministic _id. replace drops target collections before inserting.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    batches = build_upload_batches(
        root,
        domain_collection_name=args.domain_collection,
        table_catalog_collection_name=args.table_catalog_collection,
        main_flow_filter_collection_name=args.main_flow_filter_collection,
        include_regression=args.include_regression,
        include_sample_data=args.include_sample_data,
        collection_prefix=args.collection_prefix,
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

    batches: dict[str, list[dict[str, Any]]] = {
        collections["domain_items"]: _domain_item_docs(metadata_dir / "domain_items.json"),
        collections["table_catalog"]: _table_catalog_docs(metadata_dir / "table_catalog.json"),
        collections["main_flow_filters"]: _main_flow_filter_docs(metadata_dir / "main_flow_filters.json"),
    }

    if include_regression:
        batches[f"{auxiliary_prefix}_regression_questions"] = _regression_question_docs(metadata_dir / "regression_questions.json")

    if include_sample_data:
        for path in sorted(sample_dir.glob("*.json")):
            batches[f"{auxiliary_prefix}_sample_{path.stem}"] = _sample_row_docs(path)

    return batches


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
    for section in ["process_groups", "product_terms", "quantity_terms", "metric_terms", "analysis_recipes", "status_terms"]:
        for key, payload in data.get(section, {}).items():
            docs.append(_doc(f"domain:{section}:{key}", path, {"section": section, "key": key, "payload": payload}))
    docs.append(
        _doc(
            "domain:product_key_columns",
            path,
            {"section": "product_key_columns", "key": "product_key_columns", "columns": data.get("product_key_columns", [])},
        )
    )
    return docs


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


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]


if __name__ == "__main__":
    raise SystemExit(main())
