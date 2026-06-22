from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_marked_example(relative_path: str, marker: str) -> str:
    text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    pattern = rf"<!--\s*{re.escape(marker)}:start\s*-->(.*?)<!--\s*{re.escape(marker)}:end\s*-->"
    match = re.search(pattern, text, re.DOTALL)
    assert match, f"{relative_path} does not contain marked example {marker}"
    content = match.group(1).strip()
    fenced = re.fullmatch(r"```(?:text)?\s*\n(.*?)\n```", content, re.DOTALL)
    return (fenced.group(1) if fenced else content).strip()


DOMAIN_EXAMPLE_PATH = "langflow_components/domain_authoring_flow/raw_text_input_example.md"
TABLE_EXAMPLE_PATH = "langflow_components/table_catalog_authoring_flow/raw_text_input_example.md"
FILTER_EXAMPLE_PATH = "langflow_components/main_flow_filters_authoring_flow/raw_text_input_example.md"

DOMAIN_BULK_TEXT = read_marked_example(DOMAIN_EXAMPLE_PATH, "bulk_domain")
DOMAIN_DA_TEXT = read_marked_example(DOMAIN_EXAMPLE_PATH, "single_da_process")
TABLE_BULK_TEXT = read_marked_example(TABLE_EXAMPLE_PATH, "bulk_table_catalog")
TABLE_HOLD_HISTORY_TEXT = read_marked_example(TABLE_EXAMPLE_PATH, "single_hold_history")
FILTER_BULK_TEXT = read_marked_example(FILTER_EXAMPLE_PATH, "bulk_main_flow_filters")
FILTER_EQP_MODEL_TEXT = read_marked_example(FILTER_EXAMPLE_PATH, "single_eqp_model")
FORBIDDEN_STORAGE_FIELDS = {
    "schema_version",
    "agent_version",
    "metadata_type",
    "namespace",
    "identity",
    "source",
    "_source_file",
    "_source_name",
    "payload_hash",
}


def assert_lean_metadata_doc(doc: dict[str, Any]) -> None:
    assert not (FORBIDDEN_STORAGE_FIELDS & set(doc))


def load_module(relative_path: str):
    path = PROJECT_ROOT / relative_path
    module_name = "metadata_text_input_test_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeReplaceResult:
    def __init__(self, upserted_id: str | None, modified_count: int) -> None:
        self.upserted_id = upserted_id
        self.modified_count = modified_count


class FakeCollection:
    def __init__(self, docs: dict[str, dict[str, Any]]) -> None:
        self.docs = docs

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    def replace_one(self, query: dict[str, Any], doc: dict[str, Any], upsert: bool = False) -> FakeReplaceResult:
        key = str(query.get("_id") or doc["_id"])
        existed = key in self.docs
        self.docs[key] = dict(doc)
        return FakeReplaceResult(None if existed else key, 1 if existed else 0)


class FakeDatabase:
    def __init__(self, db_name: str, store: dict[tuple[str, str], dict[str, dict[str, Any]]]) -> None:
        self.db_name = db_name
        self.store = store

    def __getitem__(self, collection_name: str) -> FakeCollection:
        docs = self.store.setdefault((self.db_name, collection_name), {})
        return FakeCollection(docs)


class FakeMongoClient:
    store: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}

    def __init__(self, mongo_uri: str, **_: Any) -> None:
        self.mongo_uri = mongo_uri

    def __getitem__(self, db_name: str) -> FakeDatabase:
        return FakeDatabase(db_name, self.store)

    def close(self) -> None:
        return None


def install_fake_mongo(monkeypatch: Any, writer_module: Any) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    FakeMongoClient.store = {}
    fake_pymongo = SimpleNamespace(MongoClient=FakeMongoClient)
    monkeypatch.setattr(writer_module, "import_module", lambda name: fake_pymongo)
    return FakeMongoClient.store


def read_json(relative_path: str) -> Any:
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def domain_items_from_current_metadata() -> list[dict[str, Any]]:
    data = read_json("metadata/domain_items.json")
    items: list[dict[str, Any]] = []
    for section in ["process_groups", "product_terms", "quantity_terms", "metric_terms", "analysis_recipes", "status_terms"]:
        for key, payload in data[section].items():
            items.append({"section": section, "key": key, "payload": payload, "confidence": "high"})
    items.append(
        {
            "section": "product_key_columns",
            "key": "product_key_columns",
            "columns": data["product_key_columns"],
            "payload": {"columns": data["product_key_columns"]},
            "confidence": "high",
        }
    )
    return items


