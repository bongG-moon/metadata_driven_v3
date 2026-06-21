from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def test_metadata_loader_assembles_uploaded_mongodb_docs() -> None:
    module = _load_metadata_loader()

    metadata = module._assemble_metadata_from_mongo_docs(
        [
            {
                "_id": "domain:process_groups:DA",
                "section": "process_groups",
                "key": "DA",
                "payload": {"display_name": "D/A", "processes": ["D/A1"]},
            },
            {
                "_id": "domain:product_key_columns",
                "section": "product_key_columns",
                "key": "product_key_columns",
                "columns": ["TECH", "MODE"],
            },
        ],
        [
            {
                "_id": "table_catalog:production_today",
                "dataset_key": "production_today",
                "payload": {"source_type": "oracle", "columns": ["TECH", "MODE", "PRODUCTION"]},
            }
        ],
        [
            {
                "_id": "main_flow_filter:OPER_NAME",
                "filter_key": "OPER_NAME",
                "payload": {"column_candidates": ["OPER_NAME"]},
            }
        ],
    )

    assert metadata["domain_items"]["process_groups"]["DA"]["processes"] == ["D/A1"]
    assert metadata["domain_items"]["product_key_columns"] == ["TECH", "MODE"]
    assert metadata["table_catalog"]["datasets"]["production_today"]["source_type"] == "oracle"
    assert metadata["main_flow_filters"]["OPER_NAME"]["column_candidates"] == ["OPER_NAME"]


def test_metadata_loader_loads_only_from_mongodb(monkeypatch: Any) -> None:
    module = _load_metadata_loader()
    install_fake_pymongo(
        monkeypatch,
        {
            "factory_domain_metadata": [
                {
                    "_id": "domain:product_key_columns",
                    "section": "product_key_columns",
                    "key": "product_key_columns",
                    "columns": ["TECH", "MODE"],
                }
            ],
            "factory_table_catalog_metadata": [
                {
                    "_id": "table_catalog:wip_today",
                    "dataset_key": "wip_today",
                    "payload": {"source_type": "oracle", "columns": ["TECH", "MODE", "WIP"]},
                }
            ],
            "factory_filter_metadata": [
                {
                    "_id": "main_flow_filter:DATE",
                    "filter_key": "DATE",
                    "payload": {"column_candidates": ["WORK_DT"]},
                }
            ],
        },
    )

    payload = module.load_metadata_payload(
        {"request": {"question": "q"}, "warnings": []},
        mongo_uri="mongodb://fake",
        domain_collection_name="factory_domain_metadata",
        table_catalog_collection_name="factory_table_catalog_metadata",
        main_flow_filter_collection_name="factory_filter_metadata",
    )

    assert payload["metadata"]["domain_items"]["product_key_columns"] == ["TECH", "MODE"]
    assert payload["metadata"]["table_catalog"]["datasets"]["wip_today"]["source_type"] == "oracle"
    assert payload["metadata"]["main_flow_filters"]["DATE"]["column_candidates"] == ["WORK_DT"]
    load_info = payload["metadata_context"]["metadata_load"]
    assert load_info["source"] == "mongodb"
    assert load_info["collections"] == {
        "domain_items": "factory_domain_metadata",
        "table_catalog": "factory_table_catalog_metadata",
        "main_flow_filters": "factory_filter_metadata",
    }
    assert "fallback_from" not in load_info


class FakeCursor(list):
    def limit(self, value: int) -> "FakeCursor":
        return FakeCursor(self[:value])


class FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def find(self, query: dict[str, Any]) -> FakeCursor:
        return FakeCursor(self.docs)


class FakeDatabase:
    def __init__(self, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
        self.docs_by_collection = docs_by_collection

    def __getitem__(self, collection_name: str) -> FakeCollection:
        return FakeCollection(self.docs_by_collection.get(collection_name, []))


class FakeClient:
    def __init__(self, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
        self.docs_by_collection = docs_by_collection

    def __getitem__(self, database_name: str) -> FakeDatabase:
        return FakeDatabase(self.docs_by_collection)

    def close(self) -> None:
        return None


def install_fake_pymongo(monkeypatch: Any, docs_by_collection: dict[str, list[dict[str, Any]]]) -> None:
    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return FakeClient(docs_by_collection)

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))


def _load_metadata_loader():
    path = ROOT / "langflow_components" / "data_analysis_flow" / "01_metadata_context_loader.py"
    spec = importlib.util.spec_from_file_location("metadata_context_loader", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
