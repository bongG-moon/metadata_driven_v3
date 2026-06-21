from __future__ import annotations

import importlib.util
import sys
import types
from copy import deepcopy
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

    def replace_one(self, query: dict[str, Any], doc: dict[str, Any], upsert: bool = False) -> None:
        self.docs[str(query["ref_id"])] = doc

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return self.docs.get(str(query["ref_id"]))


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


class MultiFakeCollection(FakeCollection):
    def __init__(self, name: str, database: "MultiFakeDatabase") -> None:
        super().__init__()
        self.name = name
        self.database = database


class MultiFakeDatabase:
    def __init__(self, name: str, client: "MultiFakeClient") -> None:
        self.name = name
        self.client = client
        self.collections: dict[str, MultiFakeCollection] = {}

    def __getitem__(self, name: str) -> MultiFakeCollection:
        if name not in self.collections:
            self.collections[name] = MultiFakeCollection(name, self)
        return self.collections[name]


class MultiFakeClient:
    def __init__(self) -> None:
        self.databases: dict[str, MultiFakeDatabase] = {}
        self.closed = False

    def __getitem__(self, name: str) -> MultiFakeDatabase:
        if name not in self.databases:
            self.databases[name] = MultiFakeDatabase(name, self)
        return self.databases[name]

    def close(self) -> None:
        self.closed = True


def install_fake_pymongo(monkeypatch: Any, collection: FakeCollection) -> None:
    client = FakeClient(collection)

    def mongo_client(*args: Any, **kwargs: Any) -> FakeClient:
        return client

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))


def install_multi_fake_pymongo(monkeypatch: Any, client: MultiFakeClient) -> None:
    def mongo_client(*args: Any, **kwargs: Any) -> MultiFakeClient:
        return client

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=mongo_client))


def test_mongodb_store_compacts_runtime_sources_and_loader_keeps_preview_by_default(monkeypatch: Any) -> None:
    store = load_component("langflow_components/data_analysis_flow/17_mongodb_data_store.py")
    loader = load_component("langflow_components/data_analysis_flow/05_mongodb_data_loader.py")
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    rows = [{"PRODUCT": "A", "WIP": 10}, {"PRODUCT": "B", "WIP": 20}]
    payload = {
        "request": {"session_id": "session-1"},
        "runtime_sources": {"wip_total": rows},
        "source_results": [
            {
                "source_alias": "wip_total",
                "dataset_key": "wip_today",
                "source_type": "oracle",
                "row_count": 2,
                "columns": ["PRODUCT", "WIP"],
                "preview_rows": rows[:1],
                "data_ref": "source://oracle/wip_today/wip_total",
            }
        ],
    }

    stored = store.store_payload_in_mongodb(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
        preview_row_limit="1",
        min_rows="1",
    )

    assert stored["mongo_data_store"]["stored"] is True
    assert stored["runtime_sources"]["wip_total"] == rows[:1]
    data_ref = stored["runtime_source_refs"]["wip_total"]
    assert data_ref["store"] == "mongodb"
    assert data_ref["collection_name"] == "agent_v3_result_store"
    assert stored["source_results"][0]["data_ref"]["ref_id"] == data_ref["ref_id"]
    assert collection.docs[data_ref["ref_id"]]["rows"] == rows

    restored = loader.load_payload_from_mongodb(
        stored,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
    )

    assert restored["runtime_sources"]["wip_total"] == rows[:1]
    assert restored["runtime_sources_are_preview"] is True
    assert restored["mongo_data_load"]["restore_mode"] == "preview"
    assert restored["mongo_data_load"]["loaded"] is False

    full = loader.load_payload_from_mongodb(
        stored,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
        restore_mode="full",
    )

    assert full["runtime_sources"]["wip_total"] == rows
    assert full["runtime_sources_are_preview"] is False
    assert full["mongo_data_load"]["loaded"] is True


