from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_component(path: str):
    component_path = ROOT / path
    spec = importlib.util.spec_from_file_location(component_path.stem, component_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_pandas_executor_drops_redundant_source_alias_columns_before_llm_code_runs() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "low_output_vs_target",
            "product_grain": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
            "production_column": "PRODUCTION",
            "target_column": "OUT_PLAN",
            "threshold": 1.0,
            "retrieval_jobs": [
                {"dataset_key": "production_today", "source_alias": "production_data"},
                {
                    "dataset_key": "target",
                    "source_alias": "target_data",
                    "standard_column_aliases": {
                        "MODE": ["Mode"],
                        "PKG_TYPE1": ["PKG1"],
                        "PKG_TYPE2": ["PKG2"],
                        "MCP_NO": ["MCP NO"],
                    },
                },
            ],
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {
                    "TECH": "FC",
                    "DEN": "128G",
                    "MODE": "LPDDR5",
                    "PKG_TYPE1": "UFBGA",
                    "PKG_TYPE2": "MOBILE",
                    "LEAD": "LF",
                    "MCP_NO": "EMPTY",
                    "PRODUCTION": 10,
                }
            ],
            "target_data": [
                {
                    "TECH": "FC",
                    "DEN": "128G",
                    "Mode": "LPDDR5",
                    "MODE": "LPDDR5",
                    "PKG1": "UFBGA",
                    "PKG_TYPE1": "UFBGA",
                    "PKG2": "MOBILE",
                    "PKG_TYPE2": "MOBILE",
                    "LEAD": "LF",
                    "MCP NO": "EMPTY",
                    "MCP_NO": "EMPTY",
                    "OUT_PLAN": 20,
                }
            ],
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "product_grain = plan['product_grain']",
                "production_df = sources['production_data'].copy()",
                "production_agg = production_df.groupby(product_grain, as_index=False)['PRODUCTION'].sum()",
                "target_df = sources['target_data'].copy()",
                "target_agg = target_df.groupby(product_grain, as_index=False)['OUT_PLAN'].sum()",
                "target_agg = target_agg.rename(columns={'OUT_PLAN': 'TARGET_QTY'})",
                "result_df = production_agg.merge(target_agg, on=product_grain, how='outer')",
                "result_df['ACHIEVEMENT_RATE'] = result_df['PRODUCTION'].div(result_df['TARGET_QTY']).fillna(0)",
                "result_df['BALANCE'] = result_df['PRODUCTION'] - result_df['TARGET_QTY']",
                "result_df['LOW_OUTPUT_FLAG'] = result_df['ACHIEVEMENT_RATE'] < plan.get('threshold', 1.0)",
            ]
        ),
        "output_columns": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "PRODUCTION", "TARGET_QTY"],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 1
    assert result["analysis"]["rows"][0]["TARGET_QTY"] == 20


