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
    assert item_payload["required_param_mappings"] == {"DATE": ["DATE"]}
    assert item_payload["standard_column_aliases"] == {"OUT_PLAN": ["OUT계획"], "PKG_TYPE1": ["PKG1"]}
    assert item_payload["default_detail_columns"] == ["DATE"]
    assert item_payload["date_format"] == "YYYY-MM-DD"


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
    assert item_payload["primary_quantity_column"] == ["INPUT_PLAN", "OUT_PLAN"]
    assert item_payload["columns"] == ["DATE", "Mode", "DEN", "TECH", "PKG1", "PKG2", "LEAD", "ORG", "MCP NO", "INPUT계획", "OUT계획"]
    assert item_payload["filter_mappings"]["PKG_TYPE1"] == ["PKG1"]
    assert item_payload["filter_mappings"]["MCP_NO"] == ["MCP NO"]
    assert item_payload["standard_column_aliases"]["MODE"] == ["Mode"]
    assert item_payload["standard_column_aliases"]["PKG_TYPE1"] == ["PKG1"]
    assert item_payload["standard_column_aliases"]["MCP_NO"] == ["MCP NO"]
    assert item_payload["standard_column_aliases"]["INPUT_PLAN"] == ["INPUT계획"]
    assert item_payload["standard_column_aliases"]["OUT_PLAN"] == ["OUT계획", "TARGET"]


def test_table_catalog_authoring_backfills_structured_fields_from_raw_text() -> None:
    normalizer = load_module("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    raw_text = """당일용 생산 실적 데이터는 production_today로 등록해줘.
화면에 보일 이름은 Production Today이면 돼.
당일 생산 실적 질문에 사용하는 Oracle 데이터야.
production_today는 production 계열의 당일용 생산 실적 source야.
조회할 때 DATE 값은 WORK_DT 컬럼에 넣어서 조회하고, DATE는 조회 필수 기준일이야.
DATE는 YYYYMMDD 형식이야.
수량은 PRODUCTION 컬럼을 사용하고, 이 값은 생산량이야.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT WORK_DT, FACTORY, FAMILY, MODE, DEN, TECH, ORG, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, DEVICE, DEVICE_DESC, OPER_NUM, OPER_NAME, OPER_SEQ, PRODUCTION
FROM PRODUCTION_TODAY
WHERE 1=1
AND WORK_DT = {DATE}
AND PRODUCTION > 0

filter_mappings는 DATE -> WORK_DT, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2, LEAD -> LEAD, MCP_NO -> MCP_NO, TSV_DIE_TYP -> TSV_DIE_TYP, DEVICE_DESC -> DEVICE_DESC, OPER_NUM -> OPER_NUM, OPER_NAME -> OPER_NAME로 연결해줘."""
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
                    "required_param_mappings": {"DATE": ["WORK_DT"]},
                    "date_format": "YYYYMMDD",
                    "primary_quantity_column": "PRODUCTION",
                    "filter_mappings": {"DATE": ["WORK_DT"]},
                    "columns": ["WORK_DT", "PRODUCTION"],
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
        "WORK_DT",
        "FACTORY",
        "FAMILY",
        "MODE",
        "DEN",
        "TECH",
        "ORG",
        "PKG_TYPE1",
        "PKG_TYPE2",
        "LEAD",
        "MCP_NO",
        "TSV_DIE_TYP",
        "DEVICE",
        "DEVICE_DESC",
        "OPER_NUM",
        "OPER_NAME",
        "OPER_SEQ",
        "PRODUCTION",
    ]
    assert item_payload["filter_mappings"]["OPER_NAME"] == ["OPER_NAME"]
    assert item_payload["filter_mappings"]["MODE"] == ["MODE"]
    assert item_payload["required_param_mappings"]["DATE"] == ["WORK_DT"]
    assert item_payload["date_format"] == "YYYYMMDD"
    assert item_payload["primary_quantity_column"] == "PRODUCTION"


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
    assert "Authoring context" in table_prompt
    assert "standard_column_aliases" in table_prompt
    assert "dataset-specific mappings such as PKG_TYPE1->PKG1 or MCP_NO->MCPSALENO belong in table_catalog.filter_mappings" in filter_prompt
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
