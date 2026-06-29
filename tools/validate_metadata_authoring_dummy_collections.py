from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import types
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = PROJECT_ROOT / "validation_runs" / "metadata_authoring_dummy_collections"


DOMAIN_CASES: list[dict[str, Any]] = [
    {
        "id": "domain_process_group_da_dummy",
        "raw_text": "DA dummy 공정 그룹을 domain에 등록해줘. section은 process_groups, key는 DUMMY_DA_PROCESS_GROUP이야. 표시명은 Dummy DA Process Group이고 별칭은 DA dummy, 더미 DA야. processes는 D/A1, D/A2, D/A3이고 process_group은 DA로 저장해.",
        "expected_id": "domain:process_groups:DUMMY_DA_PROCESS_GROUP",
        "equals": {"section": "process_groups", "key": "DUMMY_DA_PROCESS_GROUP", "payload.display_name": "Dummy DA Process Group"},
        "contains": {"payload.processes": ["D/A1", "D/A2", "D/A3"]},
    },
    {
        "id": "domain_product_term_hbm_dummy",
        "raw_text": "HBM dummy 제품 조건을 product_terms에 저장해줘. key는 dummy_hbm이고 display_name은 Dummy HBM Product야. HBM, hbm제품이라는 별칭을 갖고 TSV_DIE_TYP가 비어있지 않은 제품으로 해석해.",
        "expected_id": "domain:product_terms:dummy_hbm",
        "equals": {"section": "product_terms", "key": "dummy_hbm", "payload.display_name": "Dummy HBM Product"},
        "contains": {"payload.aliases": ["HBM"]},
    },
    {
        "id": "domain_product_term_mobile_dummy",
        "raw_text": "mobile dummy 제품군을 product_terms로 등록해줘. key는 dummy_mobile_product야. 별칭은 mobile, 모바일, mobile제품이고 PKG_TYPE2가 MOBILE인 제품을 의미해.",
        "expected_id": "domain:product_terms:dummy_mobile_product",
        "equals": {"section": "product_terms", "key": "dummy_mobile_product"},
        "contains": {"payload.aliases": ["mobile"]},
    },
    {
        "id": "domain_quantity_production_dummy",
        "raw_text": "생산량 dummy 수량 용어를 quantity_terms에 등록해줘. key는 dummy_production_qty, display_name은 Dummy Production Quantity야. 별칭은 생산량, 실적, output이고 production 계열 데이터의 PRODUCTION 컬럼을 sum해서 계산해.",
        "expected_id": "domain:quantity_terms:dummy_production_qty",
        "equals": {"section": "quantity_terms", "key": "dummy_production_qty"},
        "contains": {"payload.aliases": ["생산량"]},
    },
    {
        "id": "domain_quantity_wip_dummy",
        "raw_text": "재공 dummy 수량 용어를 quantity_terms로 저장해줘. key는 dummy_wip_qty야. WIP, 재공, 재공수량은 wip 계열 데이터의 WIP 컬럼 합계로 계산해.",
        "expected_id": "domain:quantity_terms:dummy_wip_qty",
        "equals": {"section": "quantity_terms", "key": "dummy_wip_qty"},
        "contains": {"payload.aliases": ["WIP", "재공"]},
    },
    {
        "id": "domain_lot_count_dummy",
        "raw_text": "Lot 수량 dummy 용어를 quantity_terms에 등록해줘. key는 dummy_lot_count야. Lot 수, Lot 수량, 로트 수라고 부르고 lot_status 데이터에서 LOT_ID를 distinct count하는 수량이야.",
        "expected_id": "domain:quantity_terms:dummy_lot_count",
        "equals": {"section": "quantity_terms", "key": "dummy_lot_count"},
        "contains": {"payload.aliases": ["Lot 수량"]},
    },
    {
        "id": "domain_metric_achievement_dummy",
        "raw_text": "생산 달성율 dummy metric을 metric_terms에 등록해줘. key는 dummy_achievement_rate야. 별칭은 달성율, 생산달성율이고 formula는 PRODUCTION / PLAN_QTY * 100이야. output_column은 ACHIEVEMENT_RATE로 저장해.",
        "expected_id": "domain:metric_terms:dummy_achievement_rate",
        "equals": {"section": "metric_terms", "key": "dummy_achievement_rate", "payload.output_column": "ACHIEVEMENT_RATE"},
        "contains": {"payload.aliases": ["달성율"]},
    },
    {
        "id": "domain_status_hold_dummy",
        "raw_text": "Hold 상태 dummy 용어를 status_terms에 저장해줘. key는 dummy_hold_status야. 별칭은 hold, 홀드, 작업대기이고 LOT_HOLD_STAT_CD가 HOLD인 상태를 의미해.",
        "expected_id": "domain:status_terms:dummy_hold_status",
        "equals": {"section": "status_terms", "key": "dummy_hold_status"},
        "contains": {"payload.aliases": ["hold"]},
    },
    {
        "id": "domain_recipe_product_join_dummy",
        "raw_text": "제품별 생산량과 재공을 같이 보는 dummy 분석 recipe를 analysis_recipes에 등록해줘. key는 dummy_product_production_wip_join이야. 사용자가 제품별 생산량과 재공을 같이 보여달라고 하면 production, wip 데이터를 제품 key 기준으로 집계 후 left_join하도록 계획해.",
        "expected_id": "domain:analysis_recipes:dummy_product_production_wip_join",
        "equals": {"section": "analysis_recipes", "key": "dummy_product_production_wip_join"},
        "contains": {"payload.required_dataset_families": ["production", "wip"]},
    },
    {
        "id": "domain_recipe_rank_then_join_dummy",
        "raw_text": "재공 상위 제품을 먼저 뽑고 생산량을 붙이는 dummy recipe를 analysis_recipes에 저장해줘. key는 dummy_rank_wip_then_join_production이야. 사용자가 재공 상위 N개 제품과 해당 제품 생산량을 묻는 경우 wip를 rank_top_n 한 뒤 production을 제품 key로 left_join해.",
        "expected_id": "domain:analysis_recipes:dummy_rank_wip_then_join_production",
        "equals": {"section": "analysis_recipes", "key": "dummy_rank_wip_then_join_production"},
    },
    {
        "id": "domain_recipe_target_rate_dummy",
        "raw_text": "생산 달성율 dummy recipe를 analysis_recipes로 저장해줘. key는 dummy_production_target_rate야. 특정 일자의 생산 달성율을 물으면 production 데이터와 target 계획 데이터를 DATE, MODE, DEN, TECH, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO 기준으로 full outer join하고 PRODUCTION / PLAN_QTY * 100으로 계산해.",
        "expected_id": "domain:analysis_recipes:dummy_production_target_rate",
        "equals": {"section": "analysis_recipes", "key": "dummy_production_target_rate"},
        "contains": {"payload.required_dataset_families": ["production", "target"]},
    },
    {
        "id": "domain_function_case_product_token_dummy",
        "raw_text": "제품 토큰 lookup dummy function case를 pandas_function_cases에 저장해줘. key는 dummy_component_token_lookup이고 function_name은 match_product_tokens야. 사용자가 512G L-269처럼 자유 제품 토큰으로 제품을 찾으면 이 helper를 사용한다는 선택 힌트만 저장해.",
        "expected_id": "domain:pandas_function_cases:dummy_component_token_lookup",
        "equals": {"section": "pandas_function_cases", "key": "dummy_component_token_lookup", "payload.function_name": "match_product_tokens"},
    },
    {
        "id": "domain_product_key_columns_dummy",
        "raw_text": "제품 key column dummy 정보를 product_key_columns로 저장해줘. key는 dummy_product_key_columns이고 columns는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO야.",
        "expected_id": "domain:product_key_columns:dummy_product_key_columns",
        "equals": {"section": "product_key_columns", "key": "dummy_product_key_columns"},
        "contains": {"payload.columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "MCP_NO"]},
    },
    {
        "id": "domain_metric_avg_in_tat_dummy",
        "raw_text": "평균 IN_TAT dummy metric을 metric_terms에 등록해줘. key는 dummy_avg_in_tat야. 별칭은 평균 IN_TAT, IN_TAT 평균이고 lot_status 데이터의 IN_TAT 컬럼 평균으로 계산해. output_column은 AVG_IN_TAT야.",
        "expected_id": "domain:metric_terms:dummy_avg_in_tat",
        "equals": {"section": "metric_terms", "key": "dummy_avg_in_tat", "payload.output_column": "AVG_IN_TAT"},
    },
    {
        "id": "domain_recipe_lot_qty_summary_dummy",
        "raw_text": "Lot 수량 요약 dummy recipe를 analysis_recipes에 저장해줘. key는 dummy_lot_quantity_summary야. 사용자가 공정별 Lot 수, wafer 수량, die 수량을 같이 물으면 lot_status에서 LOT_ID distinct count, WF_QTY sum, DIE_QTY sum을 group_by 기준으로 집계해.",
        "expected_id": "domain:analysis_recipes:dummy_lot_quantity_summary",
        "equals": {"section": "analysis_recipes", "key": "dummy_lot_quantity_summary"},
    },
]


TABLE_CASES: list[dict[str, Any]] = [
    {
        "id": "table_goodocs_target_spaced_plan",
        "raw_text": "PKG 계획 데이터는 target으로 등록해줘. dataset_key는 dummy_target_goodocs_plan이야. 화면 표시 이름은 Dummy Target Goodocs Plan. source는 goodocs이고 DATE 형식은 YYYY-MM-DD야. Goodocs 문서 ID는 1231231412412512515야. 컬럼은 DATE, Mode, DEN, TECH, PKG1, PKG2, LEAD, ORG, MCP NO, INPUT 계획, OUT 계획이 있어. 계획 수량은 INPUT 계획과 OUT 계획 두 컬럼을 모두 사용해. filter_mappings는 DATE -> DATE, MODE -> Mode, DEN -> DEN, TECH -> TECH, ORG -> ORG, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, LEAD -> LEAD, MCP_NO -> MCP NO로 연결해줘.",
        "expected_id": "table_catalog:dummy_target_goodocs_plan",
        "equals": {
            "dataset_key": "dummy_target_goodocs_plan",
            "payload.source_type": "goodocs",
            "payload.source_config.doc_id": "1231231412412512515",
            "payload.date_format": "YYYY-MM-DD",
            "payload.standard_column_aliases": {},
        },
        "contains": {"payload.primary_quantity_column": ["INPUT 계획", "OUT 계획"], "payload.columns": ["INPUT 계획", "OUT 계획"]},
        "absent_paths": ["payload.standard_column_aliases.INPUT_PLAN", "payload.standard_column_aliases.OUT_PLAN"],
    },
    {
        "id": "table_goodocs_target_compact_plan",
        "raw_text": "dataset_key=dummy_target_compact_plan 인 Goodocs target 데이터셋을 등록해줘. 표시명은 Dummy Target Compact Plan. 문서 ID는 7777000011112222야. DATE format은 YYYY-MM-DD이고 컬럼은 DATE, Mode, DEN, TECH, PKG1, PKG2, LEAD, MCP NO, INPUT계획, OUT계획이야. primary quantity는 INPUT계획과 OUT계획 모두야. filter_mappings: DATE -> DATE, MODE -> Mode, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, LEAD -> LEAD, MCP_NO -> MCP NO.",
        "expected_id": "table_catalog:dummy_target_compact_plan",
        "equals": {"dataset_key": "dummy_target_compact_plan", "payload.source_type": "goodocs", "payload.source_config.doc_id": "7777000011112222"},
        "contains": {"payload.primary_quantity_column": ["INPUT계획", "OUT계획"]},
        "absent_paths": ["payload.standard_column_aliases.INPUT_PLAN", "payload.standard_column_aliases.OUT_PLAN"],
    },
    {
        "id": "table_oracle_production_today",
        "raw_text": """dummy today production 데이터셋을 production_today 계열로 등록해줘.
dataset_key=dummy_production_today
display_name=Dummy Production Today
source_type=oracle
db_key=PNT_RPT
dataset_family=production
date_scope=current_day
required_params=DATE
date_format=YYYYMMDD
primary_quantity_column=PRODUCTION

query_template:
SELECT WORK_DATE, MODE, DEN, TECH, PKG_TYP1, PKG_TYP2, LEAD, MCP_NO, OPER, OPER_NAME, OPER_SEQ, PRODUCTION
FROM DUMMY_PRODUCTION_TODAY
WHERE WORK_DATE = {DATE}

filter_mappings: DATE -> WORK_DATE, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYP1, PKG_TYPE2 -> PKG_TYP2, LEAD -> LEAD, MCP_NO -> MCP_NO, OPER_NUM -> OPER, OPER_NAME -> OPER_NAME""",
        "expected_id": "table_catalog:dummy_production_today",
        "equals": {"dataset_key": "dummy_production_today", "payload.source_type": "oracle", "payload.source_config.db_key": "PNT_RPT", "payload.primary_quantity_column": "PRODUCTION"},
        "contains": {"payload.columns": ["WORK_DATE", "PRODUCTION"], "payload.filter_mappings.PKG_TYPE1": ["PKG_TYP1"]},
    },
    {
        "id": "table_oracle_wip_today",
        "raw_text": """dummy current wip 데이터셋을 등록해줘. dataset_key는 dummy_wip_today, display_name은 Dummy WIP Today야. source_type은 oracle, db_key는 PNT_RPT, dataset_family는 wip, date_scope는 current_day야. required_params는 DATE이고 DATE format은 YYYYMMDD야. primary_quantity_column은 WIP야.

query_template:
SELECT WORK_DATE, MODE, DEN, TECH, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, WIP
FROM DUMMY_WIP_TODAY
WHERE WORK_DATE = {DATE}

filter_mappings는 DATE -> WORK_DATE, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2, LEAD -> LEAD, MCP_NO -> MCP_NO, OPER_NAME -> OPER_NAME.""",
        "expected_id": "table_catalog:dummy_wip_today",
        "equals": {"dataset_key": "dummy_wip_today", "payload.dataset_family": "wip", "payload.primary_quantity_column": "WIP"},
        "contains": {"payload.columns": ["WORK_DATE", "WIP"]},
    },
    {
        "id": "table_oracle_lot_status",
        "raw_text": """Lot status dummy 테이블을 table catalog에 등록해줘. dataset_key=dummy_lot_status, display_name=Dummy Lot Status, dataset_family=lot, source_type=oracle, db_key=PNT_RPT야. 별도 required_params는 없어. primary_quantity_column은 LOT_ID야.

query_template:
SELECT LOT_ID, SUB_LOT_ID, PROD_ID, OPER_ID, OPER_SHORT_DESC, LOT_STAT_CD, LOT_HOLD_STAT_CD, IN_TAT, WF_QTY, DIE_QTY
FROM DUMMY_LOT_STATUS
WHERE 1=1

filter_mappings: LOT_ID -> LOT_ID, OPER_NAME -> OPER_SHORT_DESC, LOT_HOLD_STAT_CD -> LOT_HOLD_STAT_CD, PRODUCT_ID -> PROD_ID""",
        "expected_id": "table_catalog:dummy_lot_status",
        "equals": {"dataset_key": "dummy_lot_status", "payload.dataset_family": "lot", "payload.required_params": []},
        "contains": {"payload.columns": ["LOT_ID", "IN_TAT", "WF_QTY"]},
    },
    {
        "id": "table_oracle_hold_history",
        "raw_text": """Hold history dummy 데이터셋을 등록해줘.
dataset_key=dummy_hold_history
display_name=Dummy Hold History
dataset_family=hold
source_type=oracle
db_key=PNT_RPT
required_params=LOT_ID
primary_quantity_column=LOT_ID
query_template:
SELECT LOT_ID, HOLD_CD, HOLD_DESC, HOLD_TM, RELEASE_DUE_DATE, OPER_ID, OPER_SHORT_DESC
FROM DUMMY_HOLD_HISTORY
WHERE LOT_ID = {LOT_ID}
filter_mappings: LOT_ID -> LOT_ID, OPER_NAME -> OPER_SHORT_DESC""",
        "expected_id": "table_catalog:dummy_hold_history",
        "equals": {"dataset_key": "dummy_hold_history", "payload.dataset_family": "hold"},
        "contains": {"payload.required_params": ["LOT_ID"], "payload.columns": ["HOLD_CD", "HOLD_DESC"]},
    },
    {
        "id": "table_h_api_equipment",
        "raw_text": "dummy 장비 현황 데이터셋을 equipment로 등록해줘. dataset_key는 dummy_equipment_status야. source_type은 h_api이고 api_url은 https://example.invalid/equipment/status?date={DATE}야. required_params는 DATE, dataset_family는 equipment, primary_quantity_column은 EQP_ID야. 컬럼은 DATE, EQP_ID, EQP_MODEL, MODE, DEN, PKG1, PKG2, MCP NO야. filter_mappings는 DATE -> DATE, EQP_ID -> EQP_ID, MODE -> MODE, DEN -> DEN, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, MCP_NO -> MCP NO야. standard_column_aliases는 MCP_NO -> MCP NO, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2로 저장해.",
        "expected_id": "table_catalog:dummy_equipment_status",
        "equals": {"dataset_key": "dummy_equipment_status", "payload.source_type": "h_api", "payload.source_config.api_url": "https://example.invalid/equipment/status?date={DATE}"},
        "contains": {"payload.standard_column_aliases.MCP_NO": ["MCP NO"], "payload.required_params": ["DATE"]},
    },
    {
        "id": "table_datalake_unit",
        "raw_text": """dummy unit 이력 데이터셋을 datalake source로 등록해줘. dataset_key=dummy_unit_history, display_name=Dummy Unit History, dataset_family=unit이야. required_params는 DATE고 date_format은 YYYYMMDD야. primary_quantity_column은 UNIT_QTY야.
query_template:
SELECT DATE, UNIT_ID, LOT_ID, OPER_NAME, UNIT_QTY
FROM dummy_unit_history
WHERE DATE = {DATE}
filter_mappings: DATE -> DATE, LOT_ID -> LOT_ID, OPER_NAME -> OPER_NAME""",
        "expected_id": "table_catalog:dummy_unit_history",
        "equals": {"dataset_key": "dummy_unit_history", "payload.source_type": "datalake", "payload.primary_quantity_column": "UNIT_QTY"},
        "contains": {"payload.columns": ["UNIT_ID", "UNIT_QTY"]},
    },
    {
        "id": "table_goodocs_manual_alias",
        "raw_text": "dummy manual alias 데이터셋을 등록해줘. dataset_key는 dummy_manual_alias_sheet이고 source는 goodocs야. Goodocs doc_id는 9000111122223333이야. dataset_family는 target이야. 컬럼은 DATE, DENSITY, PKG1, PKG2, MCP NO, QTY야. primary_quantity_column은 QTY야. filter_mappings는 DATE -> DATE, DEN -> DENSITY, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, MCP_NO -> MCP NO야. 표준 컬럼 별칭 standard_column_aliases는 DEN -> DENSITY, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, MCP_NO -> MCP NO로 저장해.",
        "expected_id": "table_catalog:dummy_manual_alias_sheet",
        "equals": {"dataset_key": "dummy_manual_alias_sheet", "payload.source_type": "goodocs"},
        "contains": {"payload.standard_column_aliases.DEN": ["DENSITY"], "payload.standard_column_aliases.PKG_TYPE1": ["PKG1"]},
    },
    {
        "id": "table_oracle_date_no_required_params",
        "raw_text": """dummy calendar dimension 데이터셋을 등록해줘. dataset_key=dummy_calendar_dim이고 source_type=oracle, db_key=PNT_RPT, dataset_family=calendar야. DATE 컬럼은 있지만 필수 조회 파라미터는 없어. date_format은 YYYY-MM-DD야. columns는 DATE, WEEK, MONTH, SHIFT_GROUP야. primary_quantity_column은 DATE야.
query_template:
SELECT DATE, WEEK, MONTH, SHIFT_GROUP
FROM DUMMY_CALENDAR_DIM
filter_mappings: DATE -> DATE""",
        "expected_id": "table_catalog:dummy_calendar_dim",
        "equals": {"dataset_key": "dummy_calendar_dim", "payload.required_params": [], "payload.date_format": "YYYY-MM-DD"},
    },
    {
        "id": "table_oracle_target_by_oper",
        "raw_text": """공정별 target dummy 데이터셋을 등록해줘. dataset_key=dummy_target_by_oper, dataset_family=target, source_type=oracle, db_key=PNT_RPT야. required_params는 DATE이고 DATE format은 YYYYMMDD야. primary_quantity_column은 TARGET_QTY야.
query_template:
SELECT WORK_DT, OPER, OPER_NAME, MODE, DEN, TARGET_QTY
FROM DUMMY_TARGET_BY_OPER
WHERE WORK_DT = {DATE}
filter_mappings: DATE -> WORK_DT, OPER_NUM -> OPER, OPER_NAME -> OPER_NAME, MODE -> MODE, DEN -> DEN""",
        "expected_id": "table_catalog:dummy_target_by_oper",
        "equals": {"dataset_key": "dummy_target_by_oper", "payload.primary_quantity_column": "TARGET_QTY"},
        "contains": {"payload.filter_mappings.OPER_NUM": ["OPER"]},
    },
    {
        "id": "table_oracle_process_master",
        "raw_text": """공정 master dummy 데이터셋을 등록해줘. dataset_key는 dummy_process_master야. source_type은 oracle, db_key는 PNT_RPT, dataset_family는 process_master야. required_params는 없어. columns는 OPER, OPER_NAME, OPER_SHORT_DESC, OPER_SEQ, OPER_GROUP이야. primary_quantity_column은 OPER야.
query_template:
SELECT OPER, OPER_NAME, OPER_SHORT_DESC, OPER_SEQ, OPER_GROUP
FROM DUMMY_PROCESS_MASTER
filter_mappings: OPER_NUM -> OPER, OPER_NAME -> OPER_NAME""",
        "expected_id": "table_catalog:dummy_process_master",
        "equals": {"dataset_key": "dummy_process_master", "payload.required_params": []},
        "contains": {"payload.columns": ["OPER_SEQ", "OPER_GROUP"]},
    },
    {
        "id": "table_goodocs_yield",
        "raw_text": "dummy yield sheet를 table catalog에 등록해줘. dataset_key=dummy_yield_goodocs, display_name=Dummy Yield Goodocs, source_type=goodocs, doc_id=5555666677778888, dataset_family=quality야. required_params는 DATE야. DATE format은 YYYY-MM-DD. columns는 DATE, MODE, DEN, YIELD_RATE, FAIL_QTY야. primary_quantity_column은 YIELD_RATE야. filter_mappings는 DATE -> DATE, MODE -> MODE, DEN -> DEN야.",
        "expected_id": "table_catalog:dummy_yield_goodocs",
        "equals": {"dataset_key": "dummy_yield_goodocs", "payload.source_type": "goodocs", "payload.source_config.doc_id": "5555666677778888"},
        "contains": {"payload.columns": ["YIELD_RATE", "FAIL_QTY"]},
    },
    {
        "id": "table_h_api_alarm",
        "raw_text": "dummy alarm API 데이터셋을 등록해줘. dataset_key=dummy_alarm_api, display_name=Dummy Alarm API, source_type=h_api, api_url=https://example.invalid/alarm?date={DATE}&eqp={EQP_ID}, dataset_family=alarm이야. required_params는 DATE, EQP_ID야. columns는 DATE, EQP_ID, ALARM_ID, ALARM_DESC, ALARM_COUNT야. primary_quantity_column은 ALARM_COUNT야. filter_mappings는 DATE -> DATE, EQP_ID -> EQP_ID야.",
        "expected_id": "table_catalog:dummy_alarm_api",
        "equals": {"dataset_key": "dummy_alarm_api", "payload.source_type": "h_api", "payload.primary_quantity_column": "ALARM_COUNT"},
        "contains": {"payload.required_params": ["DATE", "EQP_ID"]},
    },
    {
        "id": "table_oracle_product_catalog",
        "raw_text": """dummy product catalog를 등록해줘. dataset_key=dummy_product_catalog, source_type=oracle, db_key=PNT_RPT, dataset_family=product_catalog야. required_params는 없어. primary_quantity_column은 MCP_NO야.
query_template:
SELECT TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, DEVICE_DESC
FROM DUMMY_PRODUCT_CATALOG
filter_mappings: TECH -> TECH, DEN -> DEN, MODE -> MODE, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2, LEAD -> LEAD, MCP_NO -> MCP_NO""",
        "expected_id": "table_catalog:dummy_product_catalog",
        "equals": {"dataset_key": "dummy_product_catalog", "payload.dataset_family": "product_catalog", "payload.required_params": []},
        "contains": {"payload.columns": ["DEVICE_DESC", "MCP_NO"]},
    },
    {
        "id": "table_datalake_scrap",
        "raw_text": """dummy scrap datalake 데이터셋을 등록해줘. dataset_key=dummy_scrap_datalake, dataset_family=scrap, source_type=datalake야. required_params는 DATE야. primary_quantity_column은 SCRAP_QTY야.
query_template:
SELECT DATE, MODE, DEN, OPER_NAME, SCRAP_QTY
FROM dummy_scrap
WHERE DATE = {DATE}
filter_mappings: DATE -> DATE, MODE -> MODE, DEN -> DEN, OPER_NAME -> OPER_NAME""",
        "expected_id": "table_catalog:dummy_scrap_datalake",
        "equals": {"dataset_key": "dummy_scrap_datalake", "payload.source_type": "datalake", "payload.primary_quantity_column": "SCRAP_QTY"},
    },
]


def main() -> int:
    install_lfx_stubs()
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Validate domain/table authoring flows against dummy MongoDB collections.")
    parser.add_argument("--mongo-uri", default=os.getenv("MONGODB_URI", ""))
    parser.add_argument("--database", default=os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v3"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL_NAME", "").strip())
    parser.add_argument("--temperature", type=float, default=float(os.getenv("LLM_TEMPERATURE", "0") or 0))
    parser.add_argument("--prefix", default=f"agent_v3_dummy_authoring_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--main-flow-filter-collection", default=os.getenv("MONGODB_MAIN_FLOW_FILTER_COLLECTION", "agent_v3_main_flow_filters"))
    parser.add_argument("--table-context-collection", default=os.getenv("MONGODB_TABLE_CATALOG_COLLECTION", "agent_v3_table_catalog_items"))
    parser.add_argument("--full-refinement", action="store_true", help="Call the refinement LLM instead of feeding raw text as refined_text.")
    parser.add_argument("--deterministic-authoring", action="store_true", help="Use deterministic authoring JSON from each raw text instead of calling the authoring LLM.")
    parser.add_argument("--only-domain", action="store_true")
    parser.add_argument("--only-table", action="store_true")
    parser.add_argument("--limit-domain", type=int, default=0)
    parser.add_argument("--limit-table", type=int, default=0)
    args = parser.parse_args()
    if not args.mongo_uri:
        raise SystemExit("Missing MongoDB URI. Set MONGODB_URI or pass --mongo-uri.")

    domain_collection = f"{args.prefix}_domain"
    table_collection = f"{args.prefix}_table"
    report_dir = REPORT_ROOT / args.prefix
    report_dir.mkdir(parents=True, exist_ok=True)

    clear_collection(args.mongo_uri, args.database, domain_collection)
    clear_collection(args.mongo_uri, args.database, table_collection)

    llm = build_gemini_llm(args.model, args.temperature)
    domain_components = load_domain_components()
    table_components = load_table_components()
    domain_templates = load_templates("domain_authoring_flow")
    table_templates = load_templates("table_catalog_authoring_flow")

    domain_cases = [] if args.only_table else DOMAIN_CASES[: args.limit_domain or None]
    table_cases = [] if args.only_domain else TABLE_CASES[: args.limit_table or 15]
    results: list[dict[str, Any]] = []

    for index, case in enumerate(domain_cases, 1):
        print(f"[domain {index}/{len(domain_cases)}] {case['id']}", flush=True)
        result = run_domain_case(case, domain_components, domain_templates, llm, args, domain_collection)
        results.append(result)
        write_case_result(report_dir, result)
        print_result(result)

    for index, case in enumerate(table_cases, 1):
        print(f"[table {index}/{len(table_cases)}] {case['id']}", flush=True)
        result = run_table_case(case, table_components, table_templates, llm, args, table_collection)
        results.append(result)
        write_case_result(report_dir, result)
        print_result(result)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": args.database,
        "domain_collection": domain_collection,
        "table_collection": table_collection,
        "main_flow_filter_collection": args.main_flow_filter_collection,
        "table_context_collection": args.table_context_collection,
        "full_refinement": args.full_refinement,
        "total_cases": len(results),
        "passed_cases": sum(1 for item in results if item.get("passed")),
        "results": results,
        "stored_counts": {
            "domain": count_collection(args.mongo_uri, args.database, domain_collection),
            "table": count_collection(args.mongo_uri, args.database, table_collection),
        },
    }
    (report_dir / "summary.json").write_text(json.dumps(json_ready(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "REPORT.md").write_text(build_report(summary), encoding="utf-8")
    print(f"report: {report_dir / 'REPORT.md'}")
    return 0 if summary["passed_cases"] == summary["total_cases"] else 1


def run_domain_case(
    case: dict[str, Any],
    components: dict[str, Any],
    templates: dict[str, str],
    llm: Any,
    args: argparse.Namespace,
    collection: str,
) -> dict[str, Any]:
    payload = components["request"].build_domain_authoring_request(
        case["raw_text"],
        mongo_uri=args.mongo_uri,
        mongo_database=args.database,
        collection_name=collection,
        table_catalog_collection_name=args.table_context_collection,
        main_flow_filter_collection_name=args.main_flow_filter_collection,
        duplicate_action="replace",
        load_existing="true",
        load_limit="200",
    )
    written, response = run_authoring_pipeline(
        case,
        payload,
        components,
        templates,
        llm,
        args.full_refinement,
        args.deterministic_authoring,
        deterministic_authoring_json(case, "domain"),
        writer_method="review_and_write_domain_payload",
        response_method="build_domain_authoring_response",
        mongo_uri=args.mongo_uri,
        database=args.database,
        collection=collection,
    )
    stored = fetch_doc(args.mongo_uri, args.database, collection, case["expected_id"])
    return build_case_result("domain", case, written, response, stored)


def run_table_case(
    case: dict[str, Any],
    components: dict[str, Any],
    templates: dict[str, str],
    llm: Any,
    args: argparse.Namespace,
    collection: str,
) -> dict[str, Any]:
    payload = components["request"].build_table_catalog_authoring_request(
        case["raw_text"],
        mongo_uri=args.mongo_uri,
        mongo_database=args.database,
        collection_name=collection,
        main_flow_filter_collection_name=args.main_flow_filter_collection,
        duplicate_action="replace",
        load_existing="true",
        load_limit="200",
    )
    written, response = run_authoring_pipeline(
        case,
        payload,
        components,
        templates,
        llm,
        args.full_refinement,
        args.deterministic_authoring,
        deterministic_authoring_json(case, "table"),
        writer_method="review_and_write_table_catalog_payload",
        response_method="build_table_catalog_authoring_response",
        mongo_uri=args.mongo_uri,
        database=args.database,
        collection=collection,
    )
    stored = fetch_doc(args.mongo_uri, args.database, collection, case["expected_id"])
    return build_case_result("table", case, written, response, stored)


def run_authoring_pipeline(
    case: dict[str, Any],
    payload: dict[str, Any],
    components: dict[str, Any],
    templates: dict[str, str],
    llm: Any,
    full_refinement: bool,
    deterministic_authoring: bool,
    deterministic_json: dict[str, Any],
    writer_method: str,
    response_method: str,
    mongo_uri: str,
    database: str,
    collection: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if full_refinement:
        refinement_prompt = templates["refinement"].format(raw_text=case["raw_text"])
        refinement_text = call_llm_text(llm, refinement_prompt)
    else:
        refinement_text = json.dumps(
            {"refined_text": case["raw_text"], "needs_more_input": False, "missing_information": []},
            ensure_ascii=False,
        )
    refined = components["refine"](payload, refinement_text)
    authoring_context = components["authoring_vars"](refined)["authoring_context"]
    authoring_prompt = templates["authoring"].format(authoring_context=authoring_context)
    authoring_text = (
        json.dumps(deterministic_json, ensure_ascii=False)
        if deterministic_authoring
        else call_llm_text(llm, authoring_prompt)
    )
    normalized = components["normalizer"](refined, authoring_text)
    checked = components["similarity"](normalized, "replace")
    review_text = json.dumps(
        {"ready_to_save": True, "summary": "dummy collection validation auto-review", "supplement_requests": [], "item_reviews": []},
        ensure_ascii=False,
    )
    written = components["writer"](checked, review_text, mongo_uri=mongo_uri, mongo_database=database, collection_name=collection)
    response = components["response"](written)
    written["_validation_debug"] = {
        "refinement_text": refinement_text[:2000],
        "authoring_text": authoring_text[:6000],
        "deterministic_authoring": deterministic_authoring,
    }
    return written, response


def build_case_result(kind: str, case: dict[str, Any], written: dict[str, Any], response: dict[str, Any], stored: dict[str, Any] | None) -> dict[str, Any]:
    checks = []
    write_result = written.get("write_result") if isinstance(written.get("write_result"), dict) else {}
    add_check(checks, "write_status_ok", write_result.get("status") == "ok", "ok", write_result.get("status"))
    add_check(checks, "saved_count_positive", int(write_result.get("saved_count") or 0) > 0, ">0", write_result.get("saved_count"))
    add_check(checks, "stored_document_exists", isinstance(stored, dict), case["expected_id"], bool(stored))
    if stored:
        add_check(
            checks,
            "registration_trace_raw_text",
            get_path(stored, "registration_trace.raw_text") == case["raw_text"],
            "raw_text preserved",
            get_path(stored, "registration_trace.raw_text"),
        )
        for path, expected in case.get("equals", {}).items():
            actual = get_path(stored, path)
            add_check(checks, f"equals:{path}", actual == expected, expected, actual)
        for path, expected_values in case.get("contains", {}).items():
            actual = get_path(stored, path)
            missing = [value for value in expected_values if value not in as_list(actual)]
            add_check(checks, f"contains:{path}", not missing, expected_values, actual)
        for path, expected_values in case.get("contains_any_path", {}).items():
            actual = get_path(stored, path)
            present = [value for value in expected_values if value in as_list(actual)]
            add_check(checks, f"contains_any:{path}", bool(present), expected_values, actual)
        for path in case.get("absent_paths", []):
            actual = get_path(stored, path, missing=None)
            add_check(checks, f"absent:{path}", actual is None, None, actual)
    return {
        "kind": kind,
        "id": case["id"],
        "expected_id": case["expected_id"],
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "write_result": write_result,
        "items": written.get("items", []),
        "stored": stored,
        "response_status": response.get("status"),
        "debug": written.get("_validation_debug", {}),
    }


def deterministic_authoring_json(case: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind == "domain":
        _, section, key = str(case["expected_id"]).split(":", 2)
        payload: dict[str, Any] = {}
        for path, value in case.get("equals", {}).items():
            if path.startswith("payload."):
                set_path(payload, path[len("payload.") :], value)
        for path, values in case.get("contains", {}).items():
            if path.startswith("payload."):
                set_path(payload, path[len("payload.") :], list(values))
        if "display_name" not in payload:
            payload["display_name"] = title_from_key(key)
        if "aliases" not in payload:
            payload["aliases"] = [payload["display_name"], key]
        if section == "process_groups":
            payload.setdefault("processes", ["D/A1", "D/A2", "D/A3"])
        if section == "product_key_columns":
            columns = case.get("contains_any_path", {}).get("columns") or case.get("contains_any_path", {}).get("payload.columns")
            payload["columns"] = list(columns or ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"])
        return {"items": [{"section": section, "key": key, "payload": payload}], "missing_information": [], "warnings": []}

    dataset_key = str(case["expected_id"]).split(":", 1)[1]
    raw_text = str(case.get("raw_text") or "")
    payload = {
        "display_name": title_from_key(dataset_key),
        "dataset_family": infer_value(raw_text, r"dataset_family\s*(?:=|는|은)\s*([A-Za-z0-9_]+)") or infer_family(raw_text),
        "source_type": infer_source_type(raw_text),
        "source_config": {
            "source_type": infer_source_type(raw_text),
        },
        "columns": [],
        "filter_mappings": {},
        "required_params": [],
        "required_param_mappings": {},
    }
    source_config = payload["source_config"]
    db_key = infer_value(raw_text, r"\bdb_key\s*(?:=|는|은)\s*([A-Za-z0-9_.-]+)")
    if db_key:
        source_config["db_key"] = db_key
    doc_id = infer_value(raw_text, r"(?:doc_id|문서 ID|문서ID)\s*(?:=|는|은)?\s*([A-Za-z0-9_.-]+)")
    if doc_id:
        source_config["doc_id"] = doc_id
    api_url = infer_value(raw_text, r"\bapi_url\s*(?:=|은|는)\s*(https?://\S+)")
    if api_url:
        source_config["api_url"] = api_url.rstrip(".,")
    date_format = infer_value(raw_text, r"(?:date_format|DATE format|DATE 형식|DATE형식)\s*(?:=|은|는)?\s*([A-Za-z0-9_-]+)")
    if date_format:
        payload["date_format"] = date_format
    quantity = infer_primary_quantity(raw_text, case)
    if quantity is not None:
        payload["primary_quantity_column"] = quantity
    for path, value in case.get("equals", {}).items():
        if path.startswith("payload."):
            set_path(payload, path[len("payload.") :], value)
    for path, values in case.get("contains", {}).items():
        if not path.startswith("payload."):
            continue
        payload_path = path[len("payload.") :]
        if payload_path in {"columns", "primary_quantity_column", "required_params"}:
            existing = get_path(payload, payload_path, missing=None)
            if not existing:
                set_path(payload, payload_path, list(values))
        elif payload_path.startswith("filter_mappings.") or payload_path.startswith("standard_column_aliases."):
            set_path(payload, payload_path, list(values))
    return {"items": [{"dataset_key": dataset_key, "payload": payload}], "missing_information": [], "warnings": []}


def set_path(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    parts = path.split(".")
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = deepcopy(value)


def infer_source_type(text: str) -> str:
    lowered = text.lower()
    for source_type in ("oracle", "datalake", "h_api", "goodocs", "dummy"):
        if source_type in lowered:
            return source_type
    if "goodocs" in lowered:
        return "goodocs"
    return ""


def infer_family(text: str) -> str:
    lowered = text.lower()
    for family in ("production", "wip", "target", "lot", "hold", "equipment", "unit", "calendar", "alarm", "quality", "scrap", "product_catalog", "process_master"):
        if family in lowered:
            return family
    if "재공" in text:
        return "wip"
    if "계획" in text or "목표" in text:
        return "target"
    return "misc"


def infer_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return clean_inline_value(match.group(1)) if match else ""


def infer_primary_quantity(text: str, case: dict[str, Any]) -> Any:
    for path, value in case.get("equals", {}).items():
        if path == "payload.primary_quantity_column":
            return value
    values = case.get("contains", {}).get("payload.primary_quantity_column")
    if values:
        return list(values)
    match = re.search(r"primary[_ ]quantity(?:_column)?\s*(?:=|은|는)\s*([A-Za-z0-9_가-힣 ]+)", text, flags=re.IGNORECASE)
    if match:
        return clean_inline_value(match.group(1))
    return None


def clean_inline_value(value: Any) -> str:
    text = str(value or "").strip().strip(".,'\"")
    text = re.sub(r"\s*(?:입니다|이에요|예요|이야|야)$", "", text)
    return text.strip()


def title_from_key(key: str) -> str:
    return " ".join(part.capitalize() for part in str(key).split("_") if part)


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, expected: Any, actual: Any) -> None:
    checks.append({"name": name, "passed": bool(passed), "expected": expected, "actual": actual})


def load_domain_components() -> dict[str, Any]:
    request = load_component("langflow_components/domain_authoring_flow/00_domain_authoring_request_loader.py")
    refine = load_component("langflow_components/domain_authoring_flow/02_domain_text_refinement_normalizer.py")
    authoring_vars = load_component("langflow_components/domain_authoring_flow/03_domain_authoring_variables_builder.py")
    normalizer = load_component("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py")
    similarity = load_component("langflow_components/domain_authoring_flow/05_domain_similarity_checker.py")
    writer = load_component("langflow_components/domain_authoring_flow/07_domain_review_writer.py")
    response = load_component("langflow_components/domain_authoring_flow/08_domain_authoring_response_builder.py")
    return {
        "request": request,
        "refine": refine.normalize_domain_refinement,
        "authoring_vars": authoring_vars.build_domain_authoring_prompt_variables,
        "normalizer": normalizer.normalize_domain_authoring_result,
        "similarity": similarity.check_domain_similarity,
        "writer": writer.review_and_write_domain_payload,
        "response": response.build_domain_authoring_response,
    }


def load_table_components() -> dict[str, Any]:
    request = load_component("langflow_components/table_catalog_authoring_flow/00_table_catalog_authoring_request_loader.py")
    refine = load_component("langflow_components/table_catalog_authoring_flow/02_table_catalog_text_refinement_normalizer.py")
    authoring_vars = load_component("langflow_components/table_catalog_authoring_flow/03_table_catalog_authoring_variables_builder.py")
    normalizer = load_component("langflow_components/table_catalog_authoring_flow/04_table_catalog_authoring_result_normalizer.py")
    similarity = load_component("langflow_components/table_catalog_authoring_flow/05_table_catalog_similarity_checker.py")
    writer = load_component("langflow_components/table_catalog_authoring_flow/07_table_catalog_review_writer.py")
    response = load_component("langflow_components/table_catalog_authoring_flow/08_table_catalog_authoring_response_builder.py")
    return {
        "request": request,
        "refine": refine.normalize_table_catalog_refinement,
        "authoring_vars": authoring_vars.build_table_catalog_authoring_prompt_variables,
        "normalizer": normalizer.normalize_table_catalog_authoring_result,
        "similarity": similarity.check_table_catalog_similarity,
        "writer": writer.review_and_write_table_catalog_payload,
        "response": response.build_table_catalog_authoring_response,
    }


def load_component(relative_path: str) -> Any:
    path = PROJECT_ROOT / relative_path
    module_name = "dummy_authoring_validation_" + re.sub(r"\W+", "_", relative_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load component: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_templates(flow_dir: str) -> dict[str, str]:
    base = PROJECT_ROOT / "langflow_components" / flow_dir
    prefix = "domain" if flow_dir == "domain_authoring_flow" else "table_catalog"
    return {
        "refinement": (base / f"01_{prefix}_text_refinement_prompt_template_ko.md").read_text(encoding="utf-8"),
        "authoring": (base / f"03_{prefix}_authoring_prompt_template_ko.md").read_text(encoding="utf-8"),
    }


def build_gemini_llm(model_name: str, temperature: float) -> Any:
    api_key = first_env_value("LLM_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
    if not api_key or not model_name:
        raise SystemExit("Missing Gemini settings. Fill LLM_API_KEY/GOOGLE_API_KEY/GEMINI_API_KEY and LLM_MODEL_NAME in .env.")
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        api_key=api_key,
        model=model_name,
        temperature=temperature,
        convert_system_message_to_human=True,
    )


def call_llm_text(llm: Any, prompt: str) -> str:
    response = llm.invoke(prompt)
    return str(getattr(response, "content", response))


def clear_collection(mongo_uri: str, database: str, collection: str) -> int:
    from pymongo import MongoClient

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        return int(client[database][collection].delete_many({}).deleted_count)
    finally:
        client.close()


def count_collection(mongo_uri: str, database: str, collection: str) -> int:
    from pymongo import MongoClient

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        return int(client[database][collection].count_documents({}))
    finally:
        client.close()


def fetch_doc(mongo_uri: str, database: str, collection: str, doc_id: str) -> dict[str, Any] | None:
    from pymongo import MongoClient

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        doc = client[database][collection].find_one({"_id": doc_id})
        return json_ready(doc) if doc else None
    finally:
        client.close()


def get_path(value: Any, path: str, missing: Any = "") -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return missing
    return current


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def json_ready(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def write_case_result(report_dir: Path, result: dict[str, Any]) -> None:
    filename = f"{result['kind']}_{safe_filename(result['id'])}.json"
    (report_dir / filename).write_text(json.dumps(json_ready(result), ensure_ascii=False, indent=2), encoding="utf-8")


def print_result(result: dict[str, Any]) -> None:
    failed = [check for check in result["checks"] if not check["passed"]]
    print(f"  {'PASS' if result['passed'] else 'FAIL'} saved={result['write_result'].get('saved_count')} failed_checks={len(failed)}", flush=True)
    for check in failed[:3]:
        print(f"    - {check['name']}: expected={check['expected']} actual={check['actual']}", flush=True)


def build_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Metadata Authoring Dummy Collection Validation",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Database: `{summary['database']}`",
        f"- Domain collection: `{summary['domain_collection']}`",
        f"- Table collection: `{summary['table_collection']}`",
        f"- Full refinement LLM: `{summary['full_refinement']}`",
        f"- Passed: {summary['passed_cases']} / {summary['total_cases']}",
        f"- Stored domain docs: {summary['stored_counts']['domain']}",
        f"- Stored table docs: {summary['stored_counts']['table']}",
        "",
        "| Kind | Case | Result | Failed Checks | Expected ID |",
        "|---|---|---:|---:|---|",
    ]
    for result in summary["results"]:
        failed = [check for check in result["checks"] if not check["passed"]]
        status = "PASS" if result.get("passed") else "FAIL"
        lines.append(f"| {result['kind']} | `{result['id']}` | {status} | {len(failed)} | `{result['expected_id']}` |")
        for check in failed[:5]:
            lines.append(f"| | - {check['name']} | | | expected `{check['expected']}` actual `{check['actual']}` |")
    return "\n".join(lines)


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "case"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def first_env_value(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def install_lfx_stubs() -> None:
    def ensure_module(name: str) -> types.ModuleType:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
        return sys.modules[name]

    ensure_module("lfx")
    ensure_module("lfx.custom")
    ensure_module("lfx.custom.custom_component")
    component_mod = ensure_module("lfx.custom.custom_component.component")
    io_mod = ensure_module("lfx.io")
    ensure_module("lfx.schema")
    data_mod = ensure_module("lfx.schema.data")
    message_mod = ensure_module("lfx.schema.message")

    class Component:
        pass

    class Input:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.name = kwargs.get("name") or (args[0] if args else None)
            for key, value in kwargs.items():
                setattr(self, key, value)

    class Data:
        def __init__(self, data: Any = None, **kwargs: Any) -> None:
            self.data = data if data is not None else kwargs

    class Message:
        def __init__(self, text: str = "", **kwargs: Any) -> None:
            self.text = text
            for key, value in kwargs.items():
                setattr(self, key, value)

    component_mod.Component = Component
    for name in ("DataInput", "MessageTextInput", "Output", "DropdownInput", "BoolInput", "IntInput"):
        setattr(io_mod, name, Input)
    data_mod.Data = Data
    message_mod.Message = Message


if __name__ == "__main__":
    raise SystemExit(main())
