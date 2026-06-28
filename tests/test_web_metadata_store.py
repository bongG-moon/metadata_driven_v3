from __future__ import annotations

import sys
import types
from typing import Any

from web_app.metadata_store import load_metadata_items, mark_metadata_deleted, normalize_metadata_document


class FakeCursor(list):
    def sort(self, fields: list[tuple[str, int]]) -> "FakeCursor":
        key = fields[0][0] if fields else ""
        return FakeCursor(sorted(self, key=lambda item: str(item.get(key) or "")))


class FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def find(self, query: dict[str, Any], projection: dict[str, Any] | None = None) -> FakeCursor:
        if query.get("status"):
            return FakeCursor([doc for doc in self.docs if doc.get("status") == query["status"]])
        return FakeCursor(list(self.docs))

    def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> Any:
        for doc in self.docs:
            if matches_query(doc, query):
                doc.update(update.get("$set", {}))
                return types.SimpleNamespace(matched_count=1, modified_count=1)
        return types.SimpleNamespace(matched_count=0, modified_count=0)


def matches_query(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    if "$or" in query and isinstance(query["$or"], list):
        return any(matches_query(doc, item) for item in query["$or"] if isinstance(item, dict))
    return all(doc.get(key) == value for key, value in query.items())


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


def install_fake_pymongo(monkeypatch: Any, docs: list[dict[str, Any]]) -> FakeClient:
    client = FakeClient(FakeCollection(docs))

    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return client

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))
    return client


def test_load_metadata_items_reads_mongodb_documents(monkeypatch: Any) -> None:
    client = install_fake_pymongo(
        monkeypatch,
        [
            {"section": "process_groups", "key": "WB", "status": "deleted", "payload": {"display_name": "WB"}},
            {"section": "process_groups", "key": "DA", "status": "active", "payload": {"display_name": "DA"}},
        ],
    )

    loaded = load_metadata_items(
        "domain",
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        collection_name="agent_v3_domain_items",
        status="active",
    )

    assert loaded["ok"] is True
    assert [item["key"] for item in loaded["items"]] == ["DA"]
    assert loaded["items"][0]["gbn"] == "process_groups"
    assert client.closed is True


def test_normalize_metadata_document_exposes_domain_registration_trace() -> None:
    item = normalize_metadata_document(
        "domain",
        {
            "section": "analysis_recipes",
            "key": "DEVICE_ALIAS_TO_COLUMN_MAPPING",
            "payload": {"display_name": "DEVICE 첨자"},
            "registration_trace": {
                "raw_text": "DEVICE 첨자 규칙을 등록해줘",
                "refined_text": "DEVICE 컬럼 첨자 해석 규칙",
            },
        },
    )

    assert item["registration_trace"]["raw_text"] == "DEVICE 첨자 규칙을 등록해줘"
    assert item["registration_trace"]["refined_text"] == "DEVICE 컬럼 첨자 해석 규칙"


def test_normalize_metadata_document_accepts_legacy_authoring_trace() -> None:
    item = normalize_metadata_document(
        "domain",
        {
            "section": "analysis_recipes",
            "key": "DEVICE_ALIAS_TO_COLUMN_MAPPING",
            "payload": {"display_name": "DEVICE 첨자"},
            "authoring_trace": {"raw_text": "기존 authoring_trace 원문"},
        },
    )

    assert item["registration_trace"]["raw_text"] == "기존 authoring_trace 원문"


def test_normalize_metadata_document_handles_table_payload() -> None:
    item = normalize_metadata_document(
        "table_catalog",
        {
            "dataset_key": "production_today",
            "registration_trace": {"raw_text": "production_today 데이터셋을 등록해줘"},
            "payload": {
                "display_name": "오늘 생산",
                "dataset_family": "production",
                "source_config": {"source_type": "oracle"},
            },
        },
    )

    assert item["display_name"] == "오늘 생산"
    assert item["dataset_family"] == "production"
    assert item["source_type"] == "oracle"
    assert item["registration_trace"]["raw_text"] == "production_today 데이터셋을 등록해줘"


def test_normalize_metadata_document_handles_main_filter_registration_trace() -> None:
    item = normalize_metadata_document(
        "main_flow_filter",
        {
            "filter_key": "DATE",
            "registration_trace": {"raw_text": "오늘은 DATE 필터로 매핑해줘"},
            "payload": {
                "display_name": "날짜",
                "semantic_role": "date",
                "column_candidates": ["DATE", "WORK_DT"],
            },
        },
    )

    assert item["display_name"] == "날짜"
    assert item["semantic_role"] == "date"
    assert item["registration_trace"]["raw_text"] == "오늘은 DATE 필터로 매핑해줘"


def test_mark_metadata_deleted_updates_status_without_removing_document(monkeypatch: Any) -> None:
    docs = [
        {"section": "process_groups", "key": "DA", "status": "active", "payload": {"display_name": "DA"}},
        {"section": "process_groups", "key": "WB", "status": "active", "payload": {"display_name": "WB"}},
    ]
    client = install_fake_pymongo(monkeypatch, docs)

    result = mark_metadata_deleted(
        "domain",
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        collection_name="agent_v3_domain_items",
        item={"section": "process_groups", "key": "DA"},
    )

    assert result["ok"] is True
    assert docs[0]["status"] == "deleted"
    assert "deleted_at" in docs[0]
    assert docs[1]["status"] == "active"
    assert client.closed is True