def table_items_from_current_metadata() -> list[dict[str, Any]]:
    data = read_json("metadata/table_catalog.json")
    return [
        {"dataset_key": dataset_key, "payload": payload, "confidence": "high"}
        for dataset_key, payload in data["datasets"].items()
    ]


FILTER_AUTHORING_HINTS: dict[str, dict[str, Any]] = {
    "DATE": {"aliases": ["기준일", "일자", "날짜", "오늘", "어제", "작업일"], "semantic_role": "date", "value_type": "date"},
    "OPER_NAME": {"aliases": ["공정명", "공정", "오퍼명"], "semantic_role": "process"},
    "TECH": {"aliases": ["제품 기술", "TECH"], "semantic_role": "product_attribute"},
    "DEN": {"aliases": ["제품 용량", "DEN"], "semantic_role": "product_attribute"},
    "MODE": {"aliases": ["제품 모드", "MODE"], "semantic_role": "product_attribute"},
    "PKG_TYPE1": {"aliases": ["패키지 타입1", "PKG_TYPE1"], "semantic_role": "package_attribute"},
    "PKG_TYPE2": {"aliases": ["패키지 타입2", "PKG_TYPE2"], "semantic_role": "package_attribute"},
    "LEAD": {"aliases": ["Lead", "LEAD"], "semantic_role": "product_attribute"},
    "MCP_NO": {"aliases": ["제품 코드", "MCP 번호", "MCP NO"], "semantic_role": "product_code"},
    "DEVICE": {"aliases": ["디바이스", "DEVICE", "제품 코드"], "semantic_role": "device"},
    "DEVICE_DESC": {"aliases": ["device", "device code", "DEVICE_DESC"], "semantic_role": "device"},
    "TSV_DIE_TYP": {"aliases": ["HBM 판별", "3DS 판별", "TSV 판별"], "semantic_role": "product_condition"},
    "OPER_NUM": {"aliases": ["공정 번호", "OPER_NUM"], "semantic_role": "process_number"},
    "OPER_SEQ": {"aliases": ["공정 순서", "OPER_SEQ"], "semantic_role": "process_sequence"},
    "DIE_ATTACH_QTY": {"aliases": ["Die attach 수량", "DIE_ATTACH_QTY"], "semantic_role": "quantity"},
    "NETDIE_300_CNT": {"aliases": ["Net die 수량", "NETDIE_300_CNT"], "semantic_role": "quantity"},
    "LOT_ID": {"aliases": ["Lot ID", "LOT 번호"], "semantic_role": "lot_id"},
    "LOT_STAT_CD": {"aliases": ["Lot 작업 상태", "LOT 상태"], "semantic_role": "lot_status"},
    "LOT_HOLD_STAT_CD": {"aliases": ["Lot hold 상태", "Hold 상태"], "semantic_role": "hold_status"},
    "EQP_ID": {"aliases": ["장비 ID", "장비 번호"], "semantic_role": "equipment_id"},
    "EQP_MODEL": {"aliases": ["장비 모델", "EQP_MODEL"], "semantic_role": "equipment_model"},
    "RECIPE_ID": {"aliases": ["Recipe ID", "레시피"], "semantic_role": "recipe_id"},
}


def filter_items_from_current_metadata() -> list[dict[str, Any]]:
    data = read_json("metadata/main_flow_filters.json")
    items = []
    for filter_key, payload in data.items():
        hints = FILTER_AUTHORING_HINTS[filter_key]
        authoring_payload = {
            "display_name": payload.get("description", filter_key),
            "description": payload.get("description", ""),
            "aliases": hints["aliases"],
            "column_candidates": payload["column_candidates"],
            "semantic_role": hints["semantic_role"],
            "value_type": hints.get("value_type", "string"),
            "value_shape": "scalar",
            "operator": "eq",
        }
        items.append({"filter_key": filter_key, "payload": authoring_payload, "confidence": "high"})
    return items