def test_mongodb_store_compacts_final_data_and_loader_restores_preview_then_full(monkeypatch: Any) -> None:
    store = load_component("langflow_components/data_analysis_flow/17_mongodb_data_store.py")
    loader = load_component("langflow_components/data_analysis_flow/05_mongodb_data_loader.py")
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    rows = [{"MODE": "LPDDR5", "WIP": 10}, {"MODE": "HBM", "WIP": 20}]
    payload = {
        "request": {"session_id": "session-1"},
        "data": {"columns": ["MODE", "WIP"], "rows": rows, "row_count": 2},
        "state": {"current_data": {"columns": ["MODE", "WIP"], "rows": rows, "row_count": 2}},
    }

    stored = store.store_payload_in_mongodb(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
        preview_row_limit="1",
        min_rows="1",
    )

    assert stored["data"]["rows"] == rows[:1]
    assert stored["data"]["data_ref"]["store"] == "mongodb"
    assert stored["state"]["current_data"]["rows"] == rows[:1]
    assert stored["state"]["current_data"]["data_ref"]["store"] == "mongodb"

    restored = loader.load_payload_from_mongodb(
        stored,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
    )

    assert restored["data"]["rows"] == rows[:1]
    assert restored["data"]["data_ref_loaded"] is False
    assert restored["data"]["data_ref_load_mode"] == "preview"
    assert restored["state"]["current_data"]["rows"] == rows[:1]
    assert restored["state"]["current_data"]["data_ref_loaded"] is False

    full = loader.load_payload_from_mongodb(
        stored,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
        restore_mode="full",
    )

    assert full["data"]["rows"] == rows
    assert full["state"]["current_data"]["rows"] == rows
    assert full["state"]["current_data"]["data_ref_loaded"] is True

    auto_payload = deepcopy(stored)
    auto_payload["intent_plan"] = {"requires_full_previous_result_restore": True}
    auto = loader.load_payload_from_mongodb(
        auto_payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
        restore_mode="auto",
    )

    assert auto["mongo_data_load"]["requested_restore_mode"] == "auto"
    assert auto["mongo_data_load"]["restore_mode"] == "full"
    assert auto["state"]["current_data"]["rows"] == rows


def test_mongodb_store_after_pandas_compacts_source_and_analysis_rows(monkeypatch: Any) -> None:
    store = load_component("langflow_components/data_analysis_flow/17_mongodb_data_store.py")
    collection = FakeCollection()
    install_fake_pymongo(monkeypatch, collection)
    source_rows = [{"MODE": "LPDDR5", "WIP": 10}, {"MODE": "HBM", "WIP": 20}]
    result_rows = [{"MODE": "LPDDR5", "WIP": 10}, {"MODE": "HBM", "WIP": 20}]
    payload = {
        "request": {"session_id": "session-1"},
        "runtime_sources": {"wip_data": source_rows},
        "source_results": [
            {
                "source_alias": "wip_data",
                "dataset_key": "wip_today",
                "source_type": "oracle",
                "row_count": 2,
                "columns": ["MODE", "WIP"],
            }
        ],
        "analysis": {
            "status": "ok",
            "columns": ["MODE", "WIP"],
            "rows": result_rows,
            "row_count": 2,
            "product_key_columns": ["MODE"],
            "product_key_values": [{"MODE": "LPDDR5"}, {"MODE": "HBM"}],
            "product_key_count": 2,
            "errors": [],
        },
    }

    stored = store.store_payload_in_mongodb(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
        preview_row_limit="1",
        min_rows="1",
    )

    assert stored["mongo_data_store"]["stored"] is True
    assert stored["runtime_sources"]["wip_data"] == source_rows[:1]
    assert stored["analysis"]["rows"] == result_rows[:1]
    assert stored["analysis"]["data_ref"]["store"] == "mongodb"
    assert stored["source_results"][0]["data_ref"]["store"] == "mongodb"
    assert len(stored["data_refs"]) == 2
    assert collection.docs[stored["runtime_source_refs"]["wip_data"]["ref_id"]]["rows"] == source_rows
    assert collection.docs[stored["analysis"]["data_ref"]["ref_id"]]["rows"] == result_rows


