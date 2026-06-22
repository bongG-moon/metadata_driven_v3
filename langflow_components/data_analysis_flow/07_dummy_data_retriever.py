# 파일 설명: 07 Dummy Data Retriever Langflow custom component 파일입니다.
# 흐름 역할: 로컬 검증용 deterministic 제조 dummy 데이터를 실제 조회 결과와 같은 구조로 생성합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


PROCESS_ROWS = [
    {"OPER_NAME": "D/A1", "OPER_SHORT_DESC": "D/A1", "OPER_NUM": "DA10", "OPER_SEQ": 10, "OPER_DESC": "DIE ATTACH", "PROCESS_FAMILY": "DA"},
    {"OPER_NAME": "D/A2", "OPER_SHORT_DESC": "D/A2", "OPER_NUM": "DA20", "OPER_SEQ": 20, "OPER_DESC": "DIE ATTACH", "PROCESS_FAMILY": "DA"},
    {"OPER_NAME": "D/A3", "OPER_SHORT_DESC": "D/A3", "OPER_NUM": "DA30", "OPER_SEQ": 30, "OPER_DESC": "DIE ATTACH", "PROCESS_FAMILY": "DA"},
    {"OPER_NAME": "D/A4", "OPER_SHORT_DESC": "D/A4", "OPER_NUM": "DA40", "OPER_SEQ": 40, "OPER_DESC": "DIE ATTACH", "PROCESS_FAMILY": "DA"},
    {"OPER_NAME": "D/A5", "OPER_SHORT_DESC": "D/A5", "OPER_NUM": "DA50", "OPER_SEQ": 50, "OPER_DESC": "DIE ATTACH", "PROCESS_FAMILY": "DA"},
    {"OPER_NAME": "D/A6", "OPER_SHORT_DESC": "D/A6", "OPER_NUM": "DA60", "OPER_SEQ": 60, "OPER_DESC": "DIE ATTACH", "PROCESS_FAMILY": "DA"},
    {"OPER_NAME": "W/B1", "OPER_SHORT_DESC": "W/B1", "OPER_NUM": "WB10", "OPER_SEQ": 110, "OPER_DESC": "WIRE BOND", "PROCESS_FAMILY": "WB"},
    {"OPER_NAME": "W/B2", "OPER_SHORT_DESC": "W/B2", "OPER_NUM": "WB20", "OPER_SEQ": 120, "OPER_DESC": "WIRE BOND", "PROCESS_FAMILY": "WB"},
    {"OPER_NAME": "W/B3", "OPER_SHORT_DESC": "W/B3", "OPER_NUM": "WB30", "OPER_SEQ": 130, "OPER_DESC": "WIRE BOND", "PROCESS_FAMILY": "WB"},
    {"OPER_NAME": "W/B4", "OPER_SHORT_DESC": "W/B4", "OPER_NUM": "WB40", "OPER_SEQ": 140, "OPER_DESC": "WIRE BOND", "PROCESS_FAMILY": "WB"},
    {"OPER_NAME": "W/B5", "OPER_SHORT_DESC": "W/B5", "OPER_NUM": "WB50", "OPER_SEQ": 150, "OPER_DESC": "WIRE BOND", "PROCESS_FAMILY": "WB"},
    {"OPER_NAME": "W/B6", "OPER_SHORT_DESC": "W/B6", "OPER_NUM": "WB60", "OPER_SEQ": 160, "OPER_DESC": "WIRE BOND", "PROCESS_FAMILY": "WB"},
    {"OPER_NAME": "B/G1", "OPER_SHORT_DESC": "B/G1", "OPER_NUM": "BG10", "OPER_SEQ": 210, "OPER_DESC": "BACK GRIND", "PROCESS_FAMILY": "BG"},
    {"OPER_NAME": "B/G2", "OPER_SHORT_DESC": "B/G2", "OPER_NUM": "BG20", "OPER_SEQ": 220, "OPER_DESC": "BACK GRIND", "PROCESS_FAMILY": "BG"},
    {"OPER_NAME": "WSD1", "OPER_SHORT_DESC": "WSD1", "OPER_NUM": "WS10", "OPER_SEQ": 310, "OPER_DESC": "WAFER SAW DICE", "PROCESS_FAMILY": "WSD"},
    {"OPER_NAME": "WSD2", "OPER_SHORT_DESC": "WSD2", "OPER_NUM": "WS20", "OPER_SEQ": 320, "OPER_DESC": "WAFER SAW DICE", "PROCESS_FAMILY": "WSD"},
    {"OPER_NAME": "D/P1", "OPER_SHORT_DESC": "D/P1", "OPER_NUM": "DP10", "OPER_SEQ": 410, "OPER_DESC": "D/P FRONT", "PROCESS_FAMILY": "DP"},
    {"OPER_NAME": "D/P2", "OPER_SHORT_DESC": "D/P2", "OPER_NUM": "DP20", "OPER_SEQ": 420, "OPER_DESC": "D/P FRONT", "PROCESS_FAMILY": "DP"},
    {"OPER_NAME": "D/S1", "OPER_SHORT_DESC": "D/S1", "OPER_NUM": "DS10", "OPER_SEQ": 510, "OPER_DESC": "DIE SORT", "PROCESS_FAMILY": "DS"},
    {"OPER_NAME": "D/S2", "OPER_SHORT_DESC": "D/S2", "OPER_NUM": "DS20", "OPER_SEQ": 520, "OPER_DESC": "DIE SORT", "PROCESS_FAMILY": "DS"},
    {"OPER_NAME": "FCB1", "OPER_SHORT_DESC": "FCB1", "OPER_NUM": "FC10", "OPER_SEQ": 610, "OPER_DESC": "FLIP CHIP BOND", "PROCESS_FAMILY": "FCB"},
    {"OPER_NAME": "FCB2", "OPER_SHORT_DESC": "FCB2", "OPER_NUM": "FC20", "OPER_SEQ": 620, "OPER_DESC": "FLIP CHIP BOND", "PROCESS_FAMILY": "FCB"},
    {"OPER_NAME": "FCBH1", "OPER_SHORT_DESC": "FCBH1", "OPER_NUM": "FH10", "OPER_SEQ": 710, "OPER_DESC": "FCB HIGH", "PROCESS_FAMILY": "FCBH"},
    {"OPER_NAME": "FCBH2", "OPER_SHORT_DESC": "FCBH2", "OPER_NUM": "FH20", "OPER_SEQ": 720, "OPER_DESC": "FCB HIGH", "PROCESS_FAMILY": "FCBH"},
    {"OPER_NAME": "B/M1", "OPER_SHORT_DESC": "B/M1", "OPER_NUM": "BM10", "OPER_SEQ": 810, "OPER_DESC": "BACK MARK", "PROCESS_FAMILY": "BM"},
    {"OPER_NAME": "B/M2", "OPER_SHORT_DESC": "B/M2", "OPER_NUM": "BM20", "OPER_SEQ": 820, "OPER_DESC": "BACK MARK", "PROCESS_FAMILY": "BM"},
    {"OPER_NAME": "INPUT", "OPER_SHORT_DESC": "INPUT", "OPER_NUM": "IN10", "OPER_SEQ": 910, "OPER_DESC": "INPUT", "PROCESS_FAMILY": "INPUT"},
    {"OPER_NAME": "SHIP PKT", "OPER_SHORT_DESC": "SHIP PKT", "OPER_NUM": "PK10", "OPER_SEQ": 990, "OPER_DESC": "PACKAGE OUT", "PROCESS_FAMILY": "PKG_OUT"},
]