def run_domain_authoring_flow(raw_text: str, items: list[dict[str, Any]], monkeypatch: Any) -> tuple[dict[str, Any], dict[Any, Any]]:
    request = load_module("langflow_components/domain_authoring_flow/00_domain_authoring_request_loader.py")
    refine = load_module("langflow_components/domain_authoring_flow/02_domain_text_refinement_normalizer.py")
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/domain_authoring_flow/05_domain_similarity_checker.py")
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    store = install_fake_mongo(monkeypatch, writer)

    payload = request.build_domain_authoring_request(
        raw_text,
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
        load_existing="false",
    )
    refined = refine.normalize_domain_refinement(payload, json.dumps({"refined_text": raw_text, "needs_more_input": False}, ensure_ascii=False))
    normalized = normalizer.normalize_domain_authoring_result(
        refined,
        json.dumps({"items": items, "missing_information": [], "warnings": []}, ensure_ascii=False),
    )
    assert normalized["errors"] == []
    checked = similarity.check_domain_similarity(normalized, "merge")
    written = writer.review_and_write_domain_payload(
        checked,
        json.dumps({"ready_to_save": True, "supplement_requests": []}, ensure_ascii=False),
        mongo_uri="mongodb://fake",
    )
    return written, store


def run_table_authoring_flow(raw_text: str, items: list[dict[str, Any]], monkeypatch: Any) -> tuple[dict[str, Any], dict[Any, Any]]:
    request = load_module("langflow_components/table_catalog_authoring_flow/00_table_catalog_authoring_request_loader.py")
    refine = load_module("langflow_components/table_catalog_authoring_flow/02_table_catalog_text_refinement_normalizer.py")
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/table_catalog_authoring_flow/05_table_catalog_similarity_checker.py")
    writer = load_module("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    store = install_fake_mongo(monkeypatch, writer)

    payload = request.build_table_catalog_authoring_request(
        raw_text,
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
        load_existing="false",
    )
    refined = refine.normalize_table_catalog_refinement(payload, json.dumps({"refined_text": raw_text, "needs_more_input": False}, ensure_ascii=False))
    normalized = normalizer.normalize_table_catalog_authoring_result(
        refined,
        json.dumps({"items": items, "missing_information": [], "warnings": []}, ensure_ascii=False),
    )
    assert normalized["errors"] == []
    checked = similarity.check_table_catalog_similarity(normalized, "merge")
    written = writer.review_and_write_table_catalog_payload(
        checked,
        json.dumps({"ready_to_save": True, "supplement_requests": []}, ensure_ascii=False),
        mongo_uri="mongodb://fake",
    )
    return written, store


def run_filter_authoring_flow(raw_text: str, items: list[dict[str, Any]], monkeypatch: Any) -> tuple[dict[str, Any], dict[Any, Any]]:
    request = load_module("langflow_components/main_flow_filters_authoring_flow/00_main_flow_filter_authoring_request_loader.py")
    refine = load_module("langflow_components/main_flow_filters_authoring_flow/02_main_flow_filter_text_refinement_normalizer.py")
    normalizer = load_module("langflow_components/main_flow_filters_authoring_flow/04_main_flow_filter_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/main_flow_filters_authoring_flow/05_main_flow_filter_similarity_checker.py")
    writer = load_module("langflow_components/main_flow_filters_authoring_flow/07_main_flow_filter_review_writer.py")
    store = install_fake_mongo(monkeypatch, writer)

    payload = request.build_main_flow_filter_authoring_request(
        raw_text,
        mongo_uri="mongodb://fake",
        duplicate_action="merge",
        load_existing="false",
    )
    refined = refine.normalize_main_flow_filter_refinement(payload, json.dumps({"refined_text": raw_text, "needs_more_input": False}, ensure_ascii=False))
    normalized = normalizer.normalize_main_flow_filter_authoring_result(
        refined,
        json.dumps({"items": items, "missing_information": [], "warnings": []}, ensure_ascii=False),
    )
    assert normalized["errors"] == []
    checked = similarity.check_main_flow_filter_similarity(normalized, "merge")
    written = writer.review_and_write_main_flow_filter_payload(
        checked,
        json.dumps({"ready_to_save": True, "supplement_requests": []}, ensure_ascii=False),
        mongo_uri="mongodb://fake",
    )
    return written, store


def test_domain_writer_uses_payload_duplicate_decision_to_resolve_review_blocker(monkeypatch: Any) -> None:
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    store = install_fake_mongo(monkeypatch, writer)
    store[("metadata_driven_agent_v3", "agent_v3_domain_items")] = {
        "domain:product_terms:automotive": {
            "_id": "domain:product_terms:automotive",
            "section": "product_terms",
            "key": "automotive",
            "payload": {"display_name": "AUTO향", "aliases": ["AUTO향"]},
        }
    }
    payload = {
        "metadata_type": "domain",
        "items": [
            {
                "section": "product_terms",
                "key": "automotive",
                "payload": {"aliases": ["오토모티브향", "오토향"]},
                "confidence": "high",
            }
        ],
        "duplicate_decision": {
            "action": "merge",
            "requires_user_choice": True,
            "allowed_actions": ["merge", "replace", "skip", "create_new"],
        },
        "existing_matches": [{"match_type": "same_key"}],
        "errors": [],
    }
    review_json = {
        "ready_to_save": False,
        "supplement_requests": [
            {
                "field": "duplicate_action",
                "reason": "같은 key의 기존 domain 정보가 있어 저장 방식을 선택해야 합니다.",
            }
        ],
        "item_reviews": [{"section": "product_terms", "key": "automotive", "decision": "needs_fix"}],
    }

    written = writer.review_and_write_domain_payload(
        payload,
        json.dumps(review_json, ensure_ascii=False),
        mongo_uri="mongodb://fake",
    )

    assert written["review"]["ready_to_save"] is True
    assert written["review"]["supplement_requests"] == []
    assert written["duplicate_decision"]["action"] == "merge"
    assert written["duplicate_decision"]["requires_user_choice"] is False
    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 1
    doc = store[("metadata_driven_agent_v3", "agent_v3_domain_items")]["domain:product_terms:automotive"]
    assert doc["payload"]["aliases"] == ["AUTO향", "오토모티브향", "오토향"]


def test_domain_writer_ignores_duplicate_message_request_when_action_is_resolved(monkeypatch: Any) -> None:
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    store = install_fake_mongo(monkeypatch, writer)
    payload = {
        "metadata_type": "domain",
        "items": [
            {
                "section": "product_terms",
                "key": "pop",
                "status": "active",
                "payload": {
                    "display_name": "POP 제품",
                    "aliases": ["POP 제품"],
                    "condition": {"MODE": {"starts_with": "LP"}},
                },
                "confidence": "high",
            }
        ],
        "duplicate_decision": {
            "action": "replace",
            "requires_user_choice": False,
            "allowed_actions": ["merge", "replace", "skip", "create_new"],
            "message": "",
        },
        "existing_matches": [],
        "conflict_warnings": [],
        "errors": [],
    }
    review_json = {
        "ready_to_save": False,
        "summary": "저장 보류 중: 중복 처리 결정에 대한 설명이 필요합니다.",
        "supplement_requests": [
            {
                "field": "duplicate_decision.message",
                "reason": "기존 항목을 어떻게 처리할지에 대한 설명 메시지가 비어 있습니다.",
                "example_user_input": "기존 POP 제품을 새 정의로 교체합니다.",
            }
        ],
        "item_reviews": [{"section": "product_terms", "key": "pop", "decision": "pass"}],
    }

    written = writer.review_and_write_domain_payload(
        payload,
        json.dumps(review_json, ensure_ascii=False),
        mongo_uri="mongodb://fake",
    )

    assert written["review"]["ready_to_save"] is True
    assert written["review"]["supplement_requests"] == []
    assert written["duplicate_decision"]["action"] == "replace"
    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 1
    doc = store[("metadata_driven_agent_v3", "agent_v3_domain_items")]["domain:product_terms:pop"]
    assert doc["payload"]["display_name"] == "POP 제품"


def test_worker_bulk_domain_text_input_saves_all_current_domain_metadata(monkeypatch: Any) -> None:
    items = domain_items_from_current_metadata()
    written, store = run_domain_authoring_flow(DOMAIN_BULK_TEXT, items, monkeypatch)

    assert written["raw_text"] == DOMAIN_BULK_TEXT
    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 38
    docs = store[("metadata_driven_agent_v3", "agent_v3_domain_items")]
    assert set(docs) >= {
        "domain:process_groups:DA",
        "domain:product_terms:hbm",
        "domain:product_terms:lpddr5",
        "domain:quantity_terms:lot_count",
        "domain:quantity_terms:hold_lot_count",
        "domain:quantity_terms:in_tat",
        "domain:quantity_terms:wafer_qty",
        "domain:quantity_terms:die_qty",
        "domain:analysis_recipes:production_wip_target_rate",
        "domain:analysis_recipes:lot_quantity_summary",
        "domain:analysis_recipes:top_wip_process_hold_lot_in_tat",
        "domain:analysis_recipes:top_wip_product_oldest_lot",
        "domain:analysis_recipes:top_production_products_equipment_count",
    }
    assert docs["domain:product_terms:hbm"]["payload"]["condition_by_family"]["equipment"] == {"PKG_TYPE1": "HBM"}
    assert docs["domain:quantity_terms:lot_count"]["payload"]["aggregation"] == "nunique"
    assert docs["domain:quantity_terms:hold_lot_count"]["payload"]["output_column"] == "HOLD_LOT_COUNT"
    assert docs["domain:quantity_terms:in_tat"]["payload"]["aggregation"] == "mean"
    assert docs["domain:quantity_terms:equipment_count"]["payload"]["aggregation"] == "nunique"
    assert docs["domain:quantity_terms:equipment_count"]["payload"]["output_column"] == "EQP_COUNT"
    assert docs["domain:metric_terms:achievement_rate"]["payload"]["required_quantity_terms"] == ["production", "target"]
    assert docs["domain:analysis_recipes:production_wip_target_rate"]["payload"]["intent_type"] == "multi_source_analysis"
    assert docs["domain:analysis_recipes:production_wip_target_rate"]["payload"]["grain_policy"] == "question_or_product_grain"
    assert docs["domain:analysis_recipes:production_wip_target_rate"]["payload"]["source_aliases_by_family"] == {
        "production": "production_data",
        "wip": "wip_data",
        "target": "target_data",
    }
    assert docs["domain:analysis_recipes:lot_quantity_summary"]["payload"]["output_columns"] == [
        "LOT_COUNT",
        "WF_QTY",
        "DIE_QTY",
    ]
    top_wip_recipe = docs["domain:analysis_recipes:top_wip_process_hold_lot_in_tat"]["payload"]
    assert top_wip_recipe["intent_type"] == "multi_step_analysis"
    assert top_wip_recipe["grain_policy"] == "recipe_step_grain"
    assert top_wip_recipe["replace_retrieval_jobs"] is True
    assert top_wip_recipe["required_question_cues"][0] == ["재공", "WIP", "wip"]
    assert "장비 대수" in top_wip_recipe["forbidden_question_cues"]
    assert top_wip_recipe["blocked_filter_fields"] == ["LOT_HOLD_STAT_CD", "LOT_STAT_CD"]
    assert top_wip_recipe["step_plan_template"][0]["operation"] == "rank_top_n"
    assert top_wip_recipe["step_plan_template"][0]["rename_columns"] == {"OPER_NAME": "OPER_SHORT_DESC"}
    assert top_wip_recipe["output_columns"] == ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]
    assert docs["domain:analysis_recipes:top_wip_product_oldest_lot"]["payload"]["step_plan_template"][1]["metric"] == "IN_TAT"
    assert docs["domain:analysis_recipes:top_production_products_equipment_count"]["payload"]["step_plan_template"][1]["count_column"] == "EQPID"
    assert docs["domain:analysis_recipes:equipment_for_previous_products"]["payload"]["result_mode"] == "detail_rows"
    assert docs["domain:analysis_recipes:equipment_count_for_previous_products"]["payload"]["output_columns"] == [
        "TECH",
        "DEN",
        "MODE",
        "PKG_TYPE1",
        "PKG_TYPE2",
        "LEAD",
        "MCP_NO",
        "EQP_COUNT",
    ]
    assert docs["domain:status_terms:hold_lot"]["payload"]["result_mode"] == "detail_rows"