def test_pandas_executor_datetime_import_error_guides_repair() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "date_format_test",
            "retrieval_jobs": [{"dataset_key": "production_today", "source_alias": "production_data"}],
        },
        "state": {},
        "runtime_sources": {"production_data": [{"DATE": "20260623", "PRODUCTION": 10}]},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "import datetime",
                "target_date = datetime.datetime.strptime('20260623', '%Y%m%d')",
                "result_df = sources['production_data'].copy()",
            ]
        ),
        "output_columns": ["DATE", "PRODUCTION"],
        "reasoning_steps": ["Convert the date with datetime."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "error"
    assert result["analysis"]["executed"] is False
    assert result["analysis"]["safety_passed"] is False
    assert "Imports are not allowed in generated pandas code." in result["analysis"]["errors"]
    assert "Use pd.to_datetime and pandas string/date operations instead of importing datetime." in result["analysis"]["errors"]


def test_pandas_executor_normalizes_lot_process_column_alias() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {"analysis_kind": "lot_count_by_process"},
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "result_df = pd.DataFrame([{'OPER_NAME': 'D/A1', 'LOT_COUNT': 2}])",
        "output_columns": ["OPER_NAME", "LOT_COUNT"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["OPER_SHORT_DESC", "LOT_COUNT"]
    assert result["analysis"]["rows"][0]["OPER_SHORT_DESC"] == "D/A1"


def test_pandas_executor_replaces_incomplete_top_wip_process_lot_metrics_result() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "top_wip_process_hold_lot_in_tat",
            "top_n": 3,
            "analysis_output_columns": ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"],
            "retrieval_jobs": [
                {"dataset_key": "wip_today", "source_alias": "wip_data"},
                {"dataset_key": "lot_status", "source_alias": "lot_status_data"},
            ],
            "step_plan": [
                {"operation": "rank_top_n", "source_alias": "wip_data", "metric": "WIP", "group_by": ["OPER_NAME"], "top_n": 3},
                {"operation": "hold_lot_in_tat_by_process", "source_alias": "lot_status_data"},
            ],
        },
        "state": {},
        "runtime_sources": {
            "wip_data": [
                {"OPER_NAME": "D/A1", "WIP": 100},
                {"OPER_NAME": "D/A2", "WIP": 80},
                {"OPER_NAME": "D/A3", "WIP": 150},
                {"OPER_NAME": "D/A4", "WIP": 10},
            ],
            "lot_status_data": [
                {"OPER_SHORT_DESC": "D/A3", "LOT_ID": "L31", "LOT_HOLD_STAT_CD": "HOLD", "IN_TAT": 10},
                {"OPER_SHORT_DESC": "D/A3", "LOT_ID": "L32", "LOT_HOLD_STAT_CD": "NotOnHold", "IN_TAT": 20},
                {"OPER_SHORT_DESC": "D/A1", "LOT_ID": "L11", "LOT_HOLD_STAT_CD": "NotOnHold", "IN_TAT": 5},
                {"OPER_SHORT_DESC": "D/A1", "LOT_ID": "L12", "LOT_HOLD_STAT_CD": "HOLD", "IN_TAT": 15},
                {"OPER_SHORT_DESC": "D/A2", "LOT_ID": "L21", "LOT_HOLD_STAT_CD": "OnHold", "IN_TAT": 40},
                {"OPER_SHORT_DESC": "D/A2", "LOT_ID": "L22", "LOT_HOLD_STAT_CD": "NotOnHold", "IN_TAT": 20},
            ],
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "filtered_df = sources['lot_status_data']",
                "result_df = filtered_df.groupby('OPER_SHORT_DESC')['LOT_ID'].nunique().reset_index(name='LOT_COUNT')",
            ]
        ),
        "output_columns": ["OPER_SHORT_DESC", "LOT_COUNT"],
        "reasoning_steps": ["Only count lots by process."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"]
    assert result["analysis"]["rows"] == [
        {"OPER_SHORT_DESC": "D/A3", "WIP": 150, "HOLD_LOT_COUNT": 1, "AVG_IN_TAT": 15.0},
        {"OPER_SHORT_DESC": "D/A1", "WIP": 100, "HOLD_LOT_COUNT": 1, "AVG_IN_TAT": 10.0},
        {"OPER_SHORT_DESC": "D/A2", "WIP": 80, "HOLD_LOT_COUNT": 1, "AVG_IN_TAT": 30.0},
    ]
    assert "missed required plan output columns" in result["analysis"]["analysis_code"]


def test_pandas_executor_does_not_apply_specific_lot_fallback_without_recipe_or_step() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "multi_step_analysis",
            "analysis_output_columns": ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"],
            "retrieval_jobs": [
                {"dataset_key": "wip_today", "source_alias": "wip_data"},
                {"dataset_key": "lot_status", "source_alias": "lot_data"},
            ],
            "step_plan": [
                {
                    "step_id": "custom_lot_summary",
                    "operation": "custom_unregistered_lot_summary",
                    "source_alias": "lot_data",
                    "output_columns": ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"],
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "wip_data": [{"OPER_SHORT_DESC": "WB", "WIP": 100}],
            "lot_data": [{"OPER_SHORT_DESC": "WB", "LOT_ID": "LOT1", "LOT_HOLD_STAT_CD": "HOLD", "IN_TAT": 30}],
        },
    }
    pandas_llm_json = {
        "code": "result_df = pd.DataFrame(columns=['OPER_SHORT_DESC', 'WIP', 'HOLD_LOT_COUNT', 'AVG_IN_TAT'])",
        "output_columns": ["OPER_SHORT_DESC", "WIP", "HOLD_LOT_COUNT", "AVG_IN_TAT"],
        "reasoning_steps": ["No deterministic registered recipe was selected."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["row_count"] == 0
    assert result["analysis"]["used_executor_fallback"] is False
    assert "executor_fallback" not in result["analysis"]["analysis_code"]


def test_pandas_executor_errors_when_required_source_columns_are_missing() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "retrieval_jobs": [
                {
                    "dataset_key": "lot_status",
                    "source_alias": "lot_data",
                    "required_columns": ["LOT_ID", "LOT_HOLD_STAT_CD", "HOLD_TM", "REASON_CD", "TECH_NM"],
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "lot_data": [
                {"LOT_ID": "LOT1", "LOT_HOLD_STAT_CD": "HOLD", "TECH": "FC"},
            ]
        },
    }
    pandas_llm_json = {
        "code": "result_df = sources['lot_data'][['LOT_ID', 'LOT_HOLD_STAT_CD', 'HOLD_TM', 'REASON_CD', 'TECH_NM']]",
        "output_columns": ["LOT_ID", "LOT_HOLD_STAT_CD", "HOLD_TM", "REASON_CD", "TECH_NM"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "error"
    assert result["analysis"]["errors"] == [
        "Runtime source 'lot_data' is missing required columns: HOLD_TM, REASON_CD, TECH_NM"
    ]
    assert result["analysis"]["executed"] is False


def test_pandas_executor_copies_required_columns_from_real_aliases_only() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "retrieval_jobs": [
                {
                    "dataset_key": "lot_status",
                    "source_alias": "lot_data",
                    "required_columns": ["LOT_ID", "TECH_NM"],
                    "standard_column_aliases": {"TECH_NM": ["TECH"]},
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "lot_data": [
                {"LOT_ID": "LOT1", "TECH": "FC"},
            ]
        },
    }
    pandas_llm_json = {
        "code": "result_df = sources['lot_data'][['LOT_ID', 'TECH_NM']]",
        "output_columns": ["LOT_ID", "TECH_NM"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"][0] == {"LOT_ID": "LOT1", "TECH_NM": "FC"}


def test_pandas_executor_does_not_hide_missing_group_columns_with_fallback() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "aggregate_previous_source",
            "retrieval_jobs": [
                {
                    "dataset_key": "production",
                    "source_alias": "production_data",
                    "required_columns": ["DEVICE", "DEVICE_DESC", "PRODUCTION"],
                }
            ],
            "step_plan": [
                {"source_alias": "production_data", "group_by": ["DEVICE", "DEVICE_DESC"], "metric": "PRODUCTION"}
            ],
            "metric": "PRODUCTION",
            "product_grain": ["DEVICE", "DEVICE_DESC"],
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {"PRODUCTION": 10},
                {"PRODUCTION": 20},
            ]
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "production_data_df = sources['production_data']",
                "result_df = production_data_df.groupby(['DEVICE', 'DEVICE_DESC'])['PRODUCTION'].sum().reset_index()",
                "result_df = result_df[['DEVICE', 'DEVICE_DESC', 'PRODUCTION']]",
            ]
        ),
        "output_columns": ["DEVICE", "DEVICE_DESC", "PRODUCTION"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "error"
    assert result["analysis"]["errors"] == [
        "Runtime source 'production_data' is missing required columns: DEVICE, DEVICE_DESC"
    ]
    assert "executor_fallback" not in result["analysis"]["analysis_code"]


def test_pandas_executor_does_not_derive_rank_group_without_rank_groups() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "rank_wip_then_join_production",
            "product_grain": ["TECH"],
        },
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "result_df = pd.DataFrame([{'OPER_NAME': 'D/A1', 'WIP_RANK': 1, 'TECH': 'TSV', 'WIP': 10, 'PRODUCTION': 7}])",
        "output_columns": ["OPER_NAME", "WIP_RANK", "TECH", "WIP", "PRODUCTION"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert "RANK_GROUP" not in result["analysis"]["columns"]
    assert "RANK_GROUP" not in result["analysis"]["rows"][0]


def test_pandas_executor_falls_back_for_lot_quantity_summary_to_frame_error() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "lot_quantity_summary",
            "step_plan": [{"source_alias": "lot_data"}],
        },
        "state": {},
        "runtime_sources": {
            "lot_data": [
                {"LOT_ID": "LOT1", "WF_QTY": 2, "SUB_PROD_QTY": 10},
                {"LOT_ID": "LOT1", "WF_QTY": 3, "SUB_PROD_QTY": 20},
                {"LOT_ID": "LOT2", "WF_QTY": 4, "SUB_PROD_QTY": 30},
            ]
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "aggregated_data = sources['lot_data'].agg(",
                "    LOT_COUNT=('LOT_ID', 'nunique'),",
                "    WF_QTY=('WF_QTY', 'sum'),",
                "    DIE_QTY=('SUB_PROD_QTY', 'sum')",
                ")",
                "result_df = aggregated_data.to_frame().T",
            ]
        ),
        "output_columns": ["LOT_COUNT", "WF_QTY", "DIE_QTY"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"][0] == {"LOT_COUNT": 2, "WF_QTY": 9, "DIE_QTY": 60}


def test_pandas_executor_falls_back_for_previous_source_aggregation() -> None:
    payload = {
        "intent_plan": {
            "analysis_kind": "aggregate_previous_source",
            "product_grain": ["MODE", "DEVICE"],
            "metric": "PRODUCTION",
            "step_plan": [
                {
                    "source_alias": "production_data",
                    "group_by": ["MODE", "DEVICE"],
                    "metric": "PRODUCTION",
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "production_data": [
                {"MODE": "LPDDR5", "DEVICE": "D1", "PRODUCTION": 10},
                {"MODE": "LPDDR5", "DEVICE": "D1", "PRODUCTION": 15},
                {"MODE": "LPDDR5", "DEVICE": "D2", "PRODUCTION": 20},
            ]
        },
    }
    pandas_llm_json = {
        "code": "result_df = missing_previous_source_df",
        "output_columns": ["MODE", "DEVICE", "PRODUCTION"],
        "reasoning_steps": [],
    }

    for executor_path in [
        "langflow_components/data_analysis_flow/15_pandas_code_executor.py",
        "langflow_components/data_analysis_flow/15_pandas_code_executor.py",
    ]:
        pandas_executor = load_component(executor_path)
        result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

        assert result["analysis"]["status"] == "ok"
        assert result["analysis"]["rows"] == [
            {"MODE": "LPDDR5", "DEVICE": "D1", "PRODUCTION": 25},
            {"MODE": "LPDDR5", "DEVICE": "D2", "PRODUCTION": 20},
        ]


def test_pandas_executor_falls_back_from_generic_aggregate_step_primitive() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "generic_aggregate_recipe",
            "analysis_output_columns": ["MODE", "DEVICE", "PRODUCTION", "WIP"],
            "step_plan": [
                {
                    "step_id": "sum_by_product",
                    "operation": "aggregate_sum_by_group",
                    "source_alias": "mixed_source",
                    "group_by": ["MODE", "DEVICE"],
                    "metrics": ["PRODUCTION", "WIP"],
                    "aggregation": "sum",
                    "output_columns": ["MODE", "DEVICE", "PRODUCTION", "WIP"],
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "mixed_source": [
                {"MODE": "A", "DEVICE": "D1", "PRODUCTION": 10, "WIP": 3},
                {"MODE": "A", "DEVICE": "D1", "PRODUCTION": 5, "WIP": 2},
                {"MODE": "B", "DEVICE": "D2", "PRODUCTION": 7, "WIP": 4},
            ]
        },
    }
    pandas_llm_json = {
        "code": "result_df = pd.DataFrame(columns=['MODE', 'DEVICE', 'PRODUCTION', 'WIP'])",
        "output_columns": ["MODE", "DEVICE", "PRODUCTION", "WIP"],
        "reasoning_steps": ["The generated code failed to implement the aggregate step."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["MODE", "DEVICE", "PRODUCTION", "WIP"]
    assert result["analysis"]["rows"] == [
        {"MODE": "A", "DEVICE": "D1", "PRODUCTION": 15, "WIP": 5},
        {"MODE": "B", "DEVICE": "D2", "PRODUCTION": 7, "WIP": 4},
    ]
    assert "executor_fallback" in result["analysis"]["analysis_code"]


def test_pandas_executor_collapses_over_detailed_metric_aggregate_result() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "generic_aggregate_recipe",
            "result_scope_columns": [{"column": "OPER_GROUP", "value": "WB", "source_field": "OPER_NAME"}],
            "analysis_output_columns": ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
            "step_plan": [
                {
                    "step_id": "aggregate_metric_outputs",
                    "operation": "aggregate_sum_by_group",
                    "source_alias": "production_today",
                    "group_by": [],
                    "metrics": ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
                    "aggregation": "sum",
                    "output_columns": ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "production_today": [
                {"OPER_NAME": "W/B1", "PRODUCTION": 100, "NETDIE_300_CNT": 10},
                {"OPER_NAME": "W/B2", "PRODUCTION": 50, "NETDIE_300_CNT": 0},
            ]
        },
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "result_df = pd.DataFrame([",
                "    {'WAFER_OUT_QTY': 10.0, 'FAIL_UNIT_QTY': 0.0},",
                "    {'WAFER_OUT_QTY': 0.0, 'FAIL_UNIT_QTY': 50.0},",
                "    {'WAFER_OUT_QTY': 2.5, 'FAIL_UNIT_QTY': 3.0},",
                "])",
            ]
        ),
        "output_columns": ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
        "reasoning_steps": ["The generated code calculated row-level wafer quantities but forgot to aggregate."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["OPER_GROUP", "WAFER_OUT_QTY", "FAIL_UNIT_QTY"]
    assert result["analysis"]["rows"] == [{"OPER_GROUP": "WB", "WAFER_OUT_QTY": 12.5, "FAIL_UNIT_QTY": 53.0}]


def test_pandas_executor_does_not_collapse_union_after_intermediate_aggregates() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "multi_source_analysis",
            "analysis_output_columns": ["OPER_GROUP", "PRODUCTION", "WIP"],
            "step_plan": [
                {
                    "step_id": "agg_prod_da",
                    "operation": "aggregate_sum",
                    "group_by": [],
                    "metrics": ["PRODUCTION"],
                    "output_columns": ["OPER_GROUP", "PRODUCTION"],
                },
                {
                    "step_id": "agg_wip_da",
                    "operation": "aggregate_sum",
                    "group_by": [],
                    "metrics": ["WIP"],
                    "output_columns": ["OPER_GROUP", "WIP"],
                },
                {"step_id": "join_da", "operation": "left_join", "output_columns": ["OPER_GROUP", "PRODUCTION", "WIP"]},
                {
                    "step_id": "agg_prod_wb",
                    "operation": "aggregate_sum",
                    "group_by": [],
                    "metrics": ["PRODUCTION"],
                    "output_columns": ["OPER_GROUP", "PRODUCTION"],
                },
                {
                    "step_id": "agg_wip_wb",
                    "operation": "aggregate_sum",
                    "group_by": [],
                    "metrics": ["WIP"],
                    "output_columns": ["OPER_GROUP", "WIP"],
                },
                {"step_id": "join_wb", "operation": "left_join", "output_columns": ["OPER_GROUP", "PRODUCTION", "WIP"]},
                {"step_id": "final_union", "operation": "concat", "output_columns": ["OPER_GROUP", "PRODUCTION", "WIP"]},
            ],
        },
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "da = pd.DataFrame([{'OPER_GROUP': 'DA', 'PRODUCTION': 10, 'WIP': 3}])",
                "wb = pd.DataFrame([{'OPER_GROUP': 'WB', 'PRODUCTION': 20, 'WIP': 4}])",
                "result_df = pd.concat([da, wb], ignore_index=True)",
            ]
        ),
        "output_columns": ["OPER_GROUP", "PRODUCTION", "WIP"],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["columns"] == ["OPER_GROUP", "PRODUCTION", "WIP"]
    assert result["analysis"]["rows"] == [
        {"OPER_GROUP": "DA", "PRODUCTION": 10, "WIP": 3},
        {"OPER_GROUP": "WB", "PRODUCTION": 20, "WIP": 4},
    ]


def test_pandas_executor_collapses_duplicate_group_metric_rows() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "generic_aggregate_recipe",
            "analysis_output_columns": ["OPER_NUM", "WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
            "step_plan": [
                {
                    "step_id": "aggregate_metric_outputs",
                    "operation": "aggregate_sum_by_group",
                    "source_alias": "production_today",
                    "group_by": ["OPER_NUM"],
                    "metrics": ["WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
                    "aggregation": "sum",
                    "output_columns": ["OPER_NUM", "WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
                }
            ],
        },
        "state": {},
        "runtime_sources": {},
    }
    pandas_llm_json = {
        "code": "\n".join(
            [
                "result_df = pd.DataFrame([",
                "    {'OPER_NUM': 'WB01', 'WAFER_OUT_QTY': 1.0, 'FAIL_UNIT_QTY': 2.0},",
                "    {'OPER_NUM': 'WB01', 'WAFER_OUT_QTY': 3.0, 'FAIL_UNIT_QTY': 4.0},",
                "    {'OPER_NUM': 'WB02', 'WAFER_OUT_QTY': 5.0, 'FAIL_UNIT_QTY': 6.0},",
                "])",
            ]
        ),
        "output_columns": ["OPER_NUM", "WAFER_OUT_QTY", "FAIL_UNIT_QTY"],
        "reasoning_steps": [],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["rows"] == [
        {"OPER_NUM": "WB01", "WAFER_OUT_QTY": 4.0, "FAIL_UNIT_QTY": 6.0},
        {"OPER_NUM": "WB02", "WAFER_OUT_QTY": 5.0, "FAIL_UNIT_QTY": 6.0},
    ]


def test_pandas_prompt_tells_llm_to_apply_retrieval_filters_in_pandas() -> None:
    prompt_builder = load_component("langflow_components/data_analysis_flow/14_pandas_prompt_builder.py")
    payload = {
        "request": {"question": "현재 WB공정에서 WIP가 가장 많은 제품 TOP 5 보여줘"},
        "intent_plan": {
            "analysis_kind": "rank_top_n",
            "product_grain": ["MODE"],
            "retrieval_jobs": [
                {
                    "dataset_key": "wip_today",
                    "source_alias": "wip_data",
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]}],
                }
            ],
            "step_plan": [{"operation": "rank_top_n", "source_alias": "wip_data", "metric": "WIP", "group_by": ["MODE"]}],
        },
        "runtime_sources": {
            "wip_data": [
                {"OPER_NAME": "W/B1", "MODE": "WB_PRODUCT", "WIP": 10},
                {"OPER_NAME": "D/A1", "MODE": "DA_PRODUCT", "WIP": 999},
            ]
        },
        "state": {},
    }

    result = prompt_builder.build_pandas_prompt_payload(payload)

    assert "Source retrieval은 DATE 또는 LOT_ID 같은 required source parameter만 적용" in result["prompt"]
    assert "분석 전에 pandas에서 적용할 source filter" in result["prompt"]
    assert "W/B1" in result["prompt"]
    assert result["source_filters"] == {"wip_data": [{"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]}]}


def test_pandas_executor_replaces_unfiltered_rank_result_with_filtered_step_fallback() -> None:
    pandas_executor = load_component("langflow_components/data_analysis_flow/15_pandas_code_executor.py")
    payload = {
        "intent_plan": {
            "analysis_kind": "rank_top_n",
            "product_grain": ["MODE"],
            "analysis_output_columns": ["MODE", "WIP"],
            "retrieval_jobs": [
                {
                    "dataset_key": "wip_today",
                    "source_alias": "wip_data",
                    "filters": [{"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]}],
                    "required_columns": ["OPER_NAME", "MODE", "WIP"],
                }
            ],
            "step_plan": [
                {
                    "step_id": "rank_wb_wip",
                    "operation": "rank_top_n",
                    "source_alias": "wip_data",
                    "metric": "WIP",
                    "group_by": ["MODE"],
                    "top_n": 1,
                    "rank_order": "desc",
                    "output_columns": ["MODE", "WIP"],
                }
            ],
        },
        "state": {},
        "runtime_sources": {
            "wip_data": [
                {"OPER_NAME": "W/B1", "MODE": "WB_PRODUCT", "WIP": 10},
                {"OPER_NAME": "D/A1", "MODE": "DA_PRODUCT", "WIP": 999},
            ]
        },
    }
    unfiltered_llm_json = {
        "code": "result_df = sources['wip_data'].groupby(['MODE'], as_index=False)['WIP'].sum().sort_values('WIP', ascending=False).head(1)",
        "output_columns": ["MODE", "WIP"],
        "reasoning_steps": ["Rank WIP by product."],
    }

    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(unfiltered_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"] == [{"MODE": "WB_PRODUCT", "WIP": 10}]
    assert "pandas-applied source filters" in result["analysis"]["analysis_code"]
