from __future__ import annotations

import sys
import types
from typing import Any

from web_app.data_ref_store import load_data_ref_rows, rows_from_data_ref_document


class FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if "ref_id" in query:
            return self.docs.get(str(query["ref_id"]))
        if "_id" in query:
            return self.docs.get(str(query["_id"]))
        if "data_ref_id" in query:
            return self.docs.get(str(query["data_ref_id"]))
        return None


class FakeDatabase:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collection


class FakeClient:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection
        self.closed = False

    def __getitem__(self, name: str) -> FakeDatabase:
        return FakeDatabase(self.collection)

    def close(self) -> None:
        self.closed = True


def install_fake_pymongo(monkeypatch: Any, collection: FakeCollection) -> FakeClient:
    client = FakeClient(collection)

    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return client

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))
    return client


def test_rows_from_data_ref_document_extracts_nested_rows() -> None:
    document = {
        "data": {"rows": [{"MODE": "A", "WIP": 10}, {"MODE": "B", "WIP": 20}]},
        "row_count": 2,
    }

    loaded = rows_from_data_ref_document(document)

    assert loaded["ok"] is True
    assert loaded["rows"] == [{"MODE": "A", "WIP": 10}, {"MODE": "B", "WIP": 20}]
    assert loaded["columns"] == ["MODE", "WIP"]
    assert loaded["row_count"] == 2


def test_load_data_ref_rows_uses_ref_database_and_collection(monkeypatch: Any) -> None:
    collection = FakeCollection()
    collection.docs["source-ref"] = {
        "ref_id": "source-ref",
        "columns": ["PRODUCT", "PRODUCTION"],
        "rows": [{"PRODUCT": "A", "PRODUCTION": 100}, {"PRODUCT": "B", "PRODUCTION": 200}],
        "row_count": 2,
    }
    client = install_fake_pymongo(monkeypatch, collection)

    loaded = load_data_ref_rows(
        {
            "store": "mongodb",
            "ref_id": "source-ref",
            "database": "metadata_driven_agent_v3",
            "collection_name": "agent_v3_result_store",
        },
        mongo_uri="mongodb://fake",
        limit=1,
    )

    assert loaded["rows"] == [{"PRODUCT": "A", "PRODUCTION": 100}]
    assert loaded["columns"] == ["PRODUCT", "PRODUCTION"]
    assert loaded["row_count"] == 2
    assert loaded["collection_name"] == "agent_v3_result_store"
    assert client.closed is True