def test_worker_single_domain_text_input_saves_one_process_group(monkeypatch: Any) -> None:
    data = read_json("metadata/domain_items.json")
    item = {"section": "process_groups", "key": "DA", "payload": data["process_groups"]["DA"], "confidence": "high"}
    written, store = run_domain_authoring_flow(
        DOMAIN_DA_TEXT,
        [item],
        monkeypatch,
    )

    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 1
    docs = store[("metadata_driven_agent_v3", "agent_v3_domain_items")]
    doc = docs["domain:process_groups:DA"]
    assert_lean_metadata_doc(doc)
    assert doc["section"] == "process_groups"
    assert doc["key"] == "DA"
    assert doc["payload"]["processes"] == ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]


def test_worker_bulk_table_text_input_saves_all_current_datasets(monkeypatch: Any) -> None:
    items = table_items_from_current_metadata()
    written, store = run_table_authoring_flow(TABLE_BULK_TEXT, items, monkeypatch)

    assert written["raw_text"] == TABLE_BULK_TEXT
    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 9
    docs = store[("metadata_driven_agent_v3", "agent_v3_table_catalog_items")]
    assert set(docs) >= {"table_catalog:production_today", "table_catalog:wip_today", "table_catalog:hold_history"}
    assert docs["table_catalog:hold_history"]["payload"]["required_params"] == ["LOT_ID"]
    assert docs["table_catalog:hold_history"]["payload"]["default_detail_columns"] == [
        "LOT_ID",
        "HOLD_TM",
        "HOLD_CD",
        "HOLD_DESC",
        "HOLD_USER_ID",
        "EVENT_CD",
    ]
    assert docs["table_catalog:target"]["payload"]["standard_column_aliases"]["OUT_PLAN"] == ["OUT계획", "TARGET"]
    assert docs["table_catalog:equipment_status"]["payload"]["filter_mappings"]["MCP_NO"] == ["MCPSALENO", "MCP_NO"]
    assert docs["table_catalog:equipment_status"]["payload"]["standard_column_aliases"]["MCP_NO"] == ["MCPSALENO"]
    assert docs["table_catalog:equipment_status"]["payload"]["primary_quantity_column"] == "EQPID"
    assert "PRESS_CNT" not in docs["table_catalog:equipment_status"]["payload"]["default_detail_columns"]