PRODUCT_ROWS = [
    {"FAMILY": "HBM", "TECH": "TSV", "DEN": "2048G", "MODE": "HBM3E", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM16E", "TSV_DIE_TYP": "16Hi", "DEVICE": "DEV-HBM3E-16HI", "DEVICE_DESC": "HBM3E 16Hi"},
    {"FAMILY": "HBM", "TECH": "TSV", "DEN": "1536G", "MODE": "HBM3", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM12A", "TSV_DIE_TYP": "12Hi", "DEVICE": "DEV-HBM3-12HI", "DEVICE_DESC": "HBM3 12Hi"},
    {"FAMILY": "HBM", "TECH": "TSV", "DEN": "1024G", "MODE": "HBM3", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM8A", "TSV_DIE_TYP": "8Hi", "DEVICE": "DEV-HBM3-8HI", "DEVICE_DESC": "HBM3 8Hi"},
    {"FAMILY": "HBM", "TECH": "TSV", "DEN": "512G", "MODE": "HBM2E", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM4E", "TSV_DIE_TYP": "4Hi", "DEVICE": "DEV-HBM2E-4HI", "DEVICE_DESC": "HBM2E 4Hi"},
    {"FAMILY": "LPDDR", "TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "EMPTY", "TSV_DIE_TYP": "", "DEVICE": "DEV-LP5-MOBILE", "DEVICE_DESC": "LPDDR5 MOBILE"},
    {"FAMILY": "LPDDR", "TECH": "FC", "DEN": "256G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "EDGE", "LEAD": "LF", "MCP_NO": "L-269E1D", "TSV_DIE_TYP": "", "DEVICE": "DEV-LP5-EDGE", "DEVICE_DESC": "LPDDR5 EDGE"},
    {"FAMILY": "LPDDR", "TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "POP", "LEAD": "LF", "MCP_NO": "L-269P1Q", "TSV_DIE_TYP": "", "DEVICE": "DEV-LP5-POP", "DEVICE_DESC": "LPDDR5 POP"},
    {"FAMILY": "LPDDR", "TECH": "FC", "DEN": "256G", "MODE": "LPDDR5X", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "L-55XM2Q", "TSV_DIE_TYP": "", "DEVICE": "DEV-LP5X-MOBILE", "DEVICE_DESC": "LPDDR5X MOBILE"},
    {"FAMILY": "DDR", "TECH": "WB", "DEN": "512G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "AUTO", "LEAD": "LF", "MCP_NO": "L-111K1Q", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR5-AUTO", "DEVICE_DESC": "DDR5 AUTO"},
    {"FAMILY": "DDR", "TECH": "WB", "DEN": "256G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "STD", "LEAD": "LF", "MCP_NO": "L-222K1A", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR5-STD", "DEVICE_DESC": "DDR5 STD"},
    {"FAMILY": "DDR", "TECH": "WB", "DEN": "1024G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "SERVER", "LEAD": "LF", "MCP_NO": "L-555S1E", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR5-SERVER", "DEVICE_DESC": "DDR5 SERVER"},
    {"FAMILY": "DDR", "TECH": "WB", "DEN": "128G", "MODE": "DDR5", "PKG_TYPE1": "FBGA", "PKG_TYPE2": "CLIENT", "LEAD": "LF", "MCP_NO": "L-138C1L", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR5-CLIENT", "DEVICE_DESC": "DDR5 CLIENT"},
    {"FAMILY": "DDR", "TECH": "RG", "DEN": "256G", "MODE": "DDR4", "PKG_TYPE1": "FBGA", "PKG_TYPE2": "AUTO", "LEAD": "LF", "MCP_NO": "R-401A1U", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR4-AUTO", "DEVICE_DESC": "DDR4 AUTO"},
    {"FAMILY": "GDDR", "TECH": "FC", "DEN": "512G", "MODE": "GDDR7", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "AI", "LEAD": "LF", "MCP_NO": "G-777A2I", "TSV_DIE_TYP": "", "DEVICE": "DEV-GDDR7-AI", "DEVICE_DESC": "GDDR7 AI"},
    {"FAMILY": "MCP", "TECH": "POP", "DEN": "128G", "MODE": "MCP", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "MCP", "LEAD": "LF", "MCP_NO": "L-269M2B", "TSV_DIE_TYP": "", "DEVICE": "DEV-MCP-128", "DEVICE_DESC": "MCP 128G"},
    {"FAMILY": "GDDR", "TECH": "WB", "DEN": "256G", "MODE": "GDDR6", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "GRAPHICS", "LEAD": "LF", "MCP_NO": "G-626G1R", "TSV_DIE_TYP": "", "DEVICE": "DEV-GDDR6-GRAPHICS", "DEVICE_DESC": "GDDR6 GRAPHICS"},
]


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 로컬 검증용 deterministic 제조 dummy 데이터를 실제 조회 결과와 같은 구조로 생성합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def retrieve_dummy_data(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else payload
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}

    if payload.get("skipped"):
        return {
            "retrieval_payload": {
                "skipped": True,
                "skip_reason": payload.get("skip_reason", "route skipped"),
                "route": plan.get("route", ""),
                "source_results": [],
                "intent_plan": plan,
                "state": state,
            }
        }

    if plan.get("route") == "finish" or plan.get("query_mode") == "finish":
        return {
            "retrieval_payload": {
                "route": "finish",
                "source_results": [],
                "early_result": {"response": plan.get("response", ""), "current_data": state.get("current_data")},
                "intent_plan": plan,
                "state": state,
            }
        }

    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else payload.get("retrieval_jobs", [])
    source_results = [_source_result(job) for job in jobs if isinstance(job, dict)]
    return {
        "retrieval_payload": {
            "route": plan.get("route", "multi_retrieval"),
            "source_type": "dummy",
            "source_results": source_results,
            "intent_plan": plan,
            "state": state,
        }
    }


def _source_result(job: dict[str, Any]) -> dict[str, Any]:
    dataset_key = str(job.get("dataset_key") or "")
    params = deepcopy(job.get("params", {})) if isinstance(job.get("params"), dict) else {}
    rows = _dummy_rows(dataset_key, params)
    rows = _apply_job_filters(rows, _param_filters(params, dataset_key), apply_missing_field_as_match=True)
    rows = _project_required_columns(rows, job.get("required_columns"))
    columns = _rows_columns(rows)
    result = {
        "success": True,
        "dataset_key": dataset_key,
        "source_alias": job.get("source_alias", dataset_key),
        "source_type": "dummy",
        "data": rows,
        "columns": columns,
        "row_count": len(rows),
        "summary": f"{dataset_key or 'dummy'} dummy retrieval complete: {len(rows)} rows",
        "applied_params": params,
        "applied_filters": deepcopy(job.get("filters", [])) if isinstance(job.get("filters"), list) else [],
        "used_dummy_data": True,
        "source_execution": {
            "generator": "metadata_driven_v3.dummy",
            "dataset_key": dataset_key,
            "params_applied_in_retriever": True,
            "filters_applied_in_retriever": False,
            "filter_execution_stage": "pandas",
        },
    }
    for key in ("job_id", "job_key", "purpose", "primary_quantity_column", "measure_columns", "numeric_columns", "value_columns", "filter_mappings"):
        if job.get(key) not in (None, "", [], {}):
            result[key] = deepcopy(job[key])
    return result


def _dummy_rows(dataset_key: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    date_value = _date_value(params)
    if dataset_key in {"production_today", "production"}:
        return _production_rows(date_value)
    if dataset_key in {"wip_today", "wip"}:
        return _wip_rows(date_value)
    if dataset_key == "target":
        return _target_rows(_date_dash(date_value))
    if dataset_key == "lot_status":
        return _lot_status_rows(date_value)
    if dataset_key == "hold_history":
        return _hold_history_rows(params)
    if dataset_key == "equipment_status":
        return _equipment_rows(date_value)
    if dataset_key == "capacity":
        return _capacity_rows(date_value)
    return []


def _production_rows(work_date: str) -> list[dict[str, Any]]:
    rows = []
    for process_index, process in enumerate(PROCESS_ROWS, start=1):
        for product_index, product in enumerate(PRODUCT_ROWS, start=1):
            row = _base_process_product_row(work_date, process, product, process_index, product_index)
            row["PRODUCTION"] = _production_qty(process["PROCESS_FAMILY"], product, process_index, product_index)
            rows.append(row)
    return rows


def _wip_rows(work_date: str) -> list[dict[str, Any]]:
    rows = []
    for process_index, process in enumerate(PROCESS_ROWS, start=1):
        for product_index, product in enumerate(PRODUCT_ROWS, start=1):
            row = _base_process_product_row(work_date, process, product, process_index, product_index)
            row["WIP"] = _wip_qty(process["PROCESS_FAMILY"], product, process_index, product_index)
            rows.append(row)
    return rows


def _base_process_product_row(
    work_date: str,
    process: dict[str, Any],
    product: dict[str, Any],
    process_index: int,
    product_index: int,
) -> dict[str, Any]:
    return {
        "WORK_DT": work_date,
        "WORK_DATE": work_date,
        "SHIFT": str(((process_index + product_index - 2) % 3) + 1),
        "FACTORY": "PKG",
        "FAB": "PKG",
        "ORG": "ASSY",
        **_product_keys(product),
        "FAMILY": product.get("FAMILY", ""),
        "DEVICE_DESC": product.get("DEVICE_DESC", ""),
        "OPER_NUM": process.get("OPER_NUM", ""),
        "OPER": process.get("OPER_NUM", ""),
        "OPER_NAME": process.get("OPER_NAME", ""),
        "OPER_SHORT_DESC": process.get("OPER_SHORT_DESC", ""),
        "OPER_SEQ": process.get("OPER_SEQ", ""),
        "DIE_ATTACH_QTY": int(product.get("DIE_ATTACH_QTY") or 1),
        "NETDIE_300_CNT": int(product.get("NETDIE_300_CNT") or max(_product_base(product) // 10, 1)),
        **_physical_product_aliases(product),
    }


def _target_rows(date_text: str) -> list[dict[str, Any]]:
    rows = []
    for index, product in enumerate(PRODUCT_ROWS, start=1):
        base = _product_base(product) * 22
        input_plan = int(base * (10.5 + (index % 4) * 0.35))
        out_plan = int(base * (0.86 + (index % 5) * 0.025))
        rows.append(
            {
                "DATE": date_text,
                "ORG": "ASSY",
                **_product_keys(product),
                **_physical_product_aliases(product),
                "INPUT_PLAN": input_plan,
                "OUT_PLAN": out_plan,
                "INPUT계획": input_plan,
                "OUT계획": out_plan,
            }
        )
    return rows


def _lot_status_rows(work_date: str) -> list[dict[str, Any]]:
    rows = [
        {
            "WORK_DT": work_date,
            "LOT_ID": "T1234567GEN1",
            "SUB_LOT_ID": "T1234567GEN1-S1",
            "OPER_ID": "DA10",
            "OPER_SHORT_DESC": "D/A1",
            "LOT_STAT_CD": "RUNNING",
            "LOT_HOLD_STAT_CD": "HOLD",
            **_lot_product_fields(PRODUCT_ROWS[0]),
            "SUB_PROD_QTY": 1200,
            "SUB_QTY": 1200,
            "WF_QTY": 25,
            "IN_TAT": 12.5,
            "CUM_TAT": 88.0,
            "EQP_ID": "EQP1001",
            "OPER_IN_TM": _timestamp(work_date, 7, 10),
            "CRT_TM": _timestamp(work_date, 5, 30),
            "FAC_IN_TM": _timestamp(work_date, 4, 0),
            "EVENT_DESC": "RUN",
        }
    ]
    status_cycle = ["WAITING", "RUNNING", "WAITING", "RUNNING"]
    hold_cycle = ["", "", "HOLD", ""]
    lot_index = 1
    lot_processes = [item for item in PROCESS_ROWS if item["PROCESS_FAMILY"] in {"DA", "WB", "BG", "WSD", "DP", "FCB"}]
    for process in lot_processes:
        for product in PRODUCT_ROWS[:12]:
            for slot in range(2):
                lot_index += 1
                sub_qty = int(_product_base(product) * (0.50 + slot * 0.08))
                rows.append(
                    {
                        "WORK_DT": work_date,
                        "LOT_ID": f"LOT{work_date[-4:]}{lot_index:05d}",
                        "SUB_LOT_ID": f"LOT{work_date[-4:]}{lot_index:05d}-S{slot + 1}",
                        "OPER_ID": process.get("OPER_NUM", ""),
                        "OPER_SHORT_DESC": process.get("OPER_SHORT_DESC", ""),
                        "LOT_STAT_CD": status_cycle[(lot_index + slot) % len(status_cycle)],
                        "LOT_HOLD_STAT_CD": hold_cycle[(lot_index + slot) % len(hold_cycle)],
                        **_lot_product_fields(product),
                        "SUB_PROD_QTY": sub_qty,
                        "SUB_QTY": sub_qty,
                        "WF_QTY": 12 + (lot_index % 16),
                        "IN_TAT": round(2.5 + (lot_index % 9) * 0.7, 2),
                        "CUM_TAT": round(18.0 + (lot_index % 40) * 1.9, 2),
                        "EQP_ID": f"EQP{1000 + lot_index % 80}",
                        "OPER_IN_TM": _timestamp(work_date, 6 + lot_index % 12, lot_index % 60),
                        "CRT_TM": _timestamp(work_date, 3 + lot_index % 6, lot_index % 60),
                        "FAC_IN_TM": _timestamp(work_date, 1 + lot_index % 4, lot_index % 60),
                        "EVENT_DESC": "HOLD" if hold_cycle[(lot_index + slot) % len(hold_cycle)] else "MOVE",
                    }
                )
    return [_with_lot_defaults(row) for row in rows]


def _hold_history_rows(params: dict[str, Any]) -> list[dict[str, Any]]:
    work_date = _date_value(params)
    lot_id = str(params.get("LOT_ID") or params.get("lot_id") or "T1234567GEN1")
    lot_rows = [row for row in _lot_status_rows(work_date) if _compare(row.get("LOT_ID"), lot_id)]
    if not lot_rows:
        lot_rows = [_lot_status_rows(work_date)[0]]
        lot_rows[0]["LOT_ID"] = lot_id
    rows = []
    for index, lot in enumerate(lot_rows[:4], start=1):
        rows.append(
            {
                "FAB_ID": "PKG",
                "DEN_TYP": lot.get("DEN_TYP", ""),
                "PROD_ID": lot.get("PROD_ID", ""),
                "GRADE_CD": "A",
                "OWNER_CD": "PNT",
                "OPER_ID": lot.get("OPER_ID", ""),
                "OPER_SHORT_DESC": lot.get("OPER_SHORT_DESC", ""),
                "LOT_ID": lot.get("LOT_ID", ""),
                "OLD_SUB_PROD_QTY": lot.get("SUB_PROD_QTY", 0),
                "HOLD_TM": _timestamp(work_date, 8 + index, 10 + index),
                "RELEASE_DUE_DATE": _date_dash(work_date),
                "HOLD_CD": "QA_HOLD" if index % 2 else "RECIPE_CHECK",
                "HOLD_USER_ID": "qa_user" if index % 2 else "process_eng",
                "HOLD_DESC": "QA review hold" if index % 2 else "Recipe approval check",
                "FAMILY_CD": lot.get("FAMILY_CD", ""),
                "TECH_NM": lot.get("TECH_NM", ""),
                "GEN_TYP": lot.get("PROD_TYP", ""),
                "ORGANIZ_CD": "ASSY",
                "PKG_TYP_2": lot.get("PKG_TYP_2", ""),
                "PKG_SIZE_VAL": "12x12",
                "PROD_GRP_ID": lot.get("PROD_GRP_ID", ""),
                "THK_CD": "STD",
                "MCP_SALE_CD": lot.get("MCP_SALE_CD", lot.get("PROD_GRP_ID", "")),
                "HOLD_GRADE_CD": "H1",
                "FLOW_ID": "FLOW-PKG",
                "FAC_ID": "PKG",
                "EVENT_CD": "HOLD" if index % 2 else "RELEASE",
            }
        )
    return rows


def _equipment_rows(work_date: str) -> list[dict[str, Any]]:
    rows = []
    eqp_index = 1000
    for product_index, product in enumerate(PRODUCT_ROWS, start=1):
        for slot in range(1, 5):
            eqp_index += 1
            model = _equipment_model(product, slot)
            rows.append(
                {
                    "BASE_DT": work_date,
                    "BAY_ID": f"BAY-{(product_index + slot) % 6 + 1:02d}",
                    "EQPID": f"EQP{eqp_index}",
                    "EQP_ID": f"EQP{eqp_index}",
                    "EQP_MODEL": model,
                    "PRESS_CNT": [1, 2, 4, 8][(product_index + slot) % 4],
                    "ORG": "ASSY",
                    "PKGSIZE": ["8x8", "10x10", "12x12", "14x14"][(product_index + slot) % 4],
                    "LOT_ID": "T1234567GEN1" if product.get("DEVICE") == "DEV-HBM3E-16HI" and slot <= 2 else f"LOT{work_date[-4:]}{eqp_index}",
                    "EQP_OPERATYN": "N" if slot == 4 and product.get("PKG_TYPE2") in {"AUTO", "AI"} else "Y",
                    "PI": ["PI_A", "PI_B", "PI_C", "PI_D"][(product_index + slot) % 4],
                    "RECIPE_ID": f"R-{product['MODE']}-{slot:02d}",
                    "DEVICE_DESC": product.get("DEVICE_DESC", ""),
                    **_product_keys(product),
                    **_physical_product_aliases(product),
                }
            )
    return rows


def _capacity_rows(work_date: str) -> list[dict[str, Any]]:
    rows = []
    row_index = 0
    for process in PROCESS_ROWS:
        for product in PRODUCT_ROWS[:12]:
            row_index += 1
            press_count = [1, 2, 4][row_index % 3]
            rows.append(
                {
                    "BASE_DT": work_date,
                    "FAC_ID": "PKG",
                    "EQP_OPER_GRP_CD": process.get("PROCESS_FAMILY", ""),
                    "EQP_OPER_DET_GRP_CD": process.get("OPER_DESC", ""),
                    "EQP_MODEL_CD": _equipment_model(product, row_index),
                    "EQP_MODEL": _equipment_model(product, row_index),
                    "OPER_ID": process.get("OPER_NUM", ""),
                    "OPER_DESC": process.get("OPER_NAME", ""),
                    "PRESS_CNT": press_count,
                    "RECIPE_ID": f"R-{product['MODE']}-{row_index % 5:02d}",
                    "AVG_UPH_VAL": _uph_value(process, product, press_count),
                    **_physical_product_aliases(product),
                    **_product_keys(product),
                }
            )
    return rows


def _product_keys(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "TECH": product.get("TECH", ""),
        "DEN": product.get("DEN", ""),
        "MODE": product.get("MODE", ""),
        "PKG_TYPE1": product.get("PKG_TYPE1", ""),
        "PKG_TYPE2": product.get("PKG_TYPE2", ""),
        "LEAD": product.get("LEAD", ""),
        "MCP_NO": product.get("MCP_NO", ""),
        "TSV_DIE_TYP": product.get("TSV_DIE_TYP", ""),
        "DEVICE": product.get("DEVICE", ""),
    }


def _lot_product_fields(product: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "FAMILY_CD": product.get("FAMILY", ""),
        "PROD_ID": product.get("DEVICE", ""),
        "PROD_TYP": product.get("MODE", ""),
        "DEN_TYP": product.get("DEN", ""),
        "TECH_NM": product.get("TECH", ""),
        "ORGANIZ_CD": "ASSY",
        "PKG_TYP": product.get("PKG_TYPE1", ""),
        "PKG_TYP_2": product.get("PKG_TYPE2", ""),
        "PKG_TYP_3": "",
        "LEAD_CNT": product.get("LEAD", ""),
        "PROD_GRP_ID": product.get("MCP_NO", ""),
        "MCP_SALE_CD": product.get("MCP_NO", ""),
        "TSV_DIE_TYP": product.get("TSV_DIE_TYP", ""),
        **_product_keys(product),
        **_physical_product_aliases(product),
    }
    return fields


def _with_lot_defaults(row: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "ERM_ID": "ERM-PKG",
        "FAB_ID": "PKG",
        "OWNER_CD": "PNT",
        "GRADE_CD": "A",
        "FLOW_ID": "FLOW-PKG",
        "REASON_CD": "",
        "THK_CD": "STD",
        "LOT_GRP_CD": "NORMAL",
        "PKG_SIZE_VAL": "12x12",
        "PKG_DEN_TYP": row.get("DEN_TYP", ""),
        "HOT_LOT_YN": "N",
        "HOT_LEVEL_TYP": "",
        "PKG_COMPOSIT_TYP": "",
        "DURABLE_ID": "",
        "DURABLE_TYP": "",
        "PLANNING_DESC": "",
        "MOVE_IN_TM": row.get("OPER_IN_TM", ""),
        "PAD_ABNORM_YN": "N",
        "SWR_REQ_NO": "",
        "OPER_GRP_VAL_1": row.get("OPER_SHORT_DESC", ""),
        "INSP_TGT_YN": "N",
    }
    merged = {**defaults, **row}
    return merged


def _physical_product_aliases(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "Mode": product.get("MODE"),
        "DENSITY": product.get("DEN"),
        "PKG1": product.get("PKG_TYPE1"),
        "PKG2": product.get("PKG_TYPE2"),
        "PKG_TYP1": product.get("PKG_TYPE1"),
        "MCP NO": product.get("MCP_NO"),
        "MCPSALENO": product.get("MCP_NO"),
        "PROD_TYP": product.get("MODE"),
        "TECH_NM": product.get("TECH"),
        "DEN_TYP": product.get("DEN"),
        "PKG_TYP": product.get("PKG_TYPE1"),
        "PKG_TYP_2": product.get("PKG_TYPE2"),
        "PKG_TYP2": product.get("PKG_TYPE2"),
        "LEAD_CNT": product.get("LEAD"),
        "PROD_GRP_ID": product.get("MCP_NO"),
        "MCP_SALE_CD": product.get("MCP_NO"),
    }


def _production_qty(process_family: str, product: dict[str, Any], process_index: int, product_index: int) -> int:
    factor = {
        "INPUT": 2.8,
        "DA": 1.25,
        "WB": 1.05,
        "BG": 0.62,
        "WSD": 0.70,
        "DP": 0.58,
        "FCB": 0.88,
        "FCBH": 0.78,
        "PKG_OUT": 0.82,
    }.get(process_family, 0.45)
    if product["PKG_TYPE1"] == "HBM" and process_family == "DA":
        factor += 0.42
    if product["MODE"] == "LPDDR5" and process_family == "WB":
        factor += 0.30
    if product["PKG_TYPE2"] == "AUTO" and process_family == "BG":
        factor -= 0.12
    return int((_product_base(product) * factor + process_index * 35 + product_index * 18) * 10)


def _wip_qty(process_family: str, product: dict[str, Any], process_index: int, product_index: int) -> int:
    factor = {
        "DA": 2.55,
        "WB": 2.25,
        "BG": 1.32,
        "WSD": 1.48,
        "DP": 1.12,
        "FCB": 1.65,
        "FCBH": 1.48,
        "INPUT": 0.88,
    }.get(process_family, 0.72)
    if product["DEVICE"] == "DEV-HBM3E-16HI" and process_family == "DA":
        factor += 1.20
    if product["MODE"] == "LPDDR5" and process_family == "WB":
        factor += 0.95
    if product["DEVICE"] == "DEV-HBM3-12HI" and process_family == "DA":
        factor += 0.75
    return int((_product_base(product) * factor + process_index * 55 + product_index * 24) * 10)


def _product_base(product: dict[str, Any]) -> int:
    base = 1200
    if product["PKG_TYPE1"] == "HBM":
        base += 850
    if str(product["MODE"]).startswith("LPDDR5"):
        base += 180
    if product["MODE"] == "DDR5":
        base += 260
    if product["PKG_TYPE2"] in {"AUTO", "SERVER", "AI"}:
        base += 220
    if str(product["DEN"]).startswith("2048"):
        base += 420
    elif str(product["DEN"]).startswith("1536"):
        base += 340
    elif str(product["DEN"]).startswith("1024"):
        base += 260
    return base


def _equipment_model(product: dict[str, Any], slot: int) -> str:
    if product.get("PKG_TYPE1") == "HBM":
        models = ["HBM-3000", "HBM-3200", "HBM-3300", "HBM-3400"]
    elif product.get("TECH") == "WB":
        models = ["WB-9000", "WB-9100", "WB-9200", "WB-9300"]
    elif product.get("TECH") == "FC":
        models = ["DA-7000", "DA-7100", "FC-7200", "FC-7300"]
    elif product.get("TECH") == "POP":
        models = ["POP-6000", "POP-6100", "POP-6200", "POP-6300"]
    else:
        models = ["PKG-5000", "PKG-5100", "PKG-5200", "PKG-5300"]
    return models[(slot - 1) % len(models)]


def _uph_value(process: dict[str, Any], product: dict[str, Any], press_count: int) -> int:
    family = process.get("PROCESS_FAMILY", "")
    value = {"INPUT": 650, "WB": 520, "DA": 390, "BG": 310, "FCB": 340, "FCBH": 330, "PKG_OUT": 460}.get(family, 260)
    if product.get("TECH") == "TSV":
        value -= 55
    if str(product.get("MODE") or "").startswith("LP"):
        value += 35
    return max(60, value + press_count * 18)


def _param_filters(params: dict[str, Any], dataset_key: str) -> list[dict[str, Any]]:
    filters = []
    param_filter_fields = {"DATE", "WORK_DT", "BASE_DT", "MODE", "TECH", "DEN", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "OPER_NAME", "EQP_MODEL", "RECIPE_ID"}
    if dataset_key in {"hold_history"}:
        param_filter_fields.add("LOT_ID")
    for key, value in params.items():
        if value in (None, "", [], {}):
            continue
        field = str(key).strip()
        if not field or field not in param_filter_fields:
            continue
        filters.append({"field": field, "op": "eq", "value": value})
    return filters


def _apply_job_filters(rows: list[dict[str, Any]], filters: Any, apply_missing_field_as_match: bool = True) -> list[dict[str, Any]]:
    if not isinstance(filters, list) or not filters:
        return rows
    filtered = list(rows)
    for condition in filters:
        if not isinstance(condition, dict):
            continue
        field = str(condition.get("field") or "").strip()
        op = str(condition.get("op") or "eq").strip().lower()
        if not field or field == "PRODUCT_GRAIN" or op == "from_state":
            continue
        values = condition.get("values")
        if values is None and "value" in condition:
            values = [condition.get("value")]
        elif not isinstance(values, list):
            values = [values]
        candidates = _field_candidates(field)
        filtered = [
            row
            for row in filtered
            if _row_matches_filter(row, candidates, op, values, apply_missing_field_as_match=apply_missing_field_as_match)
        ]
    return filtered


def _row_matches_filter(
    row: dict[str, Any],
    fields: list[str],
    op: str,
    values: list[Any],
    apply_missing_field_as_match: bool,
) -> bool:
    present_values = [row[field] for field in fields if field in row]
    if not present_values:
        return apply_missing_field_as_match
    if op in {"not_empty", "exists"}:
        return any(value not in (None, "") for value in present_values)
    normalized_values = {_normalize_compare_value(value) for value in values}
    if op in {"in", "eq", "="}:
        return any(_normalize_compare_value(value) in normalized_values for value in present_values)
    if op in {"not_in", "ne", "!="}:
        return all(_normalize_compare_value(value) not in normalized_values for value in present_values)
    if op in {"contains", "like"}:
        return any(any(str(target) in _normalize_compare_value(value) for target in normalized_values) for value in present_values)
    return True


def _field_candidates(field: str) -> list[str]:
    aliases = {
        "DATE": ["DATE", "WORK_DATE", "WORK_DT", "BASE_DT"],
        "WORK_DATE": ["WORK_DATE", "WORK_DT", "DATE", "BASE_DT"],
        "WORK_DT": ["WORK_DT", "DATE", "WORK_DATE", "BASE_DT"],
        "LOT_ID": ["LOT_ID"],
        "OPER_NAME": ["OPER_NAME", "OPER_SHORT_DESC", "OPER_ID", "OPER_DESC"],
        "OPER_SHORT_DESC": ["OPER_SHORT_DESC", "OPER_NAME", "OPER_ID", "OPER_DESC"],
        "LOT_STAT_CD": ["LOT_STAT_CD"],
        "LOT_HOLD_STAT_CD": ["LOT_HOLD_STAT_CD"],
        "PKG_TYPE1": ["PKG_TYPE1", "PKG1", "PKG_TYP1", "PKG_TYP"],
        "PKG_TYPE2": ["PKG_TYPE2", "PKG2", "PKG_TYP2", "PKG_TYP_2"],
        "MCP_NO": ["MCP_NO", "MCP NO", "MCPSALENO", "PROD_GRP_ID", "MCP_SALE_CD"],
        "TECH": ["TECH", "TECH_NM"],
        "DEN": ["DEN", "DENSITY", "DEN_TYP"],
        "MODE": ["MODE", "Mode", "PROD_TYP"],
        "LEAD": ["LEAD", "LEAD_CNT"],
        "TSV_DIE_TYP": ["TSV_DIE_TYP"],
        "DEVICE": ["DEVICE", "DEVICE_CODE"],
        "DEVICE_DESC": ["DEVICE_DESC"],
        "OPER_NUM": ["OPER_NUM", "OPER", "OPER_NO"],
        "OPER_SEQ": ["OPER_SEQ"],
        "DIE_ATTACH_QTY": ["DIE_ATTACH_QTY"],
        "NETDIE_300_CNT": ["NETDIE_300_CNT"],
        "EQP_ID": ["EQP_ID", "EQPID"],
        "EQPID": ["EQPID", "EQP_ID"],
        "EQP_MODEL": ["EQP_MODEL", "EQP_MODEL_CD"],
        "RECIPE_ID": ["RECIPE_ID"],
    }
    return aliases.get(field, [field])


def _project_required_columns(rows: list[dict[str, Any]], columns_value: Any) -> list[dict[str, Any]]:
    if not isinstance(columns_value, list) or not columns_value:
        return rows
    columns = [str(column) for column in columns_value if str(column or "").strip()]
    if not columns:
        return rows
    projected = []
    for row in rows:
        item: dict[str, Any] = {}
        for column in columns:
            for candidate in _field_candidates(column):
                if candidate in row:
                    item[column] = row[candidate]
                    break
            else:
                item[column] = row.get(column)
        projected.append(item)
    return projected


def _rows_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _normalize_compare_value(value: Any) -> str:
    text = str(value if value is not None else "").strip().upper()
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    return text


def _compare(left: Any, right: Any) -> bool:
    return _normalize_compare_value(left) == _normalize_compare_value(right)


def _date_value(params: dict[str, Any]) -> str:
    value = str(params.get("DATE") or params.get("date") or "20260612")
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else "20260612"


def _date_dash(value: str) -> str:
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _timestamp(compact_date: str, hour: int, minute: int = 0) -> str:
    return f"{compact_date[0:4]}-{compact_date[4:6]}-{compact_date[6:8]} {hour % 24:02d}:{minute % 60:02d}:00"


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


# 컴포넌트 설명: 07 Dummy Data Retriever
# Langflow 표시 설명: 로컬 검증용 deterministic 제조 dummy 데이터를 실제 조회 결과와 같은 구조로 생성합니다.
class DummyDataRetriever(Component):

    display_name = "07 Dummy Data Retriever"
    description = "로컬 검증용 deterministic 제조 dummy 데이터를 실제 조회 결과와 같은 구조로 생성합니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 로컬 검증용 deterministic 제조 dummy 데이터를 실제 조회 결과와 같은 구조로 생성합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        payload = retrieve_dummy_data(getattr(self, "payload", None))
        retrieval = payload.get("retrieval_payload", {}) if isinstance(payload.get("retrieval_payload"), dict) else {}
        source_results = retrieval.get("source_results", []) if isinstance(retrieval.get("source_results"), list) else []
        self.status = {

            "route": retrieval.get("route"),
            "source_count": len(source_results),
            "row_count": sum(int(item.get("row_count", 0) or 0) for item in source_results if isinstance(item, dict)),
        }
        return Data(data=payload)
