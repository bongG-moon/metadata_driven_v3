from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOMAIN_COLLECTION = "agent_v3_domain_items"
DEFAULT_TABLE_CATALOG_COLLECTION = "agent_v3_table_catalog_items"
DEFAULT_MAIN_FLOW_FILTER_COLLECTION = "agent_v3_main_flow_filters"
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
DOMAIN_SECTIONS = (
    "process_groups",
    "product_terms",
    "quantity_terms",
    "metric_terms",
    "analysis_recipes",
    "pandas_function_cases",
    "status_terms",
)


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Export MongoDB metadata collections into local upload JSON files.")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="Project root containing metadata/.")
    parser.add_argument("--mongo-uri", default=os.getenv("MONGODB_URI"), help="MongoDB URI. Defaults to MONGODB_URI.")
    parser.add_argument("--database", default=os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v3"))
    parser.add_argument("--domain-collection", default=os.getenv("MONGODB_DOMAIN_COLLECTION", DEFAULT_DOMAIN_COLLECTION))
    parser.add_argument(
        "--table-catalog-collection",
        default=os.getenv("MONGODB_TABLE_CATALOG_COLLECTION", DEFAULT_TABLE_CATALOG_COLLECTION),
    )
    parser.add_argument(
        "--main-flow-filter-collection",
        default=os.getenv("MONGODB_MAIN_FLOW_FILTER_COLLECTION", DEFAULT_MAIN_FLOW_FILTER_COLLECTION),
    )
    parser.add_argument(
        "--metadata-kind",
        "--kind",
        action="append",
        default=[],
        help=(
            "Metadata kind to export. Repeat or comma-separate values. "
            "Values: all, domain, table-catalog, main-flow-filter. Default exports all core metadata."
        ),
    )
    parser.add_argument("--no-backup", action="store_true", help="Do not create timestamped backups before overwriting files.")
    args = parser.parse_args()

    if not args.mongo_uri:
        print("Missing --mongo-uri or MONGODB_URI.", file=sys.stderr)
        return 2

    try:
        metadata_kinds = _normalize_metadata_kinds(args.metadata_kind)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise SystemExit("pymongo is required. Install with: python -m pip install pymongo") from exc

    root = Path(args.root).resolve()
    metadata_dir = root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    client = MongoClient(args.mongo_uri)
    db = client[args.database]
    collection_names = {
        "domain_items": args.domain_collection,
        "table_catalog": args.table_catalog_collection,
        "main_flow_filters": args.main_flow_filter_collection,
    }

    outputs: dict[str, Path] = {}
    if "domain_items" in metadata_kinds:
        docs = list(_active_docs(db[collection_names["domain_items"]]))
        domain_json = _domain_json_from_docs(docs)
        path = metadata_dir / "domain_items.json"
        _write_json(path, domain_json, backup=not args.no_backup)
        outputs["domain_items"] = path
        print(
            f"exported domain_items: docs={len(docs)}, "
            f"sections={_domain_counts(domain_json)}, path={path}"
        )

    if "table_catalog" in metadata_kinds:
        docs = list(_active_docs(db[collection_names["table_catalog"]]))
        table_catalog_json = _table_catalog_json_from_docs(docs)
        path = metadata_dir / "table_catalog.json"
        _write_json(path, table_catalog_json, backup=not args.no_backup)
        outputs["table_catalog"] = path
        print(f"exported table_catalog: docs={len(docs)}, datasets={len(table_catalog_json['datasets'])}, path={path}")

    if "main_flow_filters" in metadata_kinds:
        docs = list(_active_docs(db[collection_names["main_flow_filters"]]))
        main_flow_filter_json = _main_flow_filter_json_from_docs(docs)
        path = metadata_dir / "main_flow_filters.json"
        _write_json(path, main_flow_filter_json, backup=not args.no_backup)
        outputs["main_flow_filters"] = path
        print(f"exported main_flow_filters: docs={len(docs)}, filters={len(main_flow_filter_json)}, path={path}")

    if not outputs:
        print("No metadata exported.")
    return 0


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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


def _active_docs(collection: Any) -> list[dict[str, Any]]:
    return list(collection.find({"status": {"$ne": "deleted"}}, {"_id": 0}).sort([("section", 1), ("key", 1)]))


def _domain_json_from_docs(docs: list[dict[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {section: {} for section in DOMAIN_SECTIONS}
    data["product_key_columns"] = []
    for doc in docs:
        section = str(doc.get("section") or "").strip()
        key = str(doc.get("key") or "").strip()
        if not section:
            continue
        if section == "product_key_columns":
            data["product_key_columns"] = _as_string_list(doc.get("columns") or doc.get("payload"))
            continue
        if section not in DOMAIN_SECTIONS or not key:
            continue
        payload = doc.get("payload")
        if isinstance(payload, dict):
            data[section][key] = _strip_mongo_values(payload)
    return data


def _table_catalog_json_from_docs(docs: list[dict[str, Any]]) -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    for doc in docs:
        key = str(doc.get("dataset_key") or doc.get("key") or "").strip()
        payload = doc.get("payload")
        if key and isinstance(payload, dict):
            datasets[key] = _strip_mongo_values(payload)
    return {"datasets": datasets}


def _main_flow_filter_json_from_docs(docs: list[dict[str, Any]]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for doc in docs:
        key = str(doc.get("filter_key") or doc.get("key") or "").strip()
        payload = doc.get("payload")
        if key and isinstance(payload, dict):
            filters[key] = _strip_mongo_values(payload)
    return filters


def _strip_mongo_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _strip_mongo_values(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, list):
        return [_strip_mongo_values(item) for item in value]
    return value


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, dict):
        return _as_string_list(value.get("columns"))
    return []


def _write_json(path: Path, data: Any, backup: bool) -> None:
    if backup and path.exists():
        backup_path = path.with_name(f"{path.stem}.before_mongodb_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}")
        shutil.copy2(path, backup_path)
        print(f"backup: {backup_path}")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _domain_counts(domain_json: dict[str, Any]) -> dict[str, int]:
    counts = {section: len(domain_json.get(section, {})) for section in DOMAIN_SECTIONS}
    counts["product_key_columns"] = len(domain_json.get("product_key_columns", []))
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