def test_worker_single_table_text_input_saves_hold_history(monkeypatch: Any) -> None:
    data = read_json("metadata/table_catalog.json")
    item = {"dataset_key": "hold_history", "payload": data["datasets"]["hold_history"], "confidence": "high"}
    written, store = run_table_authoring_flow(
        TABLE_HOLD_HISTORY_TEXT,
        [item],
        monkeypatch,
    )

    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 1
    docs = store[("metadata_driven_agent_v3", "agent_v3_table_catalog_items")]
    doc = docs["table_catalog:hold_history"]
    assert_lean_metadata_doc(doc)
    assert doc["dataset_key"] == "hold_history"
    assert doc["key"] == "hold_history"
    assert doc["payload"]["source_type"] == "oracle"


def test_worker_bulk_filter_text_input_saves_all_current_filters(monkeypatch: Any) -> None:
    items = filter_items_from_current_metadata()
    written, store = run_filter_authoring_flow(FILTER_BULK_TEXT, items, monkeypatch)

    assert written["raw_text"] == FILTER_BULK_TEXT
    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 22
    docs = store[("metadata_driven_agent_v3", "agent_v3_main_flow_filters")]
    assert set(docs) >= {"main_flow_filter:DATE", "main_flow_filter:LOT_ID", "main_flow_filter:EQP_MODEL"}
    assert docs["main_flow_filter:DATE"]["payload"]["semantic_role"] == "date"


def test_worker_single_filter_text_input_saves_eqp_model(monkeypatch: Any) -> None:
    item = next(item for item in filter_items_from_current_metadata() if item["filter_key"] == "EQP_MODEL")
    written, store = run_filter_authoring_flow(
        FILTER_EQP_MODEL_TEXT,
        [item],
        monkeypatch,
    )

    assert written["write_result"]["status"] == "ok"
    assert written["write_result"]["saved_count"] == 1
    docs = store[("metadata_driven_agent_v3", "agent_v3_main_flow_filters")]
    doc = docs["main_flow_filter:EQP_MODEL"]
    assert_lean_metadata_doc(doc)
    assert doc["filter_key"] == "EQP_MODEL"
    assert doc["key"] == "EQP_MODEL"
    assert doc["payload"]["column_candidates"] == ["EQP_MODEL"]
