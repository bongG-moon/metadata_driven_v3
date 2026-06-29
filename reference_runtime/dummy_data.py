from __future__ import annotations

from typing import Any


PROCESS_ROWS = [
    {"OPER_NAME": "D/A1", "OPER_SHORT_DESC": "D/A1", "OPER_NUM": "DA10", "OPER_DESC": "DIE ATTACH", "FAMILY": "DA"},
    {"OPER_NAME": "D/A2", "OPER_SHORT_DESC": "D/A2", "OPER_NUM": "DA20", "OPER_DESC": "DIE ATTACH", "FAMILY": "DA"},
    {"OPER_NAME": "D/A3", "OPER_SHORT_DESC": "D/A3", "OPER_NUM": "DA30", "OPER_DESC": "DIE ATTACH", "FAMILY": "DA"},
    {"OPER_NAME": "D/A4", "OPER_SHORT_DESC": "D/A4", "OPER_NUM": "DA40", "OPER_DESC": "DIE ATTACH", "FAMILY": "DA"},
    {"OPER_NAME": "D/A5", "OPER_SHORT_DESC": "D/A5", "OPER_NUM": "DA50", "OPER_DESC": "DIE ATTACH", "FAMILY": "DA"},
    {"OPER_NAME": "D/A6", "OPER_SHORT_DESC": "D/A6", "OPER_NUM": "DA60", "OPER_DESC": "DIE ATTACH", "FAMILY": "DA"},
    {"OPER_NAME": "W/B1", "OPER_SHORT_DESC": "W/B1", "OPER_NUM": "WB10", "OPER_DESC": "WIRE BOND", "FAMILY": "WB"},
    {"OPER_NAME": "W/B2", "OPER_SHORT_DESC": "W/B2", "OPER_NUM": "WB20", "OPER_DESC": "WIRE BOND", "FAMILY": "WB"},
    {"OPER_NAME": "W/B3", "OPER_SHORT_DESC": "W/B3", "OPER_NUM": "WB30", "OPER_DESC": "WIRE BOND", "FAMILY": "WB"},
    {"OPER_NAME": "W/B4", "OPER_SHORT_DESC": "W/B4", "OPER_NUM": "WB40", "OPER_DESC": "WIRE BOND", "FAMILY": "WB"},
    {"OPER_NAME": "W/B5", "OPER_SHORT_DESC": "W/B5", "OPER_NUM": "WB50", "OPER_DESC": "WIRE BOND", "FAMILY": "WB"},
    {"OPER_NAME": "W/B6", "OPER_SHORT_DESC": "W/B6", "OPER_NUM": "WB60", "OPER_DESC": "WIRE BOND", "FAMILY": "WB"},
    {"OPER_NAME": "B/G1", "OPER_SHORT_DESC": "B/G1", "OPER_NUM": "BG10", "OPER_DESC": "BACK GRIND", "FAMILY": "BG"},
    {"OPER_NAME": "B/G2", "OPER_SHORT_DESC": "B/G2", "OPER_NUM": "BG20", "OPER_DESC": "BACK GRIND", "FAMILY": "BG"},
    {"OPER_NAME": "WSD1", "OPER_SHORT_DESC": "WSD1", "OPER_NUM": "WS10", "OPER_DESC": "WAFER SAW DICE", "FAMILY": "WSD"},
    {"OPER_NAME": "WSD2", "OPER_SHORT_DESC": "WSD2", "OPER_NUM": "WS20", "OPER_DESC": "WAFER SAW DICE", "FAMILY": "WSD"},
    {"OPER_NAME": "D/P1", "OPER_SHORT_DESC": "D/P1", "OPER_NUM": "DP10", "OPER_DESC": "D/P FRONT", "FAMILY": "DP"},
    {"OPER_NAME": "D/P2", "OPER_SHORT_DESC": "D/P2", "OPER_NUM": "DP20", "OPER_DESC": "D/P FRONT", "FAMILY": "DP"},
    {"OPER_NAME": "D/S1", "OPER_SHORT_DESC": "D/S1", "OPER_NUM": "DS10", "OPER_DESC": "DIE SORT", "FAMILY": "DS"},
    {"OPER_NAME": "D/S2", "OPER_SHORT_DESC": "D/S2", "OPER_NUM": "DS20", "OPER_DESC": "DIE SORT", "FAMILY": "DS"},
    {"OPER_NAME": "FCB1", "OPER_SHORT_DESC": "FCB1", "OPER_NUM": "FC10", "OPER_DESC": "FLIP CHIP BOND", "FAMILY": "FCB"},
    {"OPER_NAME": "FCB2", "OPER_SHORT_DESC": "FCB2", "OPER_NUM": "FC20", "OPER_DESC": "FLIP CHIP BOND", "FAMILY": "FCB"},
    {"OPER_NAME": "FCBH1", "OPER_SHORT_DESC": "FCBH1", "OPER_NUM": "FH10", "OPER_DESC": "FCB HIGH", "FAMILY": "FCBH"},
    {"OPER_NAME": "FCBH2", "OPER_SHORT_DESC": "FCBH2", "OPER_NUM": "FH20", "OPER_DESC": "FCB HIGH", "FAMILY": "FCBH"},
    {"OPER_NAME": "B/M1", "OPER_SHORT_DESC": "B/M1", "OPER_NUM": "BM10", "OPER_DESC": "BACK MARK", "FAMILY": "BM"},
    {"OPER_NAME": "B/M2", "OPER_SHORT_DESC": "B/M2", "OPER_NUM": "BM20", "OPER_DESC": "BACK MARK", "FAMILY": "BM"},
    {"OPER_NAME": "INPUT", "OPER_SHORT_DESC": "INPUT", "OPER_NUM": "IN10", "OPER_DESC": "INPUT", "FAMILY": "INPUT"},
    {"OPER_NAME": "SHIP PKT", "OPER_SHORT_DESC": "SHIP PKT", "OPER_NUM": "PK10", "OPER_DESC": "PACKAGE OUT", "FAMILY": "PKG_OUT"},
]


