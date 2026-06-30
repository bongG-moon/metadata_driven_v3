from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(relative_path: str):
    path = PROJECT_ROOT / relative_path
    module_name = "authoring_test_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_domain_authoring_normalizes_lot_count_and_blocks_pending_duplicate() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/domain_authoring_flow/05_domain_similarity_checker.py")
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    response = load_module("langflow_components/domain_authoring_flow/08_domain_authoring_response_builder.py")

    payload = {
        "metadata_type": "domain",
        "existing_items": [{"section": "quantity_terms", "key": "lot_count", "aliases": ["Lot 수량"]}],
        "duplicate_decision": {"action": "ask"},
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "section": "quantity_terms",
                "key": "lot_count",
                "payload": {
                    "aliases": ["Lot 수량"],
                    "dataset_key": "lot_status",
                    "quantity_column": "LOT_ID",
                    "aggregation": "count_distinct",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }
    normalized = normalizer.normalize_domain_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    assert normalized["items"][0]["payload"]["aggregation"] == "nunique"

    checked = similarity.check_domain_similarity(normalized, "ask")
    assert checked["existing_matches"]
    assert checked["duplicate_decision"]["requires_user_choice"] is True

    written = writer.review_and_write_domain_payload(checked, '{"ready_to_save": true, "supplement_requests": []}')
    assert written["write_result"]["status"] == "skipped"
    assert "선택" in written["write_result"]["skipped_reason"]

    api_response = response.build_domain_authoring_response(written)
    assert "비슷한 기존 정보" in api_response["message"]


def test_domain_authoring_preserves_dataset_specific_conditions_and_metric_dependencies() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    payload = {"metadata_type": "domain", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "section": "product_terms",
                "key": "hbm",
                "payload": {
                    "aliases": ["HBM"],
                    "condition": {"TSV_DIE_TYP": {"exists": True}},
                    "condition_by_family": {"equipment": {"PKG_TYPE1": "HBM"}},
                },
            },
            {
                "section": "metric_terms",
                "key": "achievement_rate",
                "payload": {
                    "aliases": ["달성율"],
                    "formula": "sum(PRODUCTION) / sum(OUT_PLAN) * 100",
                    "calculation_rule": "aggregate_first",
                    "required_quantity_terms": ["production", "target"],
                    "output_column": "ACHIEVEMENT_RATE",
                },
            },
            {
                "section": "analysis_recipes",
                "key": "production_wip_target_rate",
                "payload": {
                    "aliases": ["생산달성율"],
                    "intent_type": "multi_source_analysis",
                    "default_analysis_kind": "production_wip_target_rate",
                    "required_quantity_terms": ["production", "wip", "target"],
                    "required_dataset_families": ["production", "wip", "target"],
                    "metric_terms": ["achievement_rate"],
                    "grain_policy": "question_or_product_grain",
                    "source_aliases_by_family": {"production": "production_data"},
                    "required_columns_by_family": {"production": ["WORK_DT", "PRODUCTION"]},
                    "override_analysis_kinds": ["aggregate_join"],
                    "blocked_filter_fields": ["LOT_HOLD_STAT_CD"],
                    "replace_retrieval_jobs": True,
                    "override_step_plan": True,
                    "top_n_policy": "question_or_default",
                    "step_plan_template": [{"step_id": "join", "operation": "production_wip_target_rate"}],
                    "output_columns": ["WIP", "PRODUCTION", "OUT_PLAN", "ACHIEVEMENT_RATE"],
                },
            },
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_domain_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    items = {item["key"]: item for item in normalized["items"]}

    assert normalized["errors"] == []
    assert items["hbm"]["payload"]["condition_by_family"] == {"equipment": {"PKG_TYPE1": "HBM"}}
    assert items["achievement_rate"]["payload"]["required_quantity_terms"] == ["production", "target"]
    assert items["achievement_rate"]["payload"]["output_column"] == "ACHIEVEMENT_RATE"
    assert items["production_wip_target_rate"]["section"] == "analysis_recipes"
    assert items["production_wip_target_rate"]["payload"]["required_dataset_families"] == ["production", "wip", "target"]
    assert items["production_wip_target_rate"]["payload"]["required_columns_by_family"] == {"production": ["WORK_DT", "PRODUCTION"]}
    assert items["production_wip_target_rate"]["payload"]["override_analysis_kinds"] == ["aggregate_join"]
    assert items["production_wip_target_rate"]["payload"]["blocked_filter_fields"] == ["LOT_HOLD_STAT_CD"]
    assert items["production_wip_target_rate"]["payload"]["replace_retrieval_jobs"] is True
    assert items["production_wip_target_rate"]["payload"]["override_step_plan"] is True
    assert items["production_wip_target_rate"]["payload"]["top_n_policy"] == "question_or_default"
    assert items["production_wip_target_rate"]["payload"]["step_plan_template"] == [{"step_id": "join", "operation": "production_wip_target_rate"}]
    assert items["production_wip_target_rate"]["payload"]["output_columns"] == [
        "WIP",
        "PRODUCTION",
        "OUT_PLAN",
        "ACHIEVEMENT_RATE",
    ]


def test_domain_authoring_normalizes_filter_descriptors_to_executable_conditions() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    payload = {"metadata_type": "domain", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "section": "product_terms",
                "key": "pop",
                "payload": {
                    "aliases": "POP 제품",
                    "filters": [
                        {"column": "MODE", "condition": "starts_with LP"},
                        {"column": "PKG_TYPE1", "op": "in", "values": ["LFBGA", "TFBGA"]},
                        {"column": "MCP_NO", "condition": "not null and not empty"},
                    ],
                    "condition_by_family": {
                        "equipment": {"column": "PKG1", "op": "eq", "value": "HBM"},
                    },
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_domain_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    item_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert item_payload["aliases"] == ["POP 제품"]
    assert item_payload["filters"] == {"PKG_TYPE1": ["LFBGA", "TFBGA"]}
    assert item_payload["condition"] == {
        "MODE": {"starts_with": "LP"},
        "MCP_NO": {"exists": True, "not_in": [None, ""]},
    }
    assert item_payload["condition_by_family"] == {"equipment": {"PKG1": ["HBM"]}}


def test_domain_authoring_autofills_single_family_metric_from_worker_text() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    payload = {"metadata_type": "domain", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "section": "metric_terms",
                "key": "wafer_based_performance",
                "payload": {
                    "display_name": "Wafer 기준 실적",
                    "aliases": ["Wafer기준 실적", "Wafer기반 실적", "Wafer Out 수량"],
                    "formula": (
                        "WAFER_OUT_QTY = PRODUCTION / NETDIE_300_CNT when NETDIE_300_CNT > 0; "
                        "FAIL_UNIT_QTY = PRODUCTION when NETDIE_300_CNT is 0 or null"
                    ),
                    "calculation_rule": "행별 계산 후 요청한 group_by 기준으로 합산",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_domain_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    item_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert item_payload["dataset_family"] == "production"
    assert item_payload["required_dataset_families"] == ["production"]
    assert item_payload["required_quantity_terms"] == ["production"]
    assert item_payload["source_columns"] == ["PRODUCTION", "NETDIE_300_CNT"]
    assert item_payload["output_columns"] == ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"]
    assert "NETDIE_300_CNT <= 0" in item_payload["zero_division_rule"]
    assert item_payload["pandas_code_instructions"]


def test_domain_authoring_context_includes_table_catalog_and_main_filters() -> None:
    variables = load_module("langflow_components/domain_authoring_flow/03_domain_authoring_variables_builder.py")
    payload = {
        "raw_text": "장비 대수는 ASSIGN 테이블에서 EQP_ID unique count로 계산해.",
        "refined_text": "장비 대수는 ASSIGN 테이블에서 EQP_ID의 unique count로 계산한다.",
        "existing_items": [{"section": "metric_terms", "key": "equipment_count", "aliases": ["장비 대수"]}],
        "metadata_context": {
            "table_catalog": [
                {
                    "dataset_key": "equipment_status",
                    "dataset_family": "equipment",
                    "description": "장비 ASSIGN 현황",
                    "columns": ["EQPID", "TECH", "DEN"],
                    "filter_mappings": {"EQP_ID": ["EQPID"]},
                }
            ],
            "main_flow_filters": [
                {
                    "filter_key": "EQP_ID",
                    "aliases": ["장비 ID"],
                    "column_candidates": ["EQP_ID", "EQPID"],
                }
            ],
        },
    }

    context = variables.build_domain_authoring_prompt_variables(payload)["authoring_context"]

    assert "Table catalog summary for source-family inference" in context
    assert "equipment_status" in context
    assert "Main flow filter summary for standard field inference" in context
    assert "EQP_ID" in context
    assert variables._metadata_context_counts(payload)["main_flow_filters"] == 1


def test_main_flow_filter_collection_inputs_are_visible() -> None:
    domain_loader = load_module("langflow_components/domain_authoring_flow/00_domain_authoring_request_loader.py")
    table_loader = load_module("langflow_components/table_catalog_authoring_flow/00_table_catalog_authoring_request_loader.py")

    for component_cls in [
        domain_loader.DomainAuthoringRequestLoader,
        table_loader.TableCatalogAuthoringRequestLoader,
    ]:
        input_by_name = {item.name: item for item in component_cls.inputs}
        main_filter_input = input_by_name["main_flow_filter_collection_name"]

        assert main_filter_input.value == "agent_v3_main_flow_filters"
        assert getattr(main_filter_input, "advanced", False) is False


def test_domain_authoring_drops_ungrounded_artifacts_from_wafer_metric() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    payload = {
        "metadata_type": "domain",
        "raw_text": (
            "Wafer기준 실적은 생산량 조회 테이블에서 PRODUCTION/NETDIE_300_CNT로 계산하고, "
            "NETDIE_300_CNT가 0이면 FAIL_UNIT_QTY에 PRODUCTION을 보여줘."
        ),
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {"section": "product_terms", "key": "wafer", "payload": {"aliases": ["Wafer"]}},
            {"section": "quantity_terms", "key": "fail_unit_qty", "payload": {"aliases": ["FAIL_UNIT_QTY"]}},
            {"section": "process_groups", "key": "wafer", "payload": {"processes": []}},
            {"section": "product_key_columns", "key": "default", "payload": {"columns": ["TECH", "DEN"]}},
            {
                "section": "metric_terms",
                "key": "wafer_out_quantity",
                "payload": {
                    "aliases": ["Wafer 기준 실적", "Wafer Out 수량"],
                    "formula": "WAFER_OUT_QTY = PRODUCTION / NETDIE_300_CNT; FAIL_UNIT_QTY = PRODUCTION when denominator is zero",
                },
            },
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_domain_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["errors"] == []
    assert [(item["section"], item["key"]) for item in normalized["items"]] == [("metric_terms", "wafer_out_quantity")]
    metric_payload = normalized["items"][0]["payload"]
    assert metric_payload["dataset_family"] == "production"
    assert metric_payload["required_dataset_families"] == ["production"]
    assert metric_payload["required_quantity_terms"] == ["production"]
    assert metric_payload["source_columns"] == ["PRODUCTION", "NETDIE_300_CNT"]
    assert metric_payload["output_columns"] == ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"]
    warnings_text = "\n".join(normalized["authoring"]["warnings"])
    assert "product_terms/wafer" in warnings_text
    assert "quantity_terms/fail_unit_qty" in warnings_text
    assert "process_groups/wafer" in warnings_text
    assert "product_key_columns item was ignored" in warnings_text


def test_domain_authoring_autofills_equipment_count_metric_from_natural_text() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    payload = {
        "metadata_type": "domain",
        "raw_text": "장비 대수의 경우 장비 ASSIGN테이블에서 EQP_ID의 UNIQUE COUNT를 말한다.",
        "metadata_context": {
            "table_catalog": [
                {
                    "dataset_key": "equipment_status",
                    "dataset_family": "equipment",
                    "description": "장비 ASSIGN 테이블",
                    "columns": ["EQP_ID", "EQP_MODEL"],
                }
            ]
        },
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "section": "metric_terms",
                "key": "equipment_count",
                "payload": {
                    "display_name": "장비 대수",
                    "aliases": ["장비 대수"],
                    "description": "장비 ASSIGN 테이블에서 EQP_ID의 unique count",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_domain_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    metric_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert metric_payload["dataset_family"] == "equipment"
    assert metric_payload["required_dataset_families"] == ["equipment"]
    assert metric_payload["source_columns"] == ["EQP_ID"]
    assert metric_payload["aggregation"] == "nunique"
    assert metric_payload["output_column"] == "EQP_COUNT"
    assert "EQP_COUNT" in metric_payload["output_columns"]


def test_domain_authoring_target_quantity_does_not_use_production_or_input_output() -> None:
    normalizer = load_module("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    llm_json = {
        "items": [
            {
                "section": "quantity_terms",
                "key": "TARGET",
                "payload": {
                    "display_name": "계획 수량",
                    "aliases": ["계획", "스케쥴", "스케줄", "SCHD", "투입계획", "생산계획"],
                    "dataset_family": "target",
                    "quantity_column": "PRODUCTION",
                    "aggregation": "sum",
                    "output_column": "INPUT_QTY",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_domain_authoring_result(llm_json, json.dumps(llm_json, ensure_ascii=False))
    quantity_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert quantity_payload["dataset_family"] == "target"
    assert quantity_payload["quantity_column"] == ["INPUT_PLAN", "OUT_PLAN"]
    assert quantity_payload["source_columns"] == ["INPUT_PLAN", "OUT_PLAN"]
    assert quantity_payload["aggregation"] == "sum"
    assert quantity_payload["output_column"] == "PLAN_QTY"
    assert "condition" not in quantity_payload


def test_domain_writer_allows_resolved_metric_autofill_supplements() -> None:
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    payload = {
        "metadata_type": "domain",
        "items": [
            {
                "section": "metric_terms",
                "key": "wafer_based_performance",
                "payload": {
                    "aliases": ["Wafer기준 실적", "Wafer Out 수량"],
                    "dataset_family": "production",
                    "required_dataset_families": ["production"],
                    "required_quantity_terms": ["production"],
                    "source_columns": ["PRODUCTION", "NETDIE_300_CNT"],
                    "output_columns": ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
                    "formula": "WAFER_OUT_QTY = PRODUCTION / NETDIE_300_CNT; FAIL_UNIT_QTY = PRODUCTION when denominator is zero",
                },
            }
        ],
        "duplicate_decision": {"action": "ask", "requires_user_choice": False},
        "errors": [],
    }
    review_json = {
        "ready_to_save": False,
        "supplement_requests": [
            {"field": "dataset_key", "reason": "데이터셋 식별자가 없습니다."},
            {"field": "dataset_family", "reason": "데이터셋 패밀리 정보가 없습니다."},
            {"field": "required_quantity_terms", "reason": "required_quantity_terms에 production이 필요합니다."},
            {"field": "alias_overlap", "reason": "alias가 겹칩니다: Wafer 기준 실적"},
            {"field": "output_column_name_FOR_FAIL_UNIT_QTY", "reason": "FAIL_UNIT_QTY 컬럼의 정확한 이름과 데이터 타입이 필요합니다."},
        ],
        "item_reviews": [{"section": "metric_terms", "key": "wafer_based_performance", "decision": "needs_fix", "reason": "보강 필요"}],
    }

    result = writer.review_and_write_domain_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []
    assert result["review"]["item_reviews"][0]["decision"] == "pass"
    assert result["write_result"]["status"] == "error"
    assert any("mongo_uri" in error for error in result["write_result"]["errors"])


def test_domain_writer_allows_family_based_quantity_terms_with_nested_supplement_fields() -> None:
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    payload = {
        "metadata_type": "domain",
        "items": [
            {
                "section": "quantity_terms",
                "key": "WIP",
                "payload": {"dataset_family": "wip", "quantity_column": "WIP", "aggregation": "sum", "output_column": "WIP"},
            },
            {
                "section": "quantity_terms",
                "key": "PRODUCTION",
                "payload": {
                    "dataset_family": "production",
                    "quantity_column": "PRODUCTION",
                    "aggregation": "sum",
                    "output_column": "PRODUCTION",
                },
            },
            {
                "section": "quantity_terms",
                "key": "PROCESS_OUTPUT",
                "payload": {
                    "dataset_family": "production",
                    "quantity_column": "PRODUCTION",
                    "aggregation": "sum",
                    "output_column": "PRODUCTION",
                },
            },
            {
                "section": "quantity_terms",
                "key": "INPUT",
                "payload": {
                    "dataset_family": "production",
                    "quantity_column": "PRODUCTION",
                    "aggregation": "sum",
                    "output_column": "INPUT_QTY",
                    "condition": {"OPER_NAME": "INPUT"},
                },
            },
            {
                "section": "quantity_terms",
                "key": "TARGET",
                "payload": {
                    "dataset_family": "target",
                    "quantity_column": ["INPUT_PLAN", "OUT_PLAN"],
                    "source_columns": ["INPUT_PLAN", "OUT_PLAN"],
                    "aggregation": "sum",
                    "output_column": "PLAN_QTY",
                },
            },
        ],
        "duplicate_decision": {"action": "ask", "requires_user_choice": False},
        "errors": [],
    }
    review_json = {
        "ready_to_save": False,
        "supplement_requests": [
            {"field": "quantity_terms.WIP.payload.dataset_key", "reason": "dataset_key가 필요합니다."},
            {"field": "quantity_terms.PRODUCTION.payload.dataset_key", "reason": "dataset_key가 필요합니다."},
            {"field": "quantity_terms.PROCESS_OUTPUT.payload.dataset_key", "reason": "dataset_key가 필요합니다."},
            {"field": "quantity_terms.INPUT.payload.output_column", "reason": "출력 컬럼 충돌 가능성이 있습니다."},
            {"field": "quantity_terms.TARGET.payload.quantity_column", "reason": "계획 컬럼이 필요합니다."},
        ],
        "item_reviews": [{"section": "quantity_terms", "key": "TARGET", "decision": "needs_fix", "reason": "보강 필요"}],
    }

    result = writer.review_and_write_domain_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []
    assert result["review"]["item_reviews"][0]["decision"] == "pass"
    assert result["write_result"]["status"] == "error"
    assert any("mongo_uri" in error for error in result["write_result"]["errors"])


def test_domain_review_ignores_identity_supplements_when_item_has_section_and_key() -> None:
    variables = load_module("langflow_components/domain_authoring_flow/06_domain_review_variables_builder.py")
    writer = load_module("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    payload = {
        "metadata_type": "domain",
        "items": [
            {
                "section": "product_terms",
                "key": "POP_PRODUCT",
                "payload": {"display_name": "POP 제품", "aliases": ["POP"]},
            }
        ],
        "authoring": {
            "missing_information": [
                {"field": "section", "reason": "section이 필요합니다."},
                {"field": "key", "reason": "key가 필요합니다."},
            ]
        },
        "duplicate_decision": {"action": "ask", "requires_user_choice": False},
        "errors": [],
    }

    review_input = json.loads(variables.build_domain_review_prompt_variables(payload)["review_input_json"])
    assert review_input["missing_information"] == []

    review_json = {
        "ready_to_save": False,
        "supplement_requests": [
            {"field": "section", "reason": "section이 필요합니다."},
            {"field": "key", "reason": "key가 필요합니다."},
        ],
    }
    result = writer.review_and_write_domain_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []


def test_table_catalog_authoring_requires_source_config_and_detects_same_dataset_key() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/table_catalog_authoring_flow/05_table_catalog_similarity_checker.py")

    payload = {
        "metadata_type": "table_catalog",
        "existing_items": [{"dataset_key": "wip_today", "dataset_family": "wip", "date_scope": "current_day", "source_type": "oracle"}],
        "duplicate_decision": {"action": "ask"},
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "dataset_key": "wip_today",
                "payload": {
                    "display_name": "WIP Today",
                    "dataset_family": "wip",
                    "date_scope": "current_day",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT WORK_DT, WIP FROM PKG_WIP_TODAY WHERE WORK_DT = {DATE}",
                    },
                    "columns": ["WORK_DT", "WIP"],
                    "filter_mappings": {"DATE": ["WORK_DT"]},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }
    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    assert normalized["errors"] == []
    assert normalized["items"][0]["dataset_key"] == "wip_today"

    checked = similarity.check_table_catalog_similarity(normalized, "ask")
    assert checked["existing_matches"][0]["match_type"] == "same_dataset_key"
    assert checked["duplicate_decision"]["requires_user_choice"] is True


def test_table_catalog_authoring_context_includes_main_flow_filters() -> None:
    loader = load_module("langflow_components/table_catalog_authoring_flow/00_table_catalog_authoring_request_loader.py")
    variables = load_module("langflow_components/table_catalog_authoring_flow/03_table_catalog_authoring_variables_builder.py")
    payload = loader.build_table_catalog_authoring_request(
        raw_text="production_today 데이터셋은 WORK_DATE, PKG_TYP1, PRODUCTION 컬럼을 사용한다.",
        load_existing="false",
    )
    payload["existing_items"] = [
        {
            "dataset_key": "production_today",
            "dataset_family": "production",
            "columns": ["WORK_DATE", "PKG_TYP1", "PRODUCTION"],
        }
    ]
    payload["metadata_context"]["main_flow_filters"] = [
        {
            "filter_key": "DATE",
            "aliases": ["일자", "기준일"],
            "column_candidates": ["DATE", "WORK_DATE"],
            "semantic_role": "date",
        },
        {
            "filter_key": "PKG_TYPE1",
            "aliases": ["패키지1"],
            "column_candidates": ["PKG_TYPE1", "PKG_TYP1", "PKG1"],
            "semantic_role": "product_attribute",
        },
    ]

    context = variables.build_table_catalog_authoring_prompt_variables(payload)["authoring_context"]

    assert payload["mongo_config"]["main_flow_filter_collection"] == "agent_v3_main_flow_filters"
    assert "Registered main flow filter summary" in context
    assert "DATE" in context
    assert "WORK_DATE" in context
    assert "PKG_TYPE1" in context
    assert "PKG_TYP1" in context
    assert variables._metadata_context_counts(payload)["main_flow_filters"] == 2


def test_table_catalog_authoring_normalizes_detail_columns_and_filter_mappings() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    payload = {"metadata_type": "table_catalog", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "dataset_key": "target",
                "payload": {
                    "display_name": "Production Plan",
                    "dataset_family": "target",
                    "source_type": "goodocs",
                    "source_config": {
                        "source_type": "goodocs",
                        "doc_id": "TARGET_DOC",
                        "sheet_name": "daily_target",
                    },
                    "date_format": "YYYY-MM-DD",
                    "columns": ["DATE", "MODE", "OUT_PLAN"],
                    "filter_mappings": {"DATE": "DATE", "MODE": ["MODE"]},
                    "required_param_mappings": {"DATE": "DATE"},
                    "standard_column_aliases": {"OUT_PLAN": "OUT계획", "PKG_TYPE1": ["PKG1"]},
                    "default_detail_columns": "DATE",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["errors"] == []
    item_payload = normalized["items"][0]["payload"]
    assert item_payload["filter_mappings"] == {"DATE": ["DATE"], "MODE": ["MODE"]}
    assert item_payload["required_params"] == []
    assert item_payload["required_param_mappings"] == {}
    assert item_payload["standard_column_aliases"] == {"PKG_TYPE1": ["PKG1"]}
    assert item_payload["default_detail_columns"] == ["DATE"]
    assert item_payload["date_format"] == "YYYY-MM-DD"


def test_table_catalog_authoring_repairs_filter_mappings_from_standard_aliases() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    payload = {"metadata_type": "table_catalog", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "dataset_key": "production_today",
                "payload": {
                    "display_name": "Production Today",
                    "dataset_family": "production",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT DENSITY, PKG1, PKG2, PRODUCTION FROM T WHERE WORK_DT = {DATE}",
                    },
                    "columns": ["DENSITY", "PKG1", "PKG2", "PRODUCTION"],
                    "filter_mappings": {"DEN": ["DEN"], "PKG_TYPE1": ["PKG_TYPE1"], "PKG_TYPE2": ["PKG_TYPE2"]},
                    "standard_column_aliases": {"DEN": ["DENSITY"], "PKG_TYPE1": ["PKG1"], "PKG_TYPE2": ["PKG2"]},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    item_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert item_payload["filter_mappings"]["DEN"] == ["DENSITY"]
    assert item_payload["filter_mappings"]["PKG_TYPE1"] == ["PKG1"]
    assert item_payload["filter_mappings"]["PKG_TYPE2"] == ["PKG2"]


def test_table_catalog_authoring_backfills_goodocs_doc_id_without_sheet_or_query() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = """목표2 계획 데이터는 target으로 등록해줘.
화면에 보일 이름은 Target2 Goodocs Plan이면 돼.
일자별 계획 정보를 담고 있는 이력 데이터야.
Goodocs 목표2 문서에서 일자와 제품 속성별 INPUT계획, OUT계획을 가져오는 데이터야.
이 데이터는 Goodocs source이고 별도 필수 조회 파라미터는 없어.
DATE 값 형식은 YYYY-MM-DD야. 필터 조건 걸 때 이 부분을 잘 고려해서 구현해줘야 해
위 DATE 값 형식은 target dataset의 table catalog metadata에 date_format=YYYY-MM-DD로 저장되어야 해.
기본 목표 수량은 OUT계획이고, 계획/목표 데이터로 사용해.
계획 수량은 INPUT계획과 OUT계획 두 컬럼을 모두 사용해. 두 컬럼 모두 분석 수량으로 쓰는 계획 수량 컬럼이야.
Goodocs 문서 ID는 131314153513515135 이야
목표2 문서에는 DATE, Mode, DEN, TECH, PKG1, PKG2, LEAD, ORG, MCP NO, INPUT계획, OUT계획 항목이 있어.
INPUT계획은 투입 계획 수량이고 INPUT_PLAN, 투입계획이라고도 불러.
OUT계획은 산출 계획 수량이고 TARGET, OUT_PLAN, 생산목표라고도 불러.
filter_mappings는 DATE -> DATE, MODE -> Mode, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, LEAD -> LEAD, MCP_NO -> MCP NO로 연결해줘."""
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": raw_text,
        "refined_text": "Goodocs 목표2 문서에서 일자와 제품 속성별 계획 정보를 가져오는 target 데이터입니다.",
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "dataset_key": "target2_plan",
                "payload": {
                    "display_name": "Target2 Goodocs Plan",
                    "dataset_family": "target",
                    "date_scope": "history",
                    "source_type": "goodocs",
                    "source_config": {"source_type": "goodocs"},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["DATE"]},
                    "columns": ["DATE", "OUT계획"],
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["errors"] == []
    item = normalized["items"][0]
    item_payload = item["payload"]
    assert item["dataset_key"] == "target"
    assert item_payload["source_type"] == "goodocs"
    assert item_payload["source_config"]["doc_id"] == "131314153513515135"
    assert "sheet_name" not in item_payload["source_config"]
    assert "db_key" not in item_payload["source_config"]
    assert "query_template" not in item_payload["source_config"]
    assert item_payload["required_params"] == []
    assert item_payload["required_param_mappings"] == {}
    assert item_payload["date_format"] == "YYYY-MM-DD"
    assert item_payload["primary_quantity_column"] == ["INPUT계획", "OUT계획"]
    assert item_payload["columns"] == ["DATE", "Mode", "DEN", "TECH", "PKG1", "PKG2", "LEAD", "ORG", "MCP NO", "INPUT계획", "OUT계획"]
    assert item_payload["filter_mappings"]["PKG_TYPE1"] == ["PKG1"]
    assert item_payload["filter_mappings"]["MCP_NO"] == ["MCP NO"]
    assert item_payload["standard_column_aliases"] == {}
    assert "INPUT_PLAN" not in item_payload["standard_column_aliases"]
    assert "OUT_PLAN" not in item_payload["standard_column_aliases"]
    assert "TARGET" not in item_payload["standard_column_aliases"]


def test_table_catalog_authoring_preserves_spaced_plan_quantity_columns() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = """PKG 계획 데이터는 target으로 등록해줘.
화면에 보일 이름은 PKG Target Goodocs Plan이면 돼.
Goodocs PKG 계획 문서에서 일자와 제품 속성별 INPUT계획, OUT계획을 가져오는 데이터야.
이 데이터는 Goodocs source이고 별도 필수 조회 파라미터는 없어.
이게 중요한데 이 데이터에서 사용하는 DATE형식은 'YYYYMMDD'가 아니라 'YYYY-MM-DD'형식이라서 형식 변환이 필요해
계획 수량은 'INPUT 계획'과 'OUT 계획' 두 컬럼에 있는 값을 모두 사용해. 두 컬럼 모두 분석 수량으로 쓰는 계획 수량 컬럼이야.
Goodocs 문서 ID는 1231231412412512515 이야
목표2 문서에는 DATE, Mode, DEN, TECH, PKG1, PKG2, LEAD, ORG, MCP NO, INPUT 계획, OUT 계획 컬럼이 있어."""
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": raw_text,
        "refined_text": raw_text,
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "payload": {
                    "display_name": "PKG Target Goodocs Plan",
                    "dataset_family": "target",
                    "source_type": "goodocs",
                    "source_config": {"source_type": "goodocs"},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["DATE"]},
                    "primary_quantity_column": ["INPUT계획", "OUT계획"],
                    "columns": ["DATE", "Mode", "DEN", "TECH", "PKG1", "PKG2", "LEAD", "ORG", "MCP NO", "INPUT 계획", "OUT 계획"],
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    item = normalized["items"][0]
    item_payload = item["payload"]
    assert normalized["errors"] == []
    assert item["dataset_key"] == "target"
    assert item_payload["source_config"]["doc_id"] == "1231231412412512515"
    assert item_payload["required_params"] == []
    assert item_payload["required_param_mappings"] == {}
    assert item_payload["primary_quantity_column"] == ["INPUT 계획", "OUT 계획"]
    assert item_payload["columns"] == ["DATE", "Mode", "DEN", "TECH", "PKG1", "PKG2", "LEAD", "ORG", "MCP NO", "INPUT 계획", "OUT 계획"]


def test_table_catalog_authoring_parses_inline_columns_without_eating_next_fields() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = (
        "dummy yield sheet를 table catalog에 등록해줘. "
        "dataset_key=dummy_yield_goodocs, source_type=goodocs, doc_id=5555666677778888, dataset_family=quality야. "
        "required_params는 DATE야. DATE format은 YYYY-MM-DD. "
        "columns는 DATE, MODE, DEN, YIELD_RATE, FAIL_QTY야. "
        "primary_quantity_column은 YIELD_RATE야. "
        "filter_mappings는 DATE -> DATE, MODE -> MODE, DEN -> DEN야."
    )
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": raw_text,
        "refined_text": raw_text,
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "dataset_key": "dummy_yield_goodocs",
                "payload": {
                    "display_name": "Dummy Yield Goodocs",
                    "dataset_family": "quality",
                    "source_type": "goodocs",
                    "source_config": {"source_type": "goodocs"},
                    "columns": [],
                    "primary_quantity_column": "YIELD_RATE야",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["errors"] == []
    item_payload = normalized["items"][0]["payload"]
    assert item_payload["columns"] == ["DATE", "MODE", "DEN", "YIELD_RATE", "FAIL_QTY"]
    assert item_payload["primary_quantity_column"] == "YIELD_RATE"
    assert item_payload["filter_mappings"]["DEN"] == ["DEN"]


def test_table_catalog_authoring_accepts_single_item_object_response() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = """dummy unit 이력 데이터셋을 datalake source로 등록해줘. dataset_key=dummy_unit_history, dataset_family=unit이야. required_params는 DATE고 date_format은 YYYYMMDD야. primary_quantity_column은 UNIT_QTY야.
query_template:
SELECT DATE, UNIT_ID, LOT_ID, OPER_NAME, UNIT_QTY
FROM dummy_unit_history
WHERE DATE = {DATE}
filter_mappings: DATE -> DATE, LOT_ID -> LOT_ID, OPER_NAME -> OPER_NAME"""
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": raw_text,
        "refined_text": raw_text,
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "dataset_key": "dummy_unit_history",
        "payload": {
            "display_name": "Dummy Unit History",
            "dataset_family": "unit",
            "source_type": "datalake",
            "source_config": {
                "source_type": "datalake",
                "query_template": "SELECT DATE, UNIT_ID, LOT_ID, OPER_NAME, UNIT_QTY\nFROM dummy_unit_history\nWHERE DATE = {DATE}",
            },
            "required_params": ["DATE"],
            "primary_quantity_column": "UNIT_QTY",
            "columns": ["DATE", "UNIT_ID", "LOT_ID", "OPER_NAME", "UNIT_QTY"],
        },
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["errors"] == []
    assert len(normalized["items"]) == 1
    item = normalized["items"][0]
    assert item["dataset_key"] == "dummy_unit_history"
    assert item["payload"]["source_type"] == "datalake"
    assert item["payload"]["source_config"]["query_template"].startswith("SELECT DATE")
    assert item["payload"]["primary_quantity_column"] == "UNIT_QTY"


def test_table_catalog_authoring_does_not_make_date_filter_required_without_placeholder_or_explicit_text() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = """dataset_key는 production_snapshot이고 생산 snapshot 데이터야.
source는 oracle, db_key는 PNT_RPT야.
query_template:
SELECT WORK_DATE, OPER_NAME, PRODUCTION
FROM PKG_PRODUCTION_SNAPSHOT

filter_mappings는 DATE -> WORK_DATE, OPER_NAME -> OPER_NAME로 연결해줘.
DATE 형식은 YYYYMMDD야."""
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": raw_text,
        "refined_text": "production_snapshot oracle dataset with DATE filter mapping.",
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "dataset_key": "production_snapshot",
                "payload": {
                    "display_name": "Production Snapshot",
                    "dataset_family": "production",
                    "date_scope": "snapshot",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT WORK_DATE, OPER_NAME, PRODUCTION\nFROM PKG_PRODUCTION_SNAPSHOT",
                    },
                    "columns": ["WORK_DATE", "OPER_NAME", "PRODUCTION"],
                    "filter_mappings": {"DATE": ["WORK_DATE"], "OPER_NAME": ["OPER_NAME"]},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["WORK_DATE"]},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    item_payload = normalized["items"][0]["payload"]
    assert item_payload["filter_mappings"]["DATE"] == ["WORK_DATE"]
    assert item_payload["date_format"] == "YYYYMMDD"
    assert item_payload["required_params"] == []
    assert item_payload["required_param_mappings"] == {}


def test_table_catalog_authoring_drops_date_format_without_date_reference() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = """dataset_key는 equipment_status이고 장비 현황 데이터야.
source는 oracle, db_key는 PNT_RPT야.
DATE 형식은 YYYYMMDD야.

query_template:
SELECT EQPID, MODE, DEN
FROM EQUIPMENT_STATUS

filter_mappings는 EQP_ID -> EQPID, MODE -> MODE, DEN -> DEN로 연결해줘."""
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": raw_text,
        "refined_text": "equipment_status dataset without date column.",
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "dataset_key": "equipment_status",
                "payload": {
                    "display_name": "Equipment Status",
                    "dataset_family": "equipment",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT EQPID, MODE, DEN\nFROM EQUIPMENT_STATUS",
                    },
                    "date_format": "YYYYMMDD",
                    "columns": ["EQPID", "MODE", "DEN"],
                    "filter_mappings": {"EQP_ID": ["EQPID"], "MODE": ["MODE"], "DEN": ["DEN"]},
                    "required_params": [],
                    "required_param_mappings": {},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    item_payload = normalized["items"][0]["payload"]
    assert "date_format" not in item_payload
    assert "DATE" not in item_payload["filter_mappings"]
    assert item_payload["required_params"] == []


def test_table_catalog_authoring_does_not_default_missing_source_type_to_dummy() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": "dataset_key는 unknown_source이고 수량 컬럼은 QTY야.",
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "dataset_key": "unknown_source",
                "payload": {
                    "display_name": "Unknown Source",
                    "dataset_family": "other",
                    "columns": ["QTY"],
                    "primary_quantity_column": "QTY",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    item_payload = normalized["items"][0]["payload"]
    assert item_payload.get("source_type") in (None, "")
    assert item_payload["source_config"] == {}
    assert any("source_type" in error for error in normalized["errors"])


def test_table_catalog_authoring_backfills_dataset_key_from_register_sentence() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = """PKG 계획 데이터는 target으로 등록해줘.
화면에 보일 이름은 PKG Target Goodocs Plan이면 돼.
Goodocs 문서 ID는 12321232312441423124124 이야
목표2 문서에는 DATE, Mode, DEN, TECH, PKG1, PKG2, LEAD, ORG, MCP NO, INPUT계획, OUT계획 컬럼이 있어."""
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": raw_text,
        "refined_text": raw_text,
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "payload": {
                    "display_name": "PKG Target Goodocs Plan",
                    "dataset_family": "target",
                    "source_type": "goodocs",
                    "source_config": {"source_type": "goodocs"},
                    "columns": ["DATE", "Mode", "DEN", "TECH", "PKG1", "PKG2", "LEAD", "ORG", "MCP NO", "INPUT계획", "OUT계획"],
                },
            }
        ],
        "missing_information": [{"field": "dataset_key", "reason": "사용자가 dataset_key를 입력하지 않았습니다."}],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["items"][0]["dataset_key"] == "target"
    assert normalized["items"][0]["key"] == "target"
    assert not any("dataset_key" in error for error in normalized["errors"])


def test_table_catalog_authoring_backfills_structured_fields_from_raw_text() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = """당일용 생산 실적 데이터는 production_today로 등록해줘.
화면에 보일 이름은 Production Today이면 돼.
당일 생산 실적 질문에 사용하는 Oracle 데이터야.
production_today는 production 계열의 당일용 생산 실적 source야.
조회할 때 DATE 값은 WORK_DATE 컬럼에 넣어서 조회하고, DATE는 조회 필수 기준일이야.
DATE는 YYYYMMDD 형식이야.
수량은 PRODUCTION 컬럼을 사용하고, 이 값은 생산량이야.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT A.WORK_DATE, A.SHIFT, A.FACTORY, A.FAB, A.FAMILY, A.MODE, A.DEN, A.TECH, A.ORG, A.PKG_TYP1, A.PKG_TYP2, A.LEAD, A.MCP_NO, A.TSV_DIE_TYP, A.DEVICE, A.DEVICE_DESC, A.DIE_ATTACH_QTY, A.NETDIE_300_CNT, A.OPER, A.OPER_NAME, A.OPER_SEQ, PRODUCTION
FROM PRODUCTION_TODAY A
WHERE 1=1
AND A.WORK_DATE = {DATE}
AND PRODUCTION > 0

filter_mappings는 DATE -> WORK_DATE, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYP1, PKG_TYPE2 -> PKG_TYP2, LEAD -> LEAD, MCP_NO -> MCP_NO, TSV_DIE_TYP -> TSV_DIE_TYP, DEVICE_DESC -> DEVICE_DESC, OPER_NUM -> OPER, OPER_NAME -> OPER_NAME로 연결해줘."""
    payload = {
        "metadata_type": "table_catalog",
        "raw_text": raw_text,
        "refined_text": "Oracle 데이터베이스의 PNT_RPT 스키마에 있는 PRODUCTION_TODAY 테이블에서 당일 생산 실적 데이터를 제공합니다.",
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "dataset_key": "production_today_detailed",
                "payload": {
                    "display_name": "Production Today (Detailed)",
                    "dataset_family": "production",
                    "date_scope": "current_day",
                    "source_type": "oracle",
                    "source_config": {"source_type": "oracle", "db_key": "PNT_RPT"},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["WORK_DATE"]},
                    "date_format": "YYYYMMDD",
                    "primary_quantity_column": "PRODUCTION",
                    "filter_mappings": {"DATE": ["WORK_DATE"]},
                    "columns": ["WORK_DATE", "PRODUCTION"],
                    "standard_column_aliases": {},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["errors"] == []
    item = normalized["items"][0]
    item_payload = item["payload"]
    assert item["dataset_key"] == "production_today"
    assert "FROM PRODUCTION_TODAY" in item_payload["source_config"]["query_template"]
    assert item_payload["columns"] == [
        "WORK_DATE",
        "SHIFT",
        "FACTORY",
        "FAB",
        "FAMILY",
        "MODE",
        "DEN",
        "TECH",
        "ORG",
        "PKG_TYP1",
        "PKG_TYP2",
        "LEAD",
        "MCP_NO",
        "TSV_DIE_TYP",
        "DEVICE",
        "DEVICE_DESC",
        "DIE_ATTACH_QTY",
        "NETDIE_300_CNT",
        "OPER",
        "OPER_NAME",
        "OPER_SEQ",
        "PRODUCTION",
    ]
    assert item_payload["filter_mappings"]["OPER_NAME"] == ["OPER_NAME"]
    assert item_payload["filter_mappings"]["MODE"] == ["MODE"]
    assert item_payload["filter_mappings"]["PKG_TYPE1"] == ["PKG_TYP1"]
    assert item_payload["filter_mappings"]["OPER_NUM"] == ["OPER"]
    assert item_payload["required_param_mappings"]["DATE"] == ["WORK_DATE"]
    assert item_payload["date_format"] == "YYYYMMDD"
    assert item_payload["primary_quantity_column"] == "PRODUCTION"


def test_table_catalog_authoring_prefers_raw_query_template_over_llm_mutation() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_query = "\n".join(
        [
            "SELECT WORK_DT, PKG_TYPE1, PKG_TYPE2, PRODUCTION",
            "FROM DATA_EXTINF_MAS",
            "WHERE WORK_DT = {DATE}",
        ]
    )
    raw_text = f"""dataset_key=production_today
source_type=oracle
db_key=PNT_RPT
dataset_family=production

query_template:
{raw_query}

filter_mappings: DATE -> WORK_DT, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2"""
    payload = {"metadata_type": "table_catalog", "raw_text": raw_text, "refined_text": raw_text, "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "dataset_key": "production_today",
                "payload": {
                    "display_name": "Production Today",
                    "dataset_family": "production",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT WORK_DT, PKG_TYPE1,, PKG_TYPE2, PRODUCTION FROM DATA_EXT_INF_MAS WHERE WORK_DT = {DATE}",
                    },
                    "columns": ["WORK_DT", "PKG_TYPE1", "PKG_TYPE2", "PRODUCTION"],
                    "filter_mappings": {"DATE": ["WORK_DT"], "PKG_TYPE1": ["PKG_TYPE1"], "PKG_TYPE2": ["PKG_TYPE2"]},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["WORK_DT"]},
                    "primary_quantity_column": "PRODUCTION",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["errors"] == []
    stored_query = normalized["items"][0]["payload"]["source_config"]["query_template"]
    assert stored_query == raw_query
    assert "DATA_EXT_INF_MAS" not in stored_query
    assert "PKG_TYPE1,," not in stored_query


def test_table_catalog_authoring_preserves_raw_query_template_with_blank_lines() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_query = "\n".join(
        [
            "WITH base AS (",
            "  SELECT WORK_DT, PROD_QTY",
            "  FROM PRODUCTION_RAW",
            "  WHERE WORK_DT = {DATE}",
            "),",
            "",
            "final_rows AS (",
            "  SELECT WORK_DT, SUM(PROD_QTY) AS PRODUCTION",
            "  FROM base",
            "  GROUP BY WORK_DT",
            ")",
            "SELECT WORK_DT, PRODUCTION",
            "FROM final_rows",
        ]
    )
    raw_text = f"""dataset_key=production_today
source_type=oracle
db_key=PNT_RPT
dataset_family=production

query_template:
{raw_query}

filter_mappings: DATE -> WORK_DT"""
    payload = {"metadata_type": "table_catalog", "raw_text": raw_text, "refined_text": raw_text, "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "dataset_key": "production_today",
                "payload": {
                    "display_name": "Production Today",
                    "dataset_family": "production",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "WITH base AS ( SELECT ... ) SELECT WORK_DT, PRODUCTION FROM final_rows",
                    },
                    "columns": ["WORK_DT"],
                    "filter_mappings": {"DATE": ["WORK_DT"]},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["WORK_DT"]},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    item_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert item_payload["source_config"]["query_template"] == raw_query
    assert item_payload["columns"] == ["WORK_DT", "PRODUCTION"]
    assert normalized["query_template_checks"][0]["line_count"] == len(raw_query.splitlines())
    assert normalized["query_template_checks"][0]["contains_truncation_marker"] is False


def test_table_catalog_authoring_blocks_truncated_query_template_without_raw_sql() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    payload = {"metadata_type": "table_catalog", "raw_text": "dataset_key=production_today", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "dataset_key": "production_today",
                "payload": {
                    "display_name": "Production Today",
                    "dataset_family": "production",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT ... FROM PRODUCTION_TABLE WHERE WORK_DT = {DATE}",
                    },
                    "columns": ["WORK_DT", "PRODUCTION"],
                    "filter_mappings": {"DATE": ["WORK_DT"]},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    assert normalized["query_template_checks"][0]["contains_truncation_marker"] is True
    assert any("query_template" in error for error in normalized["errors"])


def test_table_catalog_authoring_extracts_columns_from_top_level_sql_select() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    query = """
WITH base AS (
  SELECT WORK_DT, INTERNAL_ONLY, PROD_QTY
  FROM PRODUCTION_RAW
  WHERE WORK_DT = {DATE}
),
ranked AS (
  SELECT WORK_DT, PROD_QTY, ROW_NUMBER() OVER (PARTITION BY WORK_DT ORDER BY PROD_QTY DESC) AS RN
  FROM base
)
SELECT
  r.WORK_DT,
  r.PROD_QTY AS PRODUCTION,
  CASE WHEN r.PROD_QTY > 0 THEN 'Y' ELSE 'N' END AS HAS_OUTPUT,
  (SELECT MAX(o.OPER_SEQ) FROM OPER_DIM o WHERE o.WORK_DT = r.WORK_DT) AS MAX_OPER_SEQ
FROM ranked r
WHERE r.RN = 1
"""

    assert normalizer._columns_from_query(query) == ["WORK_DT", "PRODUCTION", "HAS_OUTPUT", "MAX_OPER_SEQ"]


def test_table_catalog_authoring_expands_inline_view_star_columns() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    query = """
SELECT *
FROM (
  SELECT LOT_ID, HOLD_CD AS HOLD_CODE, IN_TAT
  FROM HOLD_HISTORY
  WHERE WORK_DT = {DATE}
) hold_rows
"""

    assert normalizer._columns_from_query(query) == ["LOT_ID", "HOLD_CODE", "IN_TAT"]


def test_table_catalog_authoring_ignores_sql_comments_when_extracting_columns() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    query = """
SELECT A.WORK_DATE,
       A.OPER_NAME,
       A.OPER_SEQ--, A.STACK_SEQ
       , ROUND(SUM(A.WIP),1) AS WIP
       /*, A.INTERNAL_COMMENTED_COLUMN */
FROM WIP_TODAY A
WHERE A.WORK_DATE = {DATE}
GROUP BY A.WORK_DATE, A.OPER_NAME, A.OPER_SEQ
"""

    assert normalizer._columns_from_query(query) == ["WORK_DATE", "OPER_NAME", "OPER_SEQ", "WIP"]


def test_table_catalog_authoring_repairs_columns_that_include_sql_comment_artifacts() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_query = "\n".join(
        [
            "SELECT A.WORK_DATE,",
            "       A.OPER_NAME,",
            "       A.OPER_SEQ--, A.STACK_SEQ",
            "       , ROUND(SUM(A.WIP),1) AS WIP",
            "FROM WIP_TODAY A",
            "WHERE A.WORK_DATE = {DATE}",
            "GROUP BY A.WORK_DATE, A.OPER_NAME, A.OPER_SEQ",
        ]
    )
    raw_text = f"""dataset_key=wip_today
source_type=oracle
db_key=PNT_RPT
dataset_family=wip

query_template:
{raw_query}

filter_mappings: DATE -> WORK_DATE, OPER_NAME -> OPER_NAME"""
    payload = {"metadata_type": "table_catalog", "raw_text": raw_text, "refined_text": raw_text, "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "dataset_key": "wip_today",
                "payload": {
                    "display_name": "WIP Today",
                    "dataset_family": "wip",
                    "source_type": "oracle",
                    "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": raw_query},
                    "required_params": ["DATE"],
                    "required_param_mappings": {"DATE": ["WORK_DATE"]},
                    "filter_mappings": {"DATE": ["WORK_DATE"], "OPER_NAME": ["OPER_NAME"]},
                    "columns": ["WORK_DATE", "OPER_NAME", "OPER_SEQ--", "STACK_SEQ", "WIP"],
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_table_catalog_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))

    item_payload = normalized["items"][0]["payload"]
    assert item_payload["source_config"]["query_template"] == raw_query
    assert item_payload["columns"] == ["WORK_DATE", "OPER_NAME", "OPER_SEQ", "WIP"]


def test_table_catalog_writer_does_not_block_missing_default_detail_columns() -> None:
    writer = load_module("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    payload = {
        "metadata_type": "table_catalog",
        "items": [{"dataset_key": "production_today", "payload": {"columns": ["WORK_DT", "PRODUCTION"]}}],
        "duplicate_decision": {"action": "ask", "requires_user_choice": False},
        "errors": [],
    }
    review_json = {
        "ready_to_save": True,
        "supplement_requests": [
            {
                "field": "default_detail_columns",
                "reason": "상세 조회 시 기본적으로 표시될 컬럼에 대한 정보가 누락되었습니다.",
            }
        ],
    }

    result = writer.review_and_write_table_catalog_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []


def test_table_catalog_review_ignores_dataset_key_supplement_when_item_has_key() -> None:
    variables = load_module("langflow_components/table_catalog_authoring_flow/06_table_catalog_review_variables_builder.py")
    writer = load_module("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    payload = {
        "metadata_type": "table_catalog",
        "items": [{"dataset_key": "target", "payload": {"columns": ["DATE", "OUT계획"]}}],
        "authoring": {
            "missing_information": [
                {"field": "dataset_key", "reason": "사용자가 dataset_key를 입력하지 않아 시스템이 고유 식별자를 생성할 수 없습니다."}
            ]
        },
        "duplicate_decision": {"action": "ask", "requires_user_choice": False},
        "errors": [],
    }

    review_input = json.loads(variables.build_table_catalog_review_prompt_variables(payload)["review_input_json"])
    assert review_input["missing_information"] == []

    review_json = {
        "ready_to_save": False,
        "supplement_requests": [
            {
                "field": "dataset_key",
                "reason": "사용자가 dataset_key를 입력하지 않아 시스템이 고유 식별자를 생성할 수 없습니다.",
            }
        ],
    }
    result = writer.review_and_write_table_catalog_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []


def test_table_catalog_writer_blocks_truncated_query_template_even_when_review_passes() -> None:
    writer = load_module("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    payload = {
        "metadata_type": "table_catalog",
        "items": [
            {
                "dataset_key": "production_today",
                "payload": {
                    "display_name": "Production Today",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT WORK_DT\nFROM PRODUCTION_TABLE\nWHERE ...",
                    },
                    "columns": ["WORK_DT"],
                },
            }
        ],
        "duplicate_decision": {"action": "replace", "requires_user_choice": False},
        "errors": [],
    }
    review_json = {"ready_to_save": True, "supplement_requests": [], "item_reviews": [{"decision": "pass"}]}

    result = writer.review_and_write_table_catalog_payload(
        payload,
        json.dumps(review_json, ensure_ascii=False),
        mongo_uri="mongodb://example",
    )

    assert result["write_result"]["status"] == "error"
    assert result["write_result"]["saved_count"] == 0
    assert any("query_template" in error for error in result["write_result"]["errors"])


def test_table_catalog_writer_does_not_block_optional_goodocs_sheet_or_query_fields() -> None:
    writer = load_module("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    payload = {
        "metadata_type": "table_catalog",
        "items": [
            {
                "dataset_key": "target",
                "payload": {
                    "display_name": "Target2 Goodocs Plan",
                    "source_type": "goodocs",
                    "source_config": {"source_type": "goodocs", "doc_id": "131314153513515135"},
                    "columns": ["DATE", "OUT계획"],
                },
            }
        ],
        "duplicate_decision": {"action": "ask", "requires_user_choice": False},
        "errors": [],
    }
    review_json = {
        "ready_to_save": False,
        "supplement_requests": [
            {"field": "source_config.sheet_name", "reason": "Goodocs 문서에서 데이터를 읽으려면 시트 이름이 필요합니다."},
            {"field": "source_config.query_template", "reason": "스키마에 query_template이 필요합니다."},
            {"field": "source_config.db_key", "reason": "db_key가 필요합니다."},
        ],
        "item_reviews": [{"dataset_key": "target", "decision": "needs_fix", "reason": "sheet_name이 없습니다."}],
    }

    result = writer.review_and_write_table_catalog_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []
    assert result["review"]["item_reviews"][0]["decision"] == "pass"


def test_table_catalog_writer_allows_false_review_without_actionable_blockers() -> None:
    writer = load_module("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    payload = {
        "metadata_type": "table_catalog",
        "items": [
            {
                "dataset_key": "production_today",
                "payload": {
                    "display_name": "Production Today",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT WORK_DT, PRODUCTION FROM PRODUCTION_TODAY WHERE WORK_DT = {DATE}",
                    },
                    "columns": ["WORK_DT", "PRODUCTION"],
                    "filter_mappings": {"DATE": ["WORK_DT"]},
                },
            }
        ],
        "duplicate_decision": {"action": "replace", "requires_user_choice": False},
        "errors": [],
    }
    review_json = {
        "ready_to_save": False,
        "supplement_requests": [],
        "item_reviews": [
            {
                "dataset_key": "production_today",
                "decision": "needs_fix",
                "reason": "기본 상세 컬럼 정보가 누락되었고 기존 dataset_key가 있습니다.",
            }
        ],
    }

    result = writer.review_and_write_table_catalog_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []
    assert result["review"]["item_reviews"][0]["decision"] == "pass"
    assert result["write_result"]["status"] == "error"
    assert any("mongo_uri" in item for item in result["write_result"]["errors"])


def test_table_catalog_writer_ignores_resolved_mapping_mismatch_when_replace_selected() -> None:
    writer = load_module("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    response = load_module("langflow_components/table_catalog_authoring_flow/08_table_catalog_authoring_response_builder.py")
    payload = {
        "metadata_type": "table_catalog",
        "items": [
            {
                "dataset_key": "production_today",
                "payload": {
                    "display_name": "Production Today",
                    "source_type": "oracle",
                    "source_config": {
                        "source_type": "oracle",
                        "db_key": "PNT_RPT",
                        "query_template": "SELECT DENSITY, PKG1, PKG2, PRODUCTION FROM T WHERE WORK_DT = {DATE}",
                    },
                    "columns": ["DENSITY", "PKG1", "PKG2", "PRODUCTION"],
                    "filter_mappings": {"DEN": ["DENSITY"], "PKG_TYPE1": ["PKG1"], "PKG_TYPE2": ["PKG2"]},
                    "standard_column_aliases": {"DEN": ["DENSITY"], "PKG_TYPE1": ["PKG1"], "PKG_TYPE2": ["PKG2"]},
                },
            }
        ],
        "existing_matches": [
            {
                "match_type": "same_dataset_key",
                "reason": "같은 dataset_key의 기존 table catalog 정보가 있습니다.",
                "existing": {"dataset_key": "production_today"},
            }
        ],
        "duplicate_decision": {"action": "replace", "requires_user_choice": False},
        "errors": [],
    }
    review_json = {
        "ready_to_save": False,
        "supplement_requests": [
            {"field": "DEN", "reason": "필터 매핑에 DEN이 지정되었지만 최종 SELECT에 DENSITY 컬럼만 존재합니다."},
            {"field": "PKG_TYPE1", "reason": "PKG_TYPE1 매핑이 있지만 최종 SELECT에 PKG1 컬럼만 있습니다."},
            {"field": "PKG_TYPE2", "reason": "PKG_TYPE2 매핑이 있지만 최종 SELECT에 PKG2 컬럼만 있습니다."},
        ],
        "item_reviews": [{"dataset_key": "production_today", "decision": "needs_fix", "reason": "mapping mismatch"}],
    }

    result = writer.review_and_write_table_catalog_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")
    api_response = response.build_table_catalog_authoring_response(result)

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []
    assert result["write_result"]["status"] == "error"
    assert "duplicate_action=replace 옵션이 적용되었습니다." in api_response["message"]
    assert "비슷한 기존 정보" not in api_response["message"]


def test_authoring_prompt_templates_include_mapping_and_equipment_contracts() -> None:
    table_prompt = (
        PROJECT_ROOT / "langflow_components/table_catalog_authoring_flow/03_table_catalog_authoring_prompt_template.md"
    ).read_text(encoding="utf-8")
    filter_prompt = (
        PROJECT_ROOT
        / "langflow_components/main_flow_filters_authoring_flow/03_main_flow_filter_authoring_prompt_template.md"
    ).read_text(encoding="utf-8")
    domain_prompt = (
        PROJECT_ROOT / "langflow_components/domain_authoring_flow/03_domain_authoring_prompt_template.md"
    ).read_text(encoding="utf-8")

    assert "table_catalog.filter_mappings maps those standard keys to this dataset's physical columns" in table_prompt
    assert "Never \"correct\" table or column spelling" in table_prompt
    assert "Authoring context" in table_prompt
    assert "standard_column_aliases" in table_prompt
    assert "dataset-specific mappings such as PKG_TYPE1->PKG1, PKG_TYPE1->PKG_TYP1, or MCP_NO->MCPSALENO belong in table_catalog.filter_mappings" in filter_prompt
    assert "EQP_COUNT" in domain_prompt
    assert "result_mode='detail_rows'" in domain_prompt

    table_variables = load_module(
        "langflow_components/table_catalog_authoring_flow/03_table_catalog_authoring_variables_builder.py"
    )
    context = table_variables.build_table_catalog_authoring_prompt_variables(
        {"raw_text": "equipment_status", "refined_text": "equipment refined", "existing_items": []}
    )["authoring_context"]
    assert "Original user text" in context
    assert "equipment_status" in context
    assert "equipment refined" in context


def test_authoring_prompt_templates_expose_only_expected_langflow_variables() -> None:
    expected_variables_by_template = {
        "langflow_components/domain_authoring_flow/01_domain_text_refinement_prompt_template.md": {"raw_text"},
        "langflow_components/domain_authoring_flow/01_domain_text_refinement_prompt_template_ko.md": {"raw_text"},
        "langflow_components/domain_authoring_flow/03_domain_authoring_prompt_template.md": {"authoring_context"},
        "langflow_components/domain_authoring_flow/03_domain_authoring_prompt_template_ko.md": {"authoring_context"},
        "langflow_components/domain_authoring_flow/06_domain_review_prompt_template.md": {"review_input_json"},
        "langflow_components/domain_authoring_flow/06_domain_review_prompt_template_ko.md": {"review_input_json"},
        "langflow_components/table_catalog_authoring_flow/01_table_catalog_text_refinement_prompt_template.md": {"raw_text"},
        "langflow_components/table_catalog_authoring_flow/01_table_catalog_text_refinement_prompt_template_ko.md": {"raw_text"},
        "langflow_components/table_catalog_authoring_flow/03_table_catalog_authoring_prompt_template.md": {"authoring_context"},
        "langflow_components/table_catalog_authoring_flow/03_table_catalog_authoring_prompt_template_ko.md": {"authoring_context"},
        "langflow_components/table_catalog_authoring_flow/06_table_catalog_review_prompt_template.md": {"review_input_json"},
        "langflow_components/table_catalog_authoring_flow/06_table_catalog_review_prompt_template_ko.md": {"review_input_json"},
        "langflow_components/main_flow_filters_authoring_flow/01_main_flow_filter_text_refinement_prompt_template.md": {"raw_text"},
        "langflow_components/main_flow_filters_authoring_flow/01_main_flow_filter_text_refinement_prompt_template_ko.md": {"raw_text"},
        "langflow_components/main_flow_filters_authoring_flow/03_main_flow_filter_authoring_prompt_template.md": {"authoring_context"},
        "langflow_components/main_flow_filters_authoring_flow/03_main_flow_filter_authoring_prompt_template_ko.md": {"authoring_context"},
        "langflow_components/main_flow_filters_authoring_flow/06_main_flow_filter_review_prompt_template.md": {"review_input_json"},
        "langflow_components/main_flow_filters_authoring_flow/06_main_flow_filter_review_prompt_template_ko.md": {"review_input_json"},
    }

    for relative_path, expected_variables in expected_variables_by_template.items():
        template = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        variables = set(re.findall(r"(?<!\{)\{([^{}]+)\}(?!\})", template))

        assert "{}" not in template
        assert "{{}}" not in template
        assert variables == expected_variables


def test_authoring_variable_builders_do_not_read_local_prompt_template_files() -> None:
    variable_builder_paths = [
        "langflow_components/domain_authoring_flow/01_domain_text_refinement_variables_builder.py",
        "langflow_components/domain_authoring_flow/03_domain_authoring_variables_builder.py",
        "langflow_components/domain_authoring_flow/06_domain_review_variables_builder.py",
        "langflow_components/table_catalog_authoring_flow/01_table_catalog_text_refinement_variables_builder.py",
        "langflow_components/table_catalog_authoring_flow/03_table_catalog_authoring_variables_builder.py",
        "langflow_components/table_catalog_authoring_flow/06_table_catalog_review_variables_builder.py",
        "langflow_components/main_flow_filters_authoring_flow/01_main_flow_filter_text_refinement_variables_builder.py",
        "langflow_components/main_flow_filters_authoring_flow/03_main_flow_filter_authoring_variables_builder.py",
        "langflow_components/main_flow_filters_authoring_flow/06_main_flow_filter_review_variables_builder.py",
    ]

    for relative_path in variable_builder_paths:
        code = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

        assert "TEMPLATE_FILE" not in code
        assert "read_text" not in code
        assert "Path(__file__)" not in code
        assert "_render_template" not in code


def test_main_flow_filter_authoring_detects_alias_overlap() -> None:
    normalizer = load_module("langflow_components/main_flow_filters_authoring_flow/04_main_flow_filter_authoring_result_normalizer.py")
    similarity = load_module("langflow_components/main_flow_filters_authoring_flow/05_main_flow_filter_similarity_checker.py")

    payload = {
        "metadata_type": "main_flow_filter",
        "existing_items": [
            {
                "filter_key": "DATE",
                "aliases": ["오늘", "금일"],
                "column_candidates": ["WORK_DT"],
                "semantic_role": "date",
            }
        ],
        "duplicate_decision": {"action": "ask"},
        "errors": [],
        "warnings": [],
    }
    llm_json = {
        "items": [
            {
                "filter_key": "WORK_DATE",
                "payload": {
                    "display_name": "작업일",
                    "aliases": ["오늘", "작업일"],
                    "column_candidates": ["WORK_DT", "BASE_DT"],
                    "semantic_role": "date",
                    "value_type": "date",
                    "operator": "eq",
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }
    normalized = normalizer.normalize_main_flow_filter_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    assert normalized["errors"] == []
    checked = similarity.check_main_flow_filter_similarity(normalized, "ask")
    assert checked["existing_matches"] == []
    assert checked["conflict_warnings"]
    assert checked["conflict_warnings"][0]["warning_type"] == "alias_overlap"


def test_main_flow_filter_authoring_normalizes_runtime_hint_lists() -> None:
    normalizer = load_module("langflow_components/main_flow_filters_authoring_flow/04_main_flow_filter_authoring_result_normalizer.py")
    payload = {"metadata_type": "main_flow_filter", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "filter_key": "DATE",
                "payload": {
                    "display_name": "기준일",
                    "aliases": "오늘",
                    "column_candidates": "WORK_DT",
                    "semantic_role": "date",
                    "value_type": "date",
                    "sample_values": "20260612",
                    "required_params": "DATE",
                    "value_mappings": [],
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_main_flow_filter_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    item_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert item_payload["aliases"] == ["오늘"]
    assert item_payload["column_candidates"] == ["WORK_DT"]
    assert item_payload["sample_values"] == ["20260612"]
    assert item_payload["required_params"] == ["DATE"]
    assert item_payload["value_mappings"] == {}


def test_main_flow_filter_authoring_accepts_legacy_field_names() -> None:
    normalizer = load_module("langflow_components/main_flow_filters_authoring_flow/04_main_flow_filter_authoring_result_normalizer.py")
    payload = {"metadata_type": "main_flow_filter", "errors": [], "warnings": []}
    llm_json = {
        "items": [
            {
                "filter_key": "OPER_NAME",
                "payload": {
                    "display_name": "공정명",
                    "aliases": "공정, 오퍼명",
                    "columns": "OPER_NAME, OPER_DESC",
                    "semantic_role": "process_name",
                    "value_type": "string",
                    "value_shape": "list",
                    "operator": "between",
                    "known_values": "D/A1, W/B1",
                    "value_aliases": {"DA": ["D/A1", "D/A2"], "WB": "W/B1"},
                },
            }
        ],
        "missing_information": [],
        "warnings": [],
    }

    normalized = normalizer.normalize_main_flow_filter_authoring_result(payload, json.dumps(llm_json, ensure_ascii=False))
    item_payload = normalized["items"][0]["payload"]

    assert normalized["errors"] == []
    assert item_payload["column_candidates"] == ["OPER_NAME", "OPER_DESC"]
    assert item_payload["operator"] == "range"
    assert item_payload["sample_values"] == ["D/A1", "W/B1"]
    assert item_payload["value_mappings"] == {"DA": ["D/A1", "D/A2"], "WB": "W/B1"}
    assert "known_values" not in item_payload
    assert "value_aliases" not in item_payload


def test_main_flow_filter_review_ignores_filter_key_supplement_when_item_has_key() -> None:
    variables = load_module("langflow_components/main_flow_filters_authoring_flow/06_main_flow_filter_review_variables_builder.py")
    writer = load_module("langflow_components/main_flow_filters_authoring_flow/07_main_flow_filter_review_writer.py")
    payload = {
        "metadata_type": "main_flow_filter",
        "items": [
            {
                "filter_key": "DATE",
                "payload": {
                    "display_name": "기준일",
                    "aliases": ["오늘", "작업일"],
                    "column_candidates": ["WORK_DT"],
                    "semantic_role": "date",
                },
            }
        ],
        "authoring": {
            "missing_information": [
                {"field": "filter_key", "reason": "filter_key가 필요합니다."}
            ]
        },
        "duplicate_decision": {"action": "ask", "requires_user_choice": False},
        "errors": [],
    }

    review_input = json.loads(variables.build_main_flow_filter_review_prompt_variables(payload)["review_input_json"])
    assert review_input["missing_information"] == []

    review_json = {
        "ready_to_save": False,
        "supplement_requests": [{"field": "filter_key", "reason": "filter_key가 필요합니다."}],
    }
    result = writer.review_and_write_main_flow_filter_payload(payload, json.dumps(review_json, ensure_ascii=False), mongo_uri="")

    assert result["review"]["ready_to_save"] is True
    assert result["review"]["supplement_requests"] == []
