from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "upload_json_to_mongodb.py"


def _load_upload_module():
    spec = importlib.util.spec_from_file_location("upload_json_to_mongodb", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_mongodb_upload_default_batches_include_only_core_metadata():
    module = _load_upload_module()
    batches = module.build_upload_batches(
        ROOT,
        domain_collection_name="factory_domain_metadata",
        table_catalog_collection_name="factory_table_catalog_metadata",
        main_flow_filter_collection_name="factory_filter_metadata",
    )

    assert list(batches) == [
        "factory_domain_metadata",
        "factory_table_catalog_metadata",
        "factory_filter_metadata",
    ]
    assert "domain:analysis_recipes:production_wip_target_rate" in {
        doc["_id"] for doc in batches["factory_domain_metadata"]
    }


def test_mongodb_upload_docs_include_v3_envelope_and_legacy_fields():
    module = _load_upload_module()
    batches = module.build_upload_batches(
        ROOT,
        domain_collection_name="factory_domain_metadata",
        table_catalog_collection_name="factory_table_catalog_metadata",
        main_flow_filter_collection_name="factory_filter_metadata",
    )

    domain_doc = next(doc for doc in batches["factory_domain_metadata"] if doc["_id"] == "domain:process_groups:DA")
    assert domain_doc["schema_version"] == "metadata-doc.v1"
    assert domain_doc["agent_version"] == "metadata_driven_v3"
    assert domain_doc["metadata_type"] == "domain"
    assert domain_doc["namespace"] == "core"
    assert domain_doc["identity"] == {"type": "domain", "section": "process_groups", "key": "DA"}
    assert domain_doc["source"]["kind"] == "local_json"
    assert len(domain_doc["payload_hash"]) == 12
    assert domain_doc["section"] == "process_groups"
    assert domain_doc["key"] == "DA"
    assert domain_doc["status"] == "active"
    assert "payload" in domain_doc

    table_doc = next(doc for doc in batches["factory_table_catalog_metadata"] if doc["_id"] == "table_catalog:wip_today")
    assert table_doc["metadata_type"] == "table_catalog"
    assert table_doc["identity"] == {"type": "table_catalog", "dataset_key": "wip_today"}
    assert table_doc["dataset_key"] == "wip_today"
    assert table_doc["status"] == "active"

    filter_doc = next(doc for doc in batches["factory_filter_metadata"] if doc["_id"] == "main_flow_filter:DATE")
    assert filter_doc["metadata_type"] == "main_flow_filter"
    assert filter_doc["identity"] == {"type": "main_flow_filter", "filter_key": "DATE"}
    assert filter_doc["filter_key"] == "DATE"
    assert filter_doc["status"] == "active"


def test_mongodb_upload_optional_batches_include_regression_and_samples():
    module = _load_upload_module()
    batches = module.build_upload_batches(
        ROOT,
        domain_collection_name="agent_v3_domain_items",
        table_catalog_collection_name="agent_v3_table_catalog_items",
        main_flow_filter_collection_name="agent_v3_main_flow_filters",
        include_regression=True,
        include_sample_data=True,
    )

    assert "agent_v3_regression_questions" in batches
    assert "agent_v3_sample_wip_today" in batches
    assert len(batches["agent_v3_regression_questions"]) >= 16
    assert batches["agent_v3_regression_questions"][0]["metadata_type"] == "regression_question"
    assert batches["agent_v3_sample_wip_today"][0]["metadata_type"] == "sample_data"


def test_mongodb_upload_docs_have_deterministic_ids():
    module = _load_upload_module()
    first = module.build_upload_batches(ROOT, collection_prefix="agent_v3", include_sample_data=True)
    second = module.build_upload_batches(ROOT, collection_prefix="agent_v3", include_sample_data=True)

    first_ids = [doc["_id"] for doc in first["agent_v3_sample_wip_today"]]
    second_ids = [doc["_id"] for doc in second["agent_v3_sample_wip_today"]]
    assert first_ids == second_ids


def test_mongodb_upload_keeps_legacy_prefix_for_old_callers():
    module = _load_upload_module()
    batches = module.build_upload_batches(ROOT, "agent_v3")

    assert list(batches) == [
        "agent_v3_domain_items",
        "agent_v3_table_catalog_items",
        "agent_v3_main_flow_filters",
    ]


def test_mongodb_upload_treats_single_custom_name_as_full_domain_collection():
    module = _load_upload_module()
    batches = module.build_upload_batches(ROOT, domain_collection_name="factory_domain_metadata")

    assert list(batches) == [
        "factory_domain_metadata",
        "agent_v3_table_catalog_items",
        "agent_v3_main_flow_filters",
    ]