PRODUCT_ROWS = [
    {"TECH": "TSV", "DEN": "2048G", "MODE": "HBM3E", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM16E", "TSV_DIE_TYP": "16Hi", "DEVICE": "DEV-HBM3E-16HI"},
    {"TECH": "TSV", "DEN": "1536G", "MODE": "HBM3", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM12A", "TSV_DIE_TYP": "12Hi", "DEVICE": "DEV-HBM3-12HI"},
    {"TECH": "TSV", "DEN": "1024G", "MODE": "HBM3", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM8A", "TSV_DIE_TYP": "8Hi", "DEVICE": "DEV-HBM3-8HI"},
    {"TECH": "TSV", "DEN": "512G", "MODE": "HBM2E", "PKG_TYPE1": "HBM", "PKG_TYPE2": "HBM", "LEAD": "LF", "MCP_NO": "H-HBM4E", "TSV_DIE_TYP": "4Hi", "DEVICE": "DEV-HBM2E-4HI"},
    {"TECH": "FC", "DEN": "128G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "EMPTY", "TSV_DIE_TYP": "", "DEVICE": "DEV-LP5-MOBILE"},
    {"TECH": "FC", "DEN": "256G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "EDGE", "LEAD": "LF", "MCP_NO": "L-269E1D", "TSV_DIE_TYP": "", "DEVICE": "DEV-LP5-EDGE"},
    {"TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "POP", "LEAD": "LF", "MCP_NO": "L-269P1Q", "TSV_DIE_TYP": "", "DEVICE": "DEV-LP5-POP"},
    {"TECH": "FC", "DEN": "256G", "MODE": "LPDDR5X", "PKG_TYPE1": "UFBGA", "PKG_TYPE2": "MOBILE", "LEAD": "LF", "MCP_NO": "L-55XM2Q", "TSV_DIE_TYP": "", "DEVICE": "DEV-LP5X-MOBILE"},
    {"TECH": "WB", "DEN": "512G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "AUTO", "LEAD": "LF", "MCP_NO": "L-111K1Q", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR5-AUTO"},
    {"TECH": "WB", "DEN": "256G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "STD", "LEAD": "LF", "MCP_NO": "L-222K1A", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR5-STD"},
    {"TECH": "WB", "DEN": "1024G", "MODE": "DDR5", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "SERVER", "LEAD": "LF", "MCP_NO": "L-555S1E", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR5-SERVER"},
    {"TECH": "WB", "DEN": "128G", "MODE": "DDR5", "PKG_TYPE1": "FBGA", "PKG_TYPE2": "CLIENT", "LEAD": "LF", "MCP_NO": "L-138C1L", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR5-CLIENT"},
    {"TECH": "RG", "DEN": "256G", "MODE": "DDR4", "PKG_TYPE1": "FBGA", "PKG_TYPE2": "AUTO", "LEAD": "LF", "MCP_NO": "R-401A1U", "TSV_DIE_TYP": "", "DEVICE": "DEV-DDR4-AUTO"},
    {"TECH": "FC", "DEN": "512G", "MODE": "GDDR7", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "AI", "LEAD": "LF", "MCP_NO": "G-777A2I", "TSV_DIE_TYP": "", "DEVICE": "DEV-GDDR7-AI"},
    {"TECH": "POP", "DEN": "128G", "MODE": "MCP", "PKG_TYPE1": "LFBGA", "PKG_TYPE2": "MCP", "LEAD": "LF", "MCP_NO": "L-269M2B", "TSV_DIE_TYP": "", "DEVICE": "DEV-MCP-128"},
    {"TECH": "WB", "DEN": "256G", "MODE": "GDDR6", "PKG_TYPE1": "FCBGA", "PKG_TYPE2": "GRAPHICS", "LEAD": "LF", "MCP_NO": "G-626G1R", "TSV_DIE_TYP": "", "DEVICE": "DEV-GDDR6-GRAPHICS"},
]


def generate_dummy_rows(dataset_key: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    params = params or {}
    date_value = _date_value(params)
    if dataset_key in {"production_today", "production"}:
        work_date = date_value if dataset_key == "production_today" else "20260611"
        return _production_rows(work_date)
    if dataset_key in {"wip_today", "wip"}:
        work_date = date_value if dataset_key == "wip_today" else "20260611"
        return _wip_rows(work_date)
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
            row["PRODUCTION"] = _production_qty(process["FAMILY"], product, process_index, product_index)
            rows.append(row)
    return rows


def _wip_rows(work_date: str) -> list[dict[str, Any]]:
    rows = []
    for process_index, process in enumerate(PROCESS_ROWS, start=1):
        for product_index, product in enumerate(PRODUCT_ROWS, start=1):
            row = _base_process_product_row(work_date, process, product, process_index, product_index)
            row["WIP"] = _wip_qty(process["FAMILY"], product, process_index, product_index)
            rows.append(row)
    return rows


def _base_process_product_row(
    work_date: str,
    process: dict[str, Any],
    product: dict[str, Any],
    process_index: int,
    product_index: int,
) -> dict[str, Any]:
    base = _product_base(product)
    return {
        "WORK_DT": work_date,
        "WORK_DATE": work_date,
        "SHIFT": str(((process_index + product_index - 2) % 3) + 1),
        "FACTORY": "PKG",
        "FAB": "PKG",
        "ORG": "ASSY",
        **process,
        **product,
        "DENSITY": product.get("DEN"),
        "PKG1": product.get("PKG_TYPE1"),
        "PKG2": product.get("PKG_TYPE2"),
        "OPER": process.get("OPER_NUM"),
        "OPER_SEQ": base % 100 + 1,
        "DIE_ATTACH_QTY": 1,
        "NETDIE_300_CNT": max(base // 10, 1),
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
                **_product_keys(product),
                **_physical_product_aliases(product),
                "INPUT_PLAN": input_plan,
                "OUT_PLAN": out_plan,
                "INPUT 계획": input_plan,
                "OUT 계획": out_plan,
                "INPUT계획": input_plan,
                "OUT계획": out_plan,
            }
        )
    return rows


def _lot_status_rows(work_date: str) -> list[dict[str, Any]]:
    rows = [
        {
            "LOT_ID": "T1234567GEN1",
            "OPER_SHORT_DESC": "D/A1",
            "LOT_STAT_CD": "RUNNING",
            "LOT_HOLD_STAT_CD": "HOLD",
            **_product_keys(PRODUCT_ROWS[0]),
            **_physical_product_aliases(PRODUCT_ROWS[0]),
            "SUB_PROD_QTY": 1200,
            "WF_QTY": 25,
            "IN_TAT": 12.5,
            "CUM_TAT": 88.0,
            "EQP_ID": "EQP1001",
            "WORK_DT": work_date,
        }
    ]
    status_cycle = ["WAITING", "RUNNING", "WAITING", "RUNNING"]
    hold_cycle = ["", "", "HOLD", ""]
    lot_index = 1
    lot_processes = [p for p in PROCESS_ROWS if p["FAMILY"] in {"DA", "WB", "BG", "WSD", "DP", "FCB"}]
    for process in lot_processes:
        for product in PRODUCT_ROWS[:12]:
            for slot in range(2):
                lot_index += 1
                rows.append(
                    {
                        "LOT_ID": f"LOT{work_date[-4:]}{lot_index:05d}",
                        "OPER_SHORT_DESC": process["OPER_SHORT_DESC"],
                        "LOT_STAT_CD": status_cycle[(lot_index + slot) % len(status_cycle)],
                        "LOT_HOLD_STAT_CD": hold_cycle[(lot_index + slot) % len(hold_cycle)],
                        **_product_keys(product),
                        **_physical_product_aliases(product),
                        "SUB_PROD_QTY": int(_product_base(product) * (0.50 + slot * 0.08)),
                        "WF_QTY": 12 + (lot_index % 16),
                        "IN_TAT": round(2.5 + (lot_index % 9) * 0.7, 2),
                        "CUM_TAT": round(18.0 + (lot_index % 40) * 1.9, 2),
                        "EQP_ID": f"EQP{1000 + lot_index % 80}",
                        "WORK_DT": work_date,
                    }
                )
    return rows


def _hold_history_rows(params: dict[str, Any]) -> list[dict[str, Any]]:
    lot_id = str(params.get("LOT_ID") or params.get("lot_id") or "T1234567GEN1")
    rows = [
        {
            "LOT_ID": "T1234567GEN1",
            "HOLD_TM": "2026-06-12 09:10:00",
            "HOLD_CD": "QA_HOLD",
            "HOLD_DESC": "QA review hold for HBM stack inspection",
            "HOLD_USER_ID": "qa_user",
            "EVENT_CD": "HOLD",
        },
        {
            "LOT_ID": "T1234567GEN1",
            "HOLD_TM": "2026-06-12 11:30:00",
            "HOLD_CD": "RECIPE_CHECK",
            "HOLD_DESC": "Recipe approval check",
            "HOLD_USER_ID": "process_eng",
            "EVENT_CD": "RELEASE",
        },
    ]
    return [row for row in rows if row["LOT_ID"] == lot_id] or rows


def _equipment_rows(work_date: str) -> list[dict[str, Any]]:
    rows = []
    model_by_family = {"HBM": "DA-HBM", "MOBILE": "WB-MOBILE", "AUTO": "BG-AUTO", "SERVER": "DA-SERVER"}
    eqp_index = 1000
    for product in PRODUCT_ROWS:
        product_family = product["PKG_TYPE2"] if product["PKG_TYPE1"] != "HBM" else "HBM"
        prefix = model_by_family.get(product_family, "PKG-GEN")
        for slot in range(3):
            eqp_index += 1
            rows.append(
                {
                    "EQPID": f"EQP{eqp_index}",
                    "EQP_ID": f"EQP{eqp_index}",
                    "EQP_MODEL": f"{prefix}-{chr(65 + slot)}",
                    "PRESS_CNT": 1 + (slot % 3),
                    **_product_keys(product),
                    **_physical_product_aliases(product),
                    "LOT_ID": "T1234567GEN1" if product["DEVICE"] == "DEV-HBM3E-16HI" and slot < 2 else f"LOT{work_date[-4:]}{eqp_index}",
                    "RECIPE_ID": f"R-{product['MODE']}-{slot + 1:02d}",
                    "BASE_DT": work_date,
                }
            )
    return rows


def _capacity_rows(work_date: str) -> list[dict[str, Any]]:
    rows = []
    for index, product in enumerate(PRODUCT_ROWS, start=1):
        for slot in range(2):
            eqp_model = f"CAPA-{product['PKG_TYPE1']}-{slot + 1}"
            rows.append(
                {
                    "BASE_DT": work_date,
                    "EQPID": f"EQP{2000 + index * 10 + slot}",
                    "EQP_ID": f"EQP{2000 + index * 10 + slot}",
                    "EQP_MODEL": eqp_model,
                    "EQP_MODEL_CD": eqp_model,
                    "RECIPE_ID": f"R-{product['MODE']}-{slot + 1:02d}",
                    "AVG_UPH_VAL": int(650 + _product_base(product) * 0.25 + slot * 80),
                    "PRESS_CNT": 1 + slot,
                    **_product_keys(product),
                    **_physical_product_aliases(product),
                }
            )
    return rows


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
    if product["MODE"].startswith("LPDDR5"):
        base += 180
    if product["MODE"] == "DDR5":
        base += 260
    if product["PKG_TYPE2"] in {"AUTO", "SERVER", "AI"}:
        base += 220
    if product["DEN"].startswith("2048"):
        base += 420
    elif product["DEN"].startswith("1536"):
        base += 340
    elif product["DEN"].startswith("1024"):
        base += 260
    return base


def _product_keys(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "TECH": product["TECH"],
        "DEN": product["DEN"],
        "MODE": product["MODE"],
        "PKG_TYPE1": product["PKG_TYPE1"],
        "PKG_TYPE2": product["PKG_TYPE2"],
        "LEAD": product["LEAD"],
        "MCP_NO": product["MCP_NO"],
        "TSV_DIE_TYP": product.get("TSV_DIE_TYP", ""),
        "DEVICE": product.get("DEVICE", ""),
    }


def _date_value(params: dict[str, Any]) -> str:
    value = str(params.get("DATE") or params.get("date") or "20260612")
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else "20260612"


def _date_dash(value: str) -> str:
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