def test_mongodb_loader_restores_followup_source_results_when_full_requested(monkeypatch: Any) -> None:
    source_rows = [{"MODE": "LPDDR5", "WIP": 10}, {"MODE": "HBM", "WIP": 20}]
    source_ref = {
        "store": "mongodb",
        "ref_id": "source-ref",
        "collection_name": "agent_v3_result_store",
        "row_count": 2,
        "columns": ["MODE", "WIP"],
    }

    for loader_path in [
        "langflow_components/data_analysis_flow/05_mongodb_data_loader.py",
        "langflow_components/data_analysis_flow/05_mongodb_data_loader.py",
    ]:
        loader = load_component(loader_path)
        collection = FakeCollection()
        collection.docs["source-ref"] = {
            "ref_id": "source-ref",
            "rows": source_rows,
            "row_count": 2,
            "columns": ["MODE", "WIP"],
        }
        install_fake_pymongo(monkeypatch, collection)
        payload = {
            "intent_plan": {"requires_full_previous_result_restore": True},
            "state": {
                "followup_source_results": [
                    {
                        "source_alias": "wip_data",
                        "dataset_key": "wip_today",
                        "data_ref": source_ref,
                        "row_count": 2,
                        "columns": ["MODE", "WIP"],
                    }
                ]
            },
        }

        restored = loader.load_payload_from_mongodb(
            payload,
            mongo_uri="mongodb://fake",
            mongo_database="metadata_driven_agent_v3",
            result_collection_name="agent_v3_result_store",
            restore_mode="auto",
        )

        assert restored["mongo_data_load"]["restore_mode"] == "full"
        assert restored["runtime_sources"]["wip_data"] == source_rows
        assert restored["runtime_source_refs"]["wip_data"]["ref_id"] == "source-ref"
        assert restored["runtime_sources_are_preview"] is False
        assert any(item.get("source") == "followup_source_results" for item in restored["mongo_data_load"]["loaded_refs"])


def test_mongodb_loader_uses_collection_name_from_data_ref(monkeypatch: Any) -> None:
    loader = load_component("langflow_components/data_analysis_flow/05_mongodb_data_loader.py")
    client = MultiFakeClient()
    default_collection = client["metadata_driven_agent_v3"]["agent_v3_result_store"]
    custom_collection = client["metadata_driven_agent_v3"]["custom_result_store"]
    default_collection.docs = {}
    custom_collection.docs["source-ref"] = {
        "ref_id": "source-ref",
        "rows": [{"MODE": "A", "WIP": 10}],
        "row_count": 1,
        "columns": ["MODE", "WIP"],
    }
    install_multi_fake_pymongo(monkeypatch, client)
    payload = {
        "intent_plan": {"requires_full_previous_result_restore": True},
        "state": {
            "followup_source_results": [
                {
                    "source_alias": "wip_data",
                    "data_ref": {
                        "store": "mongodb",
                        "ref_id": "source-ref",
                        "database": "metadata_driven_agent_v3",
                        "collection_name": "custom_result_store",
                    },
                }
            ]
        },
    }

    restored = loader.load_payload_from_mongodb(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        result_collection_name="agent_v3_result_store",
        restore_mode="auto",
    )

    assert restored["runtime_sources"]["wip_data"] == [{"MODE": "A", "WIP": 10}]
    assert restored["mongo_data_load"]["loaded"] is True


