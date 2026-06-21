from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_component(path: str):
    component_path = ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        if "_id" in query:
            return self.docs.get(str(query["_id"]))
        if "session_id" in query:
            for doc in self.docs.values():
                if doc.get("session_id") == query["session_id"]:
                    return doc
        return None

    def replace_one(self, query: dict[str, Any], doc: dict[str, Any], upsert: bool = False) -> None:
        self.docs[str(query["_id"])] = doc


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


def install_fake_pymongo(monkeypatch: Any, collection: FakeCollection) -> None:
    client = FakeClient(collection)

    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return client

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))


def test_session_state_writer_saves_compact_state_and_loader_reads_it(monkeypatch: Any) -> None:
    writer = load_component("langflow_components/session_state_flow/01_mongodb_session_state_writer.py")
    loader = load_component("langflow_components/session_state_flow/00_mongodb_session_state_loader.py")
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    rows = [{"MODE": f"M{i}", "WIP": i} for i in range(6)]
    payload = {
        "request": {"session_id": "s1", "question": "first"},
        "response_type": "analysis",
        "state": {
            "chat_history": [{"role": "user", "content": str(i)} for i in range(12)],
            "context": {"last_analysis_kind": "rank_top_n"},
            "runtime_sources": {"wip_data": rows},
            "current_data": {
                "columns": ["MODE", "WIP"],
                "rows": rows,
                "row_count": len(rows),
                "data_ref": {"store": "mongodb", "ref_id": "result-ref"},
                "product_key_columns": ["MODE"],
            },
            "followup_source_results": [
                {
                    "source_alias": "wip_data",
                    "dataset_key": "wip_today",
                    "columns": ["MODE", "WIP"],
                    "row_count": len(rows),
                    "data_ref": {"store": "mongodb", "ref_id": "source-ref"},
                }
            ],
        },
    }

    saved = writer.write_session_state_payload(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        session_collection_name="agent_v3_session_states",
        preview_row_limit="2",
        history_limit="3",
    )

    assert saved["session_state_write"]["saved"] is True
    doc = collection.docs["session_state:s1"]
    state = doc["state"]
    assert "runtime_sources" not in state
    assert len(state["chat_history"]) == 3
    assert state["current_data"]["rows"] == rows[:2]
    assert state["current_data"]["data_ref"]["ref_id"] == "result-ref"
    assert state["current_data"]["data_is_preview"] is True
    assert state["current_data"]["product_key_values"] == [{"MODE": "M0"}, {"MODE": "M1"}]
    assert state["followup_source_results"][0]["data_ref"]["ref_id"] == "source-ref"

    loaded = loader.load_session_state_payload(
        "next",
        "s1",
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        session_collection_name="agent_v3_session_states",
        preview_row_limit="2",
    )

    assert loaded["session_state_load"]["loaded"] is True
    assert loaded["session_state_load"]["source"] == "mongodb"
    assert loaded["state"]["current_data"]["data_ref"]["ref_id"] == "result-ref"
    assert loaded["request"]["question"] == "next"


def test_session_state_loader_prefers_explicit_state_over_mongodb(monkeypatch: Any) -> None:
    loader = load_component("langflow_components/session_state_flow/00_mongodb_session_state_loader.py")
    collection = FakeCollection()
    collection.docs["session_state:s1"] = {
        "_id": "session_state:s1",
        "session_id": "s1",
        "state": {"current_data": {"rows": [{"MODE": "OLD"}], "row_count": 1}},
    }
    install_fake_pymongo(monkeypatch, collection)

    loaded = loader.load_session_state_payload(
        "next",
        "s1",
        state={"current_data": {"rows": [{"MODE": "NEW"}], "row_count": 1}},
        mongo_uri="mongodb://fake",
    )

    assert loaded["session_state_load"]["source"] == "input_state"
    assert loaded["session_state_load"]["loaded"] is False
    assert loaded["state"]["current_data"]["rows"] == [{"MODE": "NEW"}]


def test_session_state_loader_component_hides_explicit_state_input() -> None:
    loader = load_component("langflow_components/session_state_flow/00_mongodb_session_state_loader.py")

    input_names = [item.name for item in loader.MongoDBSessionStateLoader.inputs]
    display_names = [item.display_name for item in loader.MongoDBSessionStateLoader.inputs]

    assert "state" not in input_names
    assert "Explicit State" not in display_names


def test_session_state_writer_accepts_api_response_wrapper(monkeypatch: Any) -> None:
    writer = load_component("langflow_components/session_state_flow/01_mongodb_session_state_writer.py")
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    payload = {
        "api_response": {
            "response_type": "metadata_qa",
            "state": {"context": {"last_route": "metadata_qa"}, "current_data": {}},
        }
    }

    saved = writer.write_session_state_payload(payload, session_id="wrapped", mongo_uri="mongodb://fake")

    assert saved["session_state_write"]["saved"] is True
    assert collection.docs["session_state:wrapped"]["state"]["context"]["last_route"] == "metadata_qa"
