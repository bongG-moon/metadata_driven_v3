from __future__ import annotations

import importlib.util
import json
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


def test_metadata_qa_lists_catalog_without_expanding_examples(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_prompt_builder = load_component("langflow_components/router_flow/03_route_classifier_prompt_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")
    api_builder = load_component("langflow_components/data_analysis_flow/21_api_response_builder.py")

    payload = seed_payload("현재 조회 가능한 DATA LIST를 알려줄래?", monkeypatch)
    routed = router.route_metadata_question(payload)
    prompt_payload = route_prompt_builder.build_route_classifier_prompt_payload(routed)
    routed = classify_route(route_normalizer, routed, metadata_action="catalog_list")
    result = response_builder.build_metadata_qa_response(routed)
    api_response = api_builder.build_main_flow_api_response(result)["api_response"]

    assert routed["metadata_route"]["route"] == "metadata_qa"
    assert routed["metadata_route"]["metadata_action"] == "catalog_list"
    assert routed["metadata_route"]["route_llm_required"] is True
    assert routed["metadata_route"]["route_llm_used"] is True
    assert prompt_payload["prompt_type"] == "route_classifier"
    assert result["direct_response_ready"] is True
    assert result["metadata_qa"]["route_source"] == "llm"
    assert result["data"]["row_count"] >= 5
    assert "production_today" in {row["DATASET_KEY"] for row in result["data"]["rows"]}
    assert "활용 예시 알려줘" in result["answer_message"]
    assert "오늘 DA공정 생산량을 제품별로 보여줘" not in result["answer_message"]
    assert api_response["success"] is True
    assert api_response["intent"]["analysis_kind"] == "catalog_list"


def test_metadata_qa_shows_examples_for_requested_dataset(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")

    payload = seed_payload("production_today 활용 예시 알려줘", monkeypatch)
    routed = classify_route(route_normalizer, router.route_metadata_question(payload), metadata_action="dataset_examples", target_dataset="production_today")
    result = response_builder.build_metadata_qa_response(routed)

    assert result["metadata_qa"]["metadata_action"] == "dataset_examples"
    assert result["metadata_qa"]["target_dataset"] == "production_today"
    assert result["data"]["row_count"] >= 3
    assert all(row["DATASET_KEY"] == "production_today" for row in result["data"]["rows"])
    assert "production_today 활용 예시" in result["answer_message"]


def test_metadata_qa_returns_registered_query_template(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")

    payload = seed_payload("production_today 조회 쿼리문 알려줘", monkeypatch)
    routed = classify_route(route_normalizer, router.route_metadata_question(payload), metadata_action="dataset_query", target_dataset="production_today")
    result = response_builder.build_metadata_qa_response(routed)

    assert result["metadata_qa"]["metadata_action"] == "dataset_query"
    assert "```sql" in result["answer_message"]
    assert "FROM PRODUCTION_TODAY" in result["answer_message"]
    assert result["data"]["rows"][0]["DB_KEY"] == "PNT_RPT"


def test_metadata_qa_maps_natural_quantity_term_to_dataset_query(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_prompt_builder = load_component("langflow_components/router_flow/03_route_classifier_prompt_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")

    payload = seed_payload("생산량 데이터를 조회하는 쿼리를 알려줘", monkeypatch)
    routed = router.route_metadata_question(payload)
    prompt_payload = route_prompt_builder.build_route_classifier_prompt_payload(routed)
    routed = classify_route(route_normalizer, routed, metadata_action="dataset_query")
    result = response_builder.build_metadata_qa_response(routed)

    assert routed["metadata_route"]["route"] == "metadata_qa"
    assert routed["metadata_route"]["metadata_action"] == "dataset_query"
    assert routed["metadata_route"]["target_dataset"] == "production_today"
    assert routed["metadata_route"]["candidate_target_dataset"] == "production_today"
    assert routed["metadata_route"]["route_llm_required"] is True
    assert routed["metadata_route"]["route_llm_used"] is True
    assert prompt_payload["prompt_type"] == "route_classifier"
    assert result["metadata_qa"]["target_dataset"] == "production_today"
    assert "FROM PRODUCTION_TODAY" in result["answer_message"]


def test_metadata_qa_searches_domain_items(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")

    payload = seed_payload("AUTO향 관련 등록 정보 알려줘", monkeypatch)
    routed = classify_route(route_normalizer, router.route_metadata_question(payload), metadata_action="domain_search", target_term="AUTO향")
    result = response_builder.build_metadata_qa_response(routed)

    assert result["metadata_qa"]["metadata_action"] == "domain_search"
    assert any(row["SECTION"] == "product_terms" and row["KEY"] == "automotive" for row in result["data"]["rows"])
    assert "automotive" in result["answer_message"]


def test_metadata_qa_does_not_overwrite_previous_current_data(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")

    previous_current_data = {
        "columns": ["MODE", "WIP"],
        "rows": [{"MODE": "LPDDR5", "WIP": 10}],
        "row_count": 1,
        "product_key_columns": ["MODE"],
        "product_key_values": [{"MODE": "LPDDR5"}],
    }
    payload = seed_payload(
        "현재 조회 가능한 데이터 목록 알려줘",
        monkeypatch,
        state={"current_data": previous_current_data},
    )
    routed = classify_route(route_normalizer, router.route_metadata_question(payload), metadata_action="catalog_list")
    result = response_builder.build_metadata_qa_response(routed)

    assert result["state"]["current_data"]["rows"] == previous_current_data["rows"]
    assert result["state"]["current_data"]["columns"] == previous_current_data["columns"]
    assert result["state"]["current_data"]["row_count"] == previous_current_data["row_count"]
    assert result["state"]["current_data"]["product_key_values"] == previous_current_data["product_key_values"]
    assert result["state"]["current_data"]["product_key_count"] == 1
    assert result["state"]["context"]["last_route"] == "metadata_qa"


def test_metadata_qa_passes_analysis_question_to_existing_flow(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")

    payload = seed_payload("오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성률을 보여줘", monkeypatch)
    routed = classify_route(route_normalizer, router.route_metadata_question(payload), route="data_analysis")
    result = response_builder.build_metadata_qa_response(routed)

    assert routed["metadata_route"]["route"] == "data_analysis"
    assert routed["metadata_route"]["route_llm_required"] is True
    assert routed["metadata_route"]["route_llm_used"] is True
    assert "direct_response_ready" not in result
    assert result["request"]["question"] == payload["request"]["question"]


def test_ambiguous_dataset_usage_question_uses_route_classifier(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_prompt_builder = load_component("langflow_components/router_flow/03_route_classifier_prompt_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")

    payload = seed_payload("production_today로 뭘 볼 수 있어?", monkeypatch)
    routed = router.route_metadata_question(payload)
    prompt_payload = route_prompt_builder.build_route_classifier_prompt_payload(routed)

    assert routed["metadata_route"]["route"] == "data_analysis"
    assert routed["metadata_route"]["route_llm_required"] is True
    assert prompt_payload["prompt_type"] == "route_classifier"

    llm_route = json.dumps(
        {
            "route": "metadata_qa",
            "metadata_action": "dataset_examples",
            "target_dataset": "production_today",
            "target_family": "",
            "target_term": "",
            "confidence": "high",
            "reason": "The user asks what can be done with a registered dataset.",
        },
        ensure_ascii=False,
    )
    classified = route_normalizer.normalize_route_classifier_payload(routed, llm_route)
    result = response_builder.build_metadata_qa_response(classified)

    assert classified["metadata_route"]["route_source"] == "llm"
    assert classified["metadata_route"]["route_llm_used"] is True
    assert result["direct_response_ready"] is True
    assert result["metadata_qa"]["metadata_action"] == "dataset_examples"
    assert result["metadata_qa"]["target_dataset"] == "production_today"


def test_direct_metadata_response_passes_through_downstream_nodes(monkeypatch: Any) -> None:
    router = load_component("langflow_components/router_flow/02_route_candidate_builder.py")
    route_prompt_builder = load_component("langflow_components/router_flow/03_route_classifier_prompt_builder.py")
    route_normalizer = load_component("langflow_components/router_flow/04_route_classifier_normalizer.py")
    response_builder = load_component("langflow_components/metadata_qa_flow/02_metadata_qa_response_builder.py")
    intent_prompt_builder = load_component("langflow_components/data_analysis_flow/02_intent_prompt_builder.py")
    intent_normalizer = load_component("langflow_components/data_analysis_flow/03_intent_plan_normalizer.py")
    retrieval_adapter = load_component("langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py")
    pandas_prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    data_store = load_component("langflow_components/data_analysis_flow/17_mongodb_data_store.py")
    answer_prompt_builder = load_component("langflow_components/data_analysis_flow/18_answer_prompt_builder.py")
    answer_builder = load_component("langflow_components/data_analysis_flow/19_answer_response_builder.py")

    payload = seed_payload("production_today 조회 쿼리문 알려줘", monkeypatch)
    routed = router.route_metadata_question(payload)
    prompt_payload = route_prompt_builder.build_route_classifier_prompt_payload(routed)
    routed = classify_route(route_normalizer, routed, metadata_action="dataset_query", target_dataset="production_today")
    payload = response_builder.build_metadata_qa_response(routed)
    original_answer = payload["answer_message"]

    assert intent_prompt_builder.build_intent_prompt_payload(payload)["prompt_type"] == "direct_response_skip"
    payload = intent_normalizer.normalize_intent_payload(payload, '{"intent_type":"wrong"}')
    payload = retrieval_adapter.adapt_retrieval_payload(payload, {"retrieval_payload": {"source_results": []}})
    assert pandas_prompt_builder.build_pandas_prompt_payload(payload)["prompt_type"] == "direct_response_skip"
    payload = pandas_executor.execute_pandas_from_llm(payload, "{}")
    payload = data_store.store_payload_in_mongodb(payload, enabled="true")
    assert payload["mongo_data_store"]["stored"] is False
    assert answer_prompt_builder.build_answer_prompt_payload(payload)["prompt_type"] == "direct_response_skip"
    payload = answer_builder.build_answer_response_payload(payload, "LLM이 다른 답을 해도 무시")

    assert payload["answer_message"] == original_answer
    assert payload["direct_response_ready"] is True


def classify_route(
    route_normalizer: Any,
    payload: dict[str, Any],
    *,
    route: str = "metadata_qa",
    metadata_action: str = "",
    target_dataset: str = "",
    target_family: str = "",
    target_term: str = "",
    confidence: str = "high",
) -> dict[str, Any]:
    llm_route = json.dumps(
        {
            "route": route,
            "metadata_question_type": metadata_action if route == "metadata_qa" else "",
            "metadata_action": metadata_action if route == "metadata_qa" else "",
            "target_dataset": target_dataset,
            "target_family": target_family,
            "target_term": target_term,
            "confidence": confidence,
            "reason": "Classified by question type.",
        },
        ensure_ascii=False,
    )
    return route_normalizer.normalize_route_classifier_payload(payload, llm_route)


def seed_payload(question: str, monkeypatch: Any, state: dict[str, Any] | None = None) -> dict[str, Any]:
    request_loader = load_component("langflow_components/data_analysis_flow/00_analysis_request_loader.py")
    metadata_loader = load_component("langflow_components/data_analysis_flow/01_metadata_context_loader.py")
    payload = request_loader.build_request_payload(question, "test-session", state=state or {})
    install_fake_pymongo(monkeypatch, seed_metadata_docs())
    return metadata_loader.load_metadata_payload(
        payload,
        mongo_uri="mongodb://fake",
        mongo_database="metadata_driven_agent_v3",
        domain_collection_name="agent_v3_domain_items",
        table_catalog_collection_name="agent_v3_table_catalog_items",
        main_flow_filter_collection_name="agent_v3_main_flow_filters",
    )


def seed_metadata_docs() -> dict[str, list[dict[str, Any]]]:
    domain = read_metadata_json("domain_items.json")
    table_catalog = read_metadata_json("table_catalog.json")
    filters = read_metadata_json("main_flow_filters.json")
    domain_docs: list[dict[str, Any]] = []
    for section, value in domain.items():
        if section == "product_key_columns":
            domain_docs.append({"section": section, "key": section, "columns": value})
        elif isinstance(value, dict):
            for key, payload in value.items():
                domain_docs.append({"section": section, "key": key, "payload": payload})
    table_docs = [
        {"dataset_key": key, "payload": payload}
        for key, payload in (table_catalog.get("datasets") or {}).items()
    ]
    filter_docs = [{"filter_key": key, "payload": payload} for key, payload in filters.items()]
    return {
        "agent_v3_domain_items": domain_docs,
        "agent_v3_table_catalog_items": table_docs,
        "agent_v3_main_flow_filters": filter_docs,
    }


def read_metadata_json(filename: str) -> dict[str, Any]:
    return json.loads((ROOT / "metadata" / filename).read_text(encoding="utf-8"))


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