def test_answer_response_state_keeps_product_key_summary_without_full_restore() -> None:
    answer_builder = load_component("langflow_components/data_analysis_flow/19_answer_response_builder.py")
    payload = {
        "request": {"session_id": "session-1", "question": "previous products"},
        "intent_plan": {"intent_type": "multi_step_analysis", "analysis_kind": "rank_wip_then_join_production", "product_grain": ["MODE"]},
        "analysis": {
            "columns": ["MODE", "WIP"],
            "rows": [{"MODE": "LPDDR5", "WIP": 10}],
            "row_count": 2,
            "data_ref": {"store": "mongodb", "ref_id": "result-ref", "collection_name": "agent_v3_result_store"},
            "data_is_reference": True,
            "data_is_preview": True,
            "product_key_columns": ["MODE"],
            "product_key_values": [{"MODE": "LPDDR5"}, {"MODE": "HBM"}],
            "product_key_count": 2,
        },
        "source_results": [],
        "state": {},
    }

    result = answer_builder.build_answer_response_payload(payload, '{"answer_message":"ok"}')

    assert result["state"]["current_data"]["product_key_columns"] == ["MODE"]
    assert result["state"]["current_data"]["product_key_values"] == [{"MODE": "LPDDR5"}, {"MODE": "HBM"}]
    assert result["state"]["current_data"]["product_key_count"] == 2
    assert result["data"]["data_ref"]["ref_id"] == "result-ref"
    assert result["state"]["current_data"]["data_ref"]["ref_id"] == "result-ref"


def test_answer_response_state_preserves_followup_source_refs() -> None:
    source_ref = {"store": "mongodb", "ref_id": "source-ref", "collection_name": "agent_v3_result_store"}
    for builder_path in [
        "langflow_components/data_analysis_flow/19_answer_response_builder.py",
        "langflow_components/data_analysis_flow/19_answer_response_builder.py",
    ]:
        answer_builder = load_component(builder_path)
        payload = {
            "request": {"session_id": "session-1", "question": "show result"},
            "analysis": {"columns": ["MODE"], "rows": [{"MODE": "A"}], "row_count": 1},
            "runtime_source_refs": {"wip_data": source_ref},
            "source_results": [
                {
                    "source_alias": "wip_data",
                    "dataset_key": "wip_today",
                    "source_type": "oracle",
                    "columns": ["MODE", "WIP"],
                    "row_count": 100,
                    "data_ref": source_ref,
                    "data_is_reference": True,
                    "data_is_preview": True,
                }
            ],
            "state": {},
        }

        result = answer_builder.build_answer_response_payload(payload, '{"answer_message":"ok"}')

        assert result["state"]["runtime_source_refs"]["wip_data"]["ref_id"] == "source-ref"
        source_state = result["state"]["followup_source_results"][0]
        assert source_state["source_alias"] == "wip_data"
        assert source_state["columns"] == ["MODE", "WIP"]
        assert source_state["data_ref"]["ref_id"] == "source-ref"


def test_request_state_loader_compacts_previous_current_data_without_mongodb_loader() -> None:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    rows = [{"MODE": f"P{i}", "WIP": i} for i in range(8)]
    previous_state = {
        "chat_history": [{"role": "assistant", "content": "previous"}],
        "context": {"last_analysis_kind": "rank_top_n"},
        "current_data": {
            "columns": ["MODE", "WIP"],
            "rows": rows,
            "row_count": 8,
            "data_ref": {"store": "mongodb", "ref_id": "result-ref"},
            "source_dataset_keys": ["wip_today"],
            "source_aliases": ["wip_data"],
            "product_key_columns": ["MODE"],
        },
    }

    payload = request_loader.build_request_payload("follow-up", "session-1", previous_state)
    current_data = payload["state"]["current_data"]

    assert current_data["rows"] == rows[:5]
    assert current_data["row_count"] == 8
    assert current_data["data_is_preview"] is True
    assert current_data["data_ref"]["ref_id"] == "result-ref"
    assert current_data["product_key_values"] == [{"MODE": f"P{i}"} for i in range(8)]
    assert current_data["product_key_count"] == 8
    assert current_data["source_dataset_keys"] == ["wip_today"]
