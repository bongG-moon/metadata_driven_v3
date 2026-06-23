from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "upload_json_to_mongodb.py"
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


def test_mongodb_upload_can_select_domain_only():
    module = _load_upload_module()
    batches = module.build_upload_batches(ROOT, metadata_kinds=["domain"])

    assert list(batches) == ["agent_v3_domain_items"]
    assert "domain:process_groups:DA" in {doc["_id"] for doc in batches["agent_v3_domain_items"]}


def test_mongodb_upload_can_select_multiple_metadata_kinds_with_aliases():
    module = _load_upload_module()
    batches = module.build_upload_batches(ROOT, metadata_kinds=["table-catalog,main-flow-filter"])

    assert list(batches) == [
        "agent_v3_table_catalog_items",
        "agent_v3_main_flow_filters",
    ]
    assert "table_catalog:wip_today" in {doc["_id"] for doc in batches["agent_v3_table_catalog_items"]}
    assert "main_flow_filter:DATE" in {doc["_id"] for doc in batches["agent_v3_main_flow_filters"]}


def test_mongodb_upload_rejects_unknown_metadata_kind():
    module = _load_upload_module()

    try:
        module.build_upload_batches(ROOT, metadata_kinds=["unknown"])
    except ValueError as exc:
        assert "Invalid --metadata-kind" in str(exc)
    else:
        raise AssertionError("unknown metadata kind should fail")


def test_mongodb_upload_docs_use_lean_metadata_shape():
    module = _load_upload_module()
    batches = module.build_upload_batches(
        ROOT,
        domain_collection_name="factory_domain_metadata",
        table_catalog_collection_name="factory_table_catalog_metadata",
        main_flow_filter_collection_name="factory_filter_metadata",
    )

    domain_doc = next(doc for doc in batches["factory_domain_metadata"] if doc["_id"] == "domain:process_groups:DA")
    assert not (FORBIDDEN_STORAGE_FIELDS & set(domain_doc))
    assert domain_doc["section"] == "process_groups"
    assert domain_doc["key"] == "DA"
    assert domain_doc["status"] == "active"
    assert "payload" in domain_doc

    table_doc = next(doc for doc in batches["factory_table_catalog_metadata"] if doc["_id"] == "table_catalog:wip_today")
    assert not (FORBIDDEN_STORAGE_FIELDS & set(table_doc))
    assert table_doc["dataset_key"] == "wip_today"
    assert table_doc["key"] == "wip_today"
    assert table_doc["status"] == "active"

    filter_doc = next(doc for doc in batches["factory_filter_metadata"] if doc["_id"] == "main_flow_filter:DATE")
    assert not (FORBIDDEN_STORAGE_FIELDS & set(filter_doc))
    assert filter_doc["filter_key"] == "DATE"
    assert filter_doc["key"] == "DATE"
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
    assert not (FORBIDDEN_STORAGE_FIELDS & set(batches["agent_v3_regression_questions"][0]))
    assert not (FORBIDDEN_STORAGE_FIELDS & set(batches["agent_v3_sample_wip_today"][0]))


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
