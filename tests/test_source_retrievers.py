from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

from reference_runtime.metadata import load_metadata
from reference_runtime.source_retrievers import retrieve_rows_for_job


ROOT = Path(__file__).resolve().parents[1]


def test_table_catalog_uses_real_source_type_boundaries():
    catalog = json.loads((ROOT / "metadata" / "table_catalog.json").read_text(encoding="utf-8"))["datasets"]
    source_types = {item["source_type"] for item in catalog.values()}

    assert "sample_json" not in source_types
    assert {"oracle", "goodocs"}.issubset(source_types)


def test_reference_retriever_uses_source_type_with_dummy_fallback():
    metadata = load_metadata(ROOT)
    catalog = metadata["table_catalog"]["datasets"]
    expected = {
        "production_today": ("oracle", 100),
        "wip_today": ("oracle", 100),
        "lot_status": ("oracle", 100),
        "hold_history": ("oracle", 2),
        "target": ("goodocs", 10),
        "capacity": ("oracle", 20),
    }

    for dataset_key, (source_type, minimum_rows) in expected.items():
        result = retrieve_rows_for_job(
            {
                "job_id": f"test_{dataset_key}",
                "dataset_key": dataset_key,
                "source_alias": dataset_key,
                "params": {"DATE": "20260612", "LOT_ID": "T1234567GEN1"},
            },
            catalog[dataset_key],
        )

        assert result["source_type"] == source_type
        assert result["used_dummy_data"] is True
        assert len(result["rows"]) >= minimum_rows
        assert result["source_execution"]["fallback_reason"]


def test_langflow_dummy_retriever_covers_all_current_datasets():
    module = _load_component("09_dummy_data_retriever.py")
    dataset_keys = [
        "production_today",
        "production",
        "wip_today",
        "wip",
        "target",
        "lot_status",
        "hold_history",
        "equipment_status",
        "capacity",
    ]
    payload = module.retrieve_dummy_data(
        {
            "intent_plan": {
                "route": "multi_retrieval",
                "retrieval_jobs": [
                    {"dataset_key": key, "source_alias": key, "params": {"DATE": "20260612", "LOT_ID": "T1234567GEN1"}}
                    for key in dataset_keys
                ],
            },
            "state": {},
        }
    )

    assert set(payload["retrieval_payload"]) == {"source_type", "source_results"}
    results = payload["retrieval_payload"]["source_results"]
    assert [item["dataset_key"] for item in results] == dataset_keys
    assert min(item["row_count"] for item in results if item["dataset_key"] != "hold_history") >= 8
    assert next(item for item in results if item["dataset_key"] == "lot_status")["row_count"] > 100


def test_table_catalog_and_dummy_data_cover_authoring_example_columns():
    catalog = json.loads((ROOT / "metadata" / "table_catalog.json").read_text(encoding="utf-8"))["datasets"]
    module = _load_component("09_dummy_data_retriever.py")
    expected = _authoring_example_dataset_specs()

    assert set(catalog) == set(expected)

    for dataset_key, spec in expected.items():
        item = catalog[dataset_key]
        assert item["display_name"] == spec["display_name"]
        assert item.get("required_params", []) == spec["required_params"]
        assert set(spec["columns"]).issubset(item.get("columns", []))

        for standard_name, physical_columns in spec["filter_columns"].items():
            mapped_columns = set(item.get("filter_mappings", {}).get(standard_name, []))
            assert set(physical_columns).issubset(mapped_columns)

        params = {"DATE": "20260612", "LOT_ID": "T1234567GEN1"}
        if dataset_key == "target":
            params["DATE"] = "2026-06-12"
        payload = module.retrieve_dummy_data(
            {
                "intent_plan": {
                    "route": "single_retrieval",
                    "retrieval_jobs": [{"dataset_key": dataset_key, "source_alias": dataset_key, "params": params}],
                },
                "state": {},
            }
        )
        source_result = payload["retrieval_payload"]["source_results"][0]

        assert source_result["row_count"] > 0
        assert set(spec["columns"]).issubset(source_result["columns"])

    assert {"INPUT 계획", "OUT 계획"}.issubset(catalog["target"]["columns"])


def test_langflow_dummy_retriever_preserves_job_filters_for_pandas_stage():
    module = _load_component("09_dummy_data_retriever.py")
    payload = module.retrieve_dummy_data(
        {
            "intent_plan": {
                "route": "single_retrieval",
                "retrieval_jobs": [
                    {
                        "dataset_key": "lot_status",
                        "source_alias": "lot_status_data",
                        "params": {"DATE": "20260612"},
                        "filters": [{"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2"]}],
                        "required_columns": ["OPER_SHORT_DESC", "LOT_ID", "IN_TAT"],
                    }
                ],
            },
            "state": {},
        }
    )

    source_result = payload["retrieval_payload"]["source_results"][0]
    processes = {row["OPER_SHORT_DESC"] for row in source_result["data"]}

    assert {"D/A1", "D/A2"}.issubset(processes)
    assert len(processes) > 2
    assert source_result["row_count"] > 0
    assert source_result["applied_filters"][0]["field"] == "OPER_NAME"
    assert source_result["source_execution"]["filters_applied_in_retriever"] is False
    assert source_result["source_execution"]["filter_execution_stage"] == "pandas"


def test_langflow_dummy_retriever_is_rich_enough_for_analysis_validation():
    module = _load_component("09_dummy_data_retriever.py")
    dataset_keys = [
        "production_today",
        "production",
        "wip_today",
        "wip",
        "target",
        "lot_status",
        "equipment_status",
        "capacity",
    ]
    payload = module.retrieve_dummy_data(
        {
            "intent_plan": {
                "route": "multi_retrieval",
                "retrieval_jobs": [
                    {"dataset_key": key, "source_alias": key, "params": {"DATE": "20260612", "LOT_ID": "T1234567GEN1"}}
                    for key in dataset_keys
                ],
            },
            "state": {},
        }
    )

    results = {item["dataset_key"]: item for item in payload["retrieval_payload"]["source_results"]}

    assert results["production_today"]["row_count"] >= 400
    assert results["wip_today"]["row_count"] >= 400
    assert results["lot_status"]["row_count"] >= 400
    assert results["capacity"]["row_count"] >= 300
    assert results["equipment_status"]["row_count"] >= 60
    assert results["target"]["row_count"] >= 16
    assert {"MODE", "DEN", "TECH", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO", "PRODUCTION"}.issubset(
        results["production_today"]["columns"]
    )
    production_rows = results["production_today"]["data"]
    wip_rows = results["wip_today"]["data"]
    assert {row["SHIFT"] for row in production_rows} == {"1", "2", "3"}
    assert {row["SHIFT"] for row in wip_rows} == {"1", "2", "3"}
    da_processes = {"D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"}
    assert sum(
        row["PRODUCTION"] for row in production_rows if row["OPER_NAME"] in da_processes and row["SHIFT"] == "1"
    ) > 0
    assert sum(row["WIP"] for row in wip_rows if row["OPER_NAME"] in da_processes and row["SHIFT"] == "1") > 0
    assert {"Mode", "PKG1", "PKG2", "MCP NO", "INPUT 계획", "OUT 계획"}.issubset(results["target"]["columns"])
    assert results["production_today"]["source_execution"]["params_applied_in_retriever"] is True


def test_langflow_dummy_retriever_applies_params_but_leaves_job_filters_for_pandas():
    module = _load_component("09_dummy_data_retriever.py")
    payload = module.retrieve_dummy_data(
        {
            "intent_plan": {
                "route": "multi_retrieval",
                "retrieval_jobs": [
                    {
                        "dataset_key": "production_today",
                        "source_alias": "production_data",
                        "params": {"DATE": "20260612"},
                        "filters": [
                            {"field": "OPER_NAME", "op": "in", "values": ["D/A1", "D/A2"]},
                            {"field": "MODE", "op": "eq", "value": "LPDDR5"},
                        ],
                    },
                    {
                        "dataset_key": "target",
                        "source_alias": "target_data",
                        "params": {"DATE": "20260612"},
                        "filters": [
                            {"field": "DATE", "op": "eq", "value": "2026-06-12"},
                            {"field": "PKG_TYPE1", "op": "eq", "value": "HBM"},
                        ],
                    },
                ],
            },
            "state": {},
        }
    )

    production, target = payload["retrieval_payload"]["source_results"]

    assert production["row_count"] > 0
    assert {"D/A1", "D/A2"}.issubset({row["OPER_NAME"] for row in production["data"]})
    assert len({row["OPER_NAME"] for row in production["data"]}) > 2
    assert "LPDDR5" in {row["MODE"] for row in production["data"]}
    assert len({row["MODE"] for row in production["data"]}) > 1
    assert target["row_count"] > 0
    assert {row["DATE"] for row in target["data"]} == {"2026-06-12"}
    assert "HBM" in {row["PKG_TYPE1"] for row in target["data"]}
    assert len({row["PKG_TYPE1"] for row in target["data"]}) > 1


def test_langflow_dummy_retriever_projects_required_columns_through_aliases():
    module = _load_component("09_dummy_data_retriever.py")
    payload = module.retrieve_dummy_data(
        {
            "intent_plan": {
                "route": "single_retrieval",
                "retrieval_jobs": [
                    {
                        "dataset_key": "lot_status",
                        "source_alias": "lot_status",
                        "params": {"DATE": "20260612"},
                        "filters": [{"field": "OPER_NAME", "op": "eq", "value": "D/A1"}],
                        "required_columns": ["OPER_NAME", "LOT_ID", "IN_TAT"],
                    }
                ],
            },
            "state": {},
        }
    )

    source_result = payload["retrieval_payload"]["source_results"][0]

    assert source_result["row_count"] > 0
    assert source_result["columns"] == ["OPER_NAME", "LOT_ID", "IN_TAT"]
    assert "D/A1" in {row["OPER_NAME"] for row in source_result["data"]}
    assert len({row["OPER_NAME"] for row in source_result["data"]}) > 1


def test_langflow_source_retrievers_and_merger_preserve_source_types():
    plan = {
        "intent_plan": {
            "route": "multi_retrieval",
            "retrieval_jobs": [
                {
                    "dataset_key": "production_today",
                    "source_alias": "production_today",
                    "source_type": "oracle",
                    "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": "SELECT * FROM T WHERE WORK_DT = {DATE}"},
                    "params": {"DATE": "20260612"},
                },
                {
                    "dataset_key": "hold_history",
                    "source_alias": "hold_history",
                    "source_type": "h_api",
                    "source_config": {"source_type": "h_api", "api_url": "https://h-api.example.invalid", "response_path": "data.rows"},
                    "required_params": ["LOT_ID"],
                    "params": {"LOT_ID": "T1234567GEN1"},
                },
                {
                    "dataset_key": "capacity",
                    "source_alias": "capacity",
                    "source_type": "datalake",
                    "source_config": {"source_type": "datalake", "query_template": "SELECT * FROM T WHERE BASE_DT = {DATE}"},
                    "params": {"DATE": "20260612"},
                },
                {
                    "dataset_key": "target",
                    "source_alias": "target",
                    "source_type": "goodocs",
                    "source_config": {"source_type": "goodocs", "doc_id": "DOC", "sheet_name": "daily_target"},
                    "params": {"DATE": "2026-06-12"},
                    "filters": [{"field": "DATE", "op": "eq", "value": "2026-06-12"}],
                },
            ],
        },
        "state": {},
    }

    oracle = _load_component("10_oracle_query_retriever.py").retrieve_oracle_data(plan)
    h_api = _load_component("11_h_api_retriever.py").retrieve_h_api_data(plan)
    datalake = _load_component("12_datalake_retriever.py").retrieve_datalake_data(plan)
    goodocs = _load_component("13_goodocs_retriever.py").retrieve_goodocs_data(plan)
    assert set(oracle["retrieval_payload"]) == {"source_type", "source_results"}
    assert set(h_api["retrieval_payload"]) == {"source_type", "source_results"}
    assert set(datalake["retrieval_payload"]) == {"source_type", "source_results"}
    assert set(goodocs["retrieval_payload"]) == {"source_type", "source_results"}
    merged = _load_component("14_source_retrieval_merger.py").merge_source_retrieval_payloads(oracle, h_api, datalake, goodocs)

    assert set(merged["retrieval_payload"]) == {"source_results"}
    source_types = [item["source_type"] for item in merged["retrieval_payload"]["source_results"]]
    assert source_types == ["oracle", "h_api", "datalake", "goodocs"]


def test_langflow_oracle_retriever_executes_sql_when_configured():
    module = _load_component("10_oracle_query_retriever.py")

    class FakeCursor:
        description = [("WORK_DT",), ("PRODUCTION",)]

        def __init__(self) -> None:
            self.executed_sql = ""

        def execute(self, sql: str) -> None:
            self.executed_sql = sql

        def fetchmany(self, _limit: int):
            return [("20260612", 1234)]

        def close(self) -> None:
            pass

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self) -> None:
            pass

    class FakeOracleModule:
        def __init__(self) -> None:
            self.connection = FakeConnection()
            self.connect_kwargs = {}

        def connect(self, **kwargs):
            self.connect_kwargs = kwargs
            return self.connection

    fake_oracle = FakeOracleModule()
    module.OracleQueryRetriever.oracledb = fake_oracle
    plan = _source_plan(
        {
            "dataset_key": "production_today",
            "source_alias": "prod",
            "source_type": "oracle",
            "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": "SELECT WORK_DT, PRODUCTION FROM T WHERE WORK_DT = {DATE}"},
            "required_params": ["DATE"],
            "params": {"DATE": "20260612"},
        }
    )

    result = module.retrieve_oracle_data(plan, json.dumps({"PNT_RPT": {"user": "u", "password": "p", "dsn": "dsn"}}))
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["data"] == [{"WORK_DT": "20260612", "PRODUCTION": 1234}]
    assert source_result["executed_query"] == "SELECT WORK_DT, PRODUCTION FROM T WHERE WORK_DT = '20260612'"
    assert fake_oracle.connect_kwargs == {"user": "u", "password": "p", "dsn": "dsn"}


def test_langflow_oracle_retriever_leaves_job_filters_for_pandas_stage():
    module = _load_component("10_oracle_query_retriever.py")

    class FakeCursor:
        description = [("WORK_DT",), ("OPER_NAME",), ("WIP",)]

        def __init__(self) -> None:
            self.executed_sql = ""

        def execute(self, sql: str) -> None:
            self.executed_sql = sql

        def fetchmany(self, _limit: int):
            return [("20260620", "W/B1", 1234)]

        def close(self) -> None:
            pass

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self) -> None:
            pass

    class FakeOracleModule:
        def __init__(self) -> None:
            self.connection = FakeConnection()

        def connect(self, **_kwargs):
            return self.connection

    fake_oracle = FakeOracleModule()
    module.OracleQueryRetriever.oracledb = fake_oracle
    plan = _source_plan(
        {
            "dataset_key": "wip_today",
            "source_alias": "wip_data",
            "source_type": "oracle",
            "source_config": {
                "source_type": "oracle",
                "db_key": "PNT_RPT",
                "query_template": "SELECT WORK_DT, OPER_NAME, WIP FROM WIP_TODAY WHERE 1=1 AND WORK_DT = {DATE}",
            },
            "required_params": ["DATE"],
            "params": {"DATE": "20260620"},
            "filters": [
                {"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]},
                {"field": "DATE", "op": "eq", "value": "20260620"},
            ],
        }
    )

    result = module.retrieve_oracle_data(plan, json.dumps({"PNT_RPT": {"user": "u", "password": "p", "dsn": "dsn"}}))
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["executed_query"] == (
        "SELECT WORK_DT, OPER_NAME, WIP FROM WIP_TODAY WHERE 1=1 AND WORK_DT = '20260620'"
    )
    assert source_result["applied_filters"] == [
        {"field": "OPER_NAME", "op": "in", "values": ["W/B1", "W/B2"]},
        {"field": "DATE", "op": "eq", "value": "20260620"},
    ]


def test_langflow_h_api_retriever_posts_bind_params_when_token_is_present(monkeypatch):
    module = _load_component("11_h_api_retriever.py")
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {"data": {"rows": [{"LOT_ID": "T1234567GEN1", "HOLD_CD": "QA_HOLD"}]}}

    def fake_post(url, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(post=fake_post))
    plan = _source_plan(
        {
            "dataset_key": "hold_history",
            "source_alias": "hold_history",
            "source_type": "h_api",
            "source_config": {"source_type": "h_api", "api_url": "https://h-api.example.invalid/hold", "response_path": "data.rows"},
            "required_params": ["LOT_ID"],
            "params": {"LOT_ID": "T1234567GEN1"},
        }
    )

    result = module.retrieve_h_api_data(plan, api_token="token")
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["data"][0]["HOLD_CD"] == "QA_HOLD"
    assert captured["json"] == {"bindParams": ["T1234567GEN1"]}


def test_langflow_datalake_retriever_uses_lakehouse_execution(monkeypatch):
    module = _load_component("12_datalake_retriever.py")
    calls = {}

    class FakeLakeHouse:
        def __init__(self, real_user_id: str) -> None:
            calls["real_user_id"] = real_user_id

        def ensure_running(self, cluster_type: str) -> None:
            calls["cluster_type"] = cluster_type

        def auto_run_sync_paragraph(self, code: str) -> None:
            calls["code"] = code

        def get_rst(self):
            return [{"BASE_DT": "20260612", "AVG_UPH_VAL": 777}]

    module.DatalakeRetriever.lakes = types.SimpleNamespace(LakeHouse=FakeLakeHouse)
    plan = _source_plan(
        {
            "dataset_key": "capacity",
            "source_alias": "capacity",
            "source_type": "datalake",
            "source_config": {"source_type": "datalake", "query_template": "SELECT BASE_DT, AVG_UPH_VAL FROM T WHERE BASE_DT = {DATE}"},
            "params": {"DATE": "20260612"},
        }
    )

    result = module.retrieve_datalake_data(plan, "lake-user", "lake-token", "access", "secret")
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["data"] == [{"BASE_DT": "20260612", "AVG_UPH_VAL": 777}]
    assert calls["code"] == "SELECT BASE_DT, AVG_UPH_VAL FROM T WHERE BASE_DT = '20260612'"
    assert os.environ["LAKEHOUSE_USER_ID"] == "lake-user"
    assert os.environ["LAKEHOUSE_S3_ACCESS_KEY"] == "access"


def test_langflow_goodocs_retriever_reads_document_and_preserves_filters_for_pandas():
    module = _load_component("13_goodocs_retriever.py")
    captured = {}

    class FakeGoodocs:
        def __init__(self, auth: dict):
            captured["auth"] = auth

        def read_all(self):
            return [
                {"DATE": "2026-06-12", "MODE": "LPDDR5", "OUT_PLAN": 100, "ROW_ID": "drop"},
                {"DATE": "2026-06-13", "MODE": "LPDDR5", "OUT_PLAN": 200},
            ]

    module.GoodocsRetriever.goodocs_class = FakeGoodocs
    plan = _source_plan(
        {
            "dataset_key": "target",
            "source_alias": "target",
            "source_type": "goodocs",
            "source_config": {"source_type": "goodocs", "doc_id": "DOC", "sheet_name": "daily_target"},
            "params": {"DATE": "2026-06-12"},
            "filters": [{"field": "DATE", "op": "eq", "value": "2026-06-12"}],
        }
    )

    result = module.retrieve_goodocs_data(plan, "user", "source", "key")
    source_result = result["retrieval_payload"]["source_results"][0]

    assert source_result["success"] is True
    assert source_result["used_dummy_data"] is False
    assert source_result["data"] == [
        {"DATE": "2026-06-12", "MODE": "LPDDR5", "OUT_PLAN": 100},
        {"DATE": "2026-06-13", "MODE": "LPDDR5", "OUT_PLAN": 200},
    ]
    assert source_result["applied_filters"] == [{"field": "DATE", "op": "eq", "value": "2026-06-12"}]
    assert captured["auth"]["DOC_ID"] == "DOC"
    assert captured["auth"]["SHEET_NAME"] == "daily_target"


def test_goodocs_spaced_plan_quantity_columns_retrieve_and_execute_in_pandas():
    goodocs_module = _load_component("13_goodocs_retriever.py")
    retrieval_adapter = _load_main_component("15_retrieval_payload_adapter.py")
    pandas_executor = _load_component("15_pandas_code_executor.py")

    class FakeGoodocs:
        def __init__(self, auth: dict):
            self.auth = auth

        def read_all(self):
            return [
                {"DATE": "2026-06-26", "Mode": "LPDDR5", "DEN": "512G", "INPUT 계획": 100, "OUT 계획": 80},
                {"DATE": "2026-06-26", "Mode": "LPDDR5", "DEN": "512G", "INPUT 계획": 200, "OUT 계획": 120},
                {"DATE": "2026-06-27", "Mode": "LPDDR5", "DEN": "512G", "INPUT 계획": 999, "OUT 계획": 999},
            ]

    previous_goodocs_class = goodocs_module.GoodocsRetriever.goodocs_class
    goodocs_module.GoodocsRetriever.goodocs_class = FakeGoodocs
    job = {
        "dataset_key": "target",
        "source_alias": "target_data",
        "source_type": "goodocs",
        "source_config": {"source_type": "goodocs", "doc_id": "1231231412412512515"},
        "params": {},
        "filters": [{"field": "DATE", "op": "eq", "value": "2026-06-26"}],
        "required_columns": ["DATE", "INPUT 계획", "OUT 계획"],
        "primary_quantity_column": ["INPUT 계획", "OUT 계획"],
    }
    main_payload = {
        "request": {"session_id": "test", "question": "2026-06-26 생산계획 보여줘"},
        "state": {},
        "intent_plan": {
            "analysis_kind": "aggregate_total",
            "metric": "OUT_PLAN",
            "retrieval_jobs": [job],
            "step_plan": [
                {
                    "step_id": "sum_plan",
                    "operation": "aggregate_sum",
                    "source_alias": "target_data",
                    "metrics": ["INPUT 계획", "OUT 계획"],
                }
            ],
        },
    }

    try:
        retrieval_payload = goodocs_module.retrieve_goodocs_data(main_payload, "user", "source", "key")
    finally:
        goodocs_module.GoodocsRetriever.goodocs_class = previous_goodocs_class

    source_result = retrieval_payload["retrieval_payload"]["source_results"][0]
    assert source_result["success"] is True
    assert {"INPUT 계획", "OUT 계획"}.issubset(source_result["columns"])

    payload = retrieval_adapter.adapt_retrieval_payload(main_payload, retrieval_payload)
    assert {"INPUT 계획", "OUT 계획"}.issubset(payload["source_results"][0]["columns"])

    pandas_llm_json = {
        "code": "\n".join(
            [
                "target_df = sources['target_data']",
                "target_df = target_df[target_df['DATE'] == '2026-06-26']",
                "result_df = pd.DataFrame([{'INPUT_PLAN': target_df['INPUT 계획'].sum(), 'OUT_PLAN': target_df['OUT 계획'].sum()}])",
            ]
        ),
        "output_columns": ["INPUT_PLAN", "OUT_PLAN"],
        "reasoning_steps": [],
    }
    result = pandas_executor.execute_pandas_from_llm(payload, json.dumps(pandas_llm_json, ensure_ascii=False))

    assert result["analysis"]["status"] == "ok"
    assert result["analysis"]["rows"] == [{"INPUT_PLAN": 300, "OUT_PLAN": 200}]


def test_retrieval_payload_adapter_builds_compact_main_payload():
    main_payload = {
        "request": {"session_id": "test", "question": "q"},
        "state": {},
        "intent_plan": {
            "analysis_kind": "detail_rows",
            "retrieval_jobs": [{"dataset_key": "hold_history", "source_alias": "hold_history", "source_type": "h_api"}],
            "step_plan": [{"source_alias": "hold_history", "columns": ["LOT_ID", "HOLD_CD"]}],
        },
    }
    retrieval_payload = {
        "retrieval_payload": {
            "source_results": [
                {
                    "success": True,
                    "dataset_key": "hold_history",
                    "source_alias": "hold_history",
                    "source_type": "h_api",
                    "data": [{"LOT_ID": "T1234567GEN1", "HOLD_CD": "QA_HOLD"}],
                }
            ]
        }
    }

    adapter = _load_main_component("15_retrieval_payload_adapter.py")
    payload = adapter.adapt_retrieval_payload(main_payload, retrieval_payload)

    assert payload["runtime_sources"]["hold_history"][0]["LOT_ID"] == "T1234567GEN1"
    assert "data" not in payload["source_results"][0]
    assert payload["source_results"][0]["preview_rows"][0]["HOLD_CD"] == "QA_HOLD"


def test_retrieval_payload_adapter_preserves_full_restored_sources_without_new_retrieval():
    restored_rows = [
        {"DEVICE": "D1", "PRODUCTION": 10},
        {"DEVICE": "D2", "PRODUCTION": 20},
        {"DEVICE": "D3", "PRODUCTION": 30},
    ]
    main_payload = {
        "request": {"session_id": "test", "question": "이때 상세 device별로 알려줘"},
        "intent_plan": {"intent_type": "followup_transform", "requires_full_previous_result_restore": True},
        "runtime_sources": {"production_data": restored_rows},
        "runtime_sources_are_preview": False,
        "state": {
            "followup_source_results": [
                {
                    "source_alias": "production_data",
                    "dataset_key": "production_today",
                    "source_type": "oracle",
                    "data_ref": {
                        "store": "mongodb",
                        "ref_id": "source-ref",
                        "collection_name": "agent_v3_result_store",
                    },
                    "row_count": 3,
                    "columns": ["DEVICE", "PRODUCTION"],
                }
            ]
        },
    }
    retrieval_payload = {"retrieval_payload": {"source_results": []}}

    for adapter_path in [
        "langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py",
        "langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py",
    ]:
        adapter = _load_flow_component(adapter_path)
        payload = adapter.adapt_retrieval_payload(main_payload, retrieval_payload)

        assert payload["runtime_sources"]["production_data"] == restored_rows
        assert payload["source_results"][0]["data_ref"]["ref_id"] == "source-ref"
        assert payload["source_results"][0]["reused_from_previous_source"] is True
        assert payload["reused_previous_runtime_sources"] is True
        assert "이전 조회 원본을 새 조회 없이 재사용했습니다." in payload["info"]


def test_retrieval_payload_adapter_does_not_reuse_preview_sources_without_full_restore():
    main_payload = {
        "request": {"session_id": "test", "question": "상세 device별로 알려줘"},
        "intent_plan": {"intent_type": "single_retrieval_analysis"},
        "runtime_sources": {"production_data": [{"DEVICE": "D1", "PRODUCTION": 10}]},
        "runtime_sources_are_preview": True,
        "state": {},
    }
    retrieval_payload = {"retrieval_payload": {"source_results": []}}

    for adapter_path in [
        "langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py",
        "langflow_components/data_analysis_flow/13_retrieval_payload_adapter.py",
    ]:
        adapter = _load_flow_component(adapter_path)
        payload = adapter.adapt_retrieval_payload(main_payload, retrieval_payload)

        assert payload["runtime_sources"] == {}
        assert payload["source_results"] == []
        assert "reused_previous_runtime_sources" not in payload


def _source_plan(job: dict) -> dict:
    return {"intent_plan": {"route": "single_retrieval", "retrieval_jobs": [job]}, "state": {}}


def _authoring_example_dataset_specs() -> dict[str, dict]:
    def product_filters(den_col: str, pkg1_col: str, pkg2_col: str) -> dict[str, list[str]]:
        return {
            "DATE": ["WORK_DATE"],
            "MODE": ["MODE"],
            "DEN": [den_col],
            "TECH": ["TECH"],
            "PKG_TYPE1": [pkg1_col],
            "PKG_TYPE2": [pkg2_col],
            "LEAD": ["LEAD"],
            "MCP_NO": ["MCP_NO"],
            "TSV_DIE_TYP": ["TSV_DIE_TYP"],
            "DEVICE": ["DEVICE"],
            "DEVICE_DESC": ["DEVICE_DESC"],
            "OPER_NUM": ["OPER"],
            "OPER_SEQ": ["OPER_SEQ"],
            "DIE_ATTACH_QTY": ["DIE_ATTACH_QTY"],
            "NETDIE_300_CNT": ["NETDIE_300_CNT"],
            "OPER_NAME": ["OPER_NAME"],
        }

    def product_columns(den_col: str, pkg1_col: str, pkg2_col: str) -> list[str]:
        return [
            "WORK_DATE",
            "SHIFT",
            "FACTORY",
            "FAB",
            "FAMILY",
            "MODE",
            den_col,
            "TECH",
            "ORG",
            pkg1_col,
            pkg2_col,
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
        ]
    lot_columns = [
        "ERM_ID",
        "OPER_ID",
        "OPER_SHORT_DESC",
        "FAB_ID",
        "OWNER_CD",
        "GRADE_CD",
        "PROD_ID",
        "LOT_ID",
        "SUB_LOT_ID",
        "SUB_PROD_QTY",
        "WF_QTY",
        "IN_TAT",
        "CUM_TAT",
        "EQP_ID",
        "FLOW_ID",
        "OPER_IN_TM",
        "CRT_TM",
        "FAC_IN_TM",
        "LOT_HOLD_STAT_CD",
        "REASON_CD",
        "FAMILY_CD",
        "PROD_TYP",
        "DEN_TYP",
        "TECH_NM",
        "ORGANIZ_CD",
        "PKG_TYP",
        "PKG_TYP_2",
        "PKG_TYP_3",
        "LEAD_CNT",
        "PROD_GRP_ID",
        "THK_CD",
        "LOT_STAT_CD",
        "LOT_GRP_CD",
        "PKG_SIZE_VAL",
        "PKG_DEN_TYP",
        "HOT_LOT_YN",
        "HOT_LEVEL_TYP",
        "PKG_COMPOSIT_TYP",
        "DURABLE_ID",
        "DURABLE_TYP",
        "SUB_QTY",
        "TSV_DIE_TYP",
        "EVENT_DESC",
        "PLANNING_DESC",
        "MOVE_IN_TM",
        "PAD_ABNORM_YN",
        "SWR_REQ_NO",
        "OPER_GRP_VAL_1",
        "INSP_TGT_YN",
    ]
    return {
        "production_today": {
            "display_name": "Production Today",
            "required_params": ["DATE"],
            "columns": product_columns("DEN", "PKG_TYP1", "PKG_TYP2") + ["PRODUCTION"],
            "filter_columns": product_filters("DEN", "PKG_TYP1", "PKG_TYP2"),
        },
        "production": {
            "display_name": "Production History",
            "required_params": ["DATE"],
            "columns": product_columns("DENSITY", "PKG1", "PKG2") + ["PRODUCTION"],
            "filter_columns": product_filters("DENSITY", "PKG1", "PKG2"),
        },
        "wip_today": {
            "display_name": "WIP Today",
            "required_params": ["DATE"],
            "columns": product_columns("DENSITY", "PKG1", "PKG2") + ["WIP"],
            "filter_columns": product_filters("DENSITY", "PKG1", "PKG2"),
        },
        "wip": {
            "display_name": "WIP History",
            "required_params": ["DATE"],
            "columns": product_columns("DENSITY", "PKG_TYP1", "PKG_TYP2") + ["WIP"],
            "filter_columns": product_filters("DENSITY", "PKG_TYP1", "PKG_TYP2"),
        },
        "target": {
            "display_name": "Target2 Goodocs Plan",
            "required_params": [],
            "columns": ["DATE", "Mode", "DEN", "TECH", "PKG1", "PKG2", "LEAD", "ORG", "MCP NO", "INPUT 계획", "OUT 계획"],
            "filter_columns": {
                "DATE": ["DATE"],
                "MODE": ["Mode"],
                "DEN": ["DEN"],
                "TECH": ["TECH"],
                "PKG_TYPE1": ["PKG1"],
                "PKG_TYPE2": ["PKG2"],
                "LEAD": ["LEAD"],
                "MCP_NO": ["MCP NO"],
            },
        },
        "lot_status": {
            "display_name": "LOT Status",
            "required_params": [],
            "columns": lot_columns,
            "filter_columns": {
                "OPER_NAME": ["OPER_SHORT_DESC", "OPER_ID"],
                "MODE": ["PROD_TYP"],
                "DEN": ["DEN_TYP"],
                "TECH": ["TECH_NM"],
                "PKG_TYPE1": ["PKG_TYP"],
                "PKG_TYPE2": ["PKG_TYP_2"],
                "LEAD": ["LEAD_CNT"],
                "MCP_NO": ["PROD_GRP_ID"],
                "TSV_DIE_TYP": ["TSV_DIE_TYP"],
                "EQP_ID": ["EQP_ID"],
                "LOT_ID": ["LOT_ID"],
            },
        },
        "hold_history": {
            "display_name": "HOLD History",
            "required_params": ["LOT_ID"],
            "columns": [
                "FAB_ID",
                "DEN_TYP",
                "PROD_ID",
                "GRADE_CD",
                "OWNER_CD",
                "OPER_ID",
                "OPER_SHORT_DESC",
                "LOT_ID",
                "OLD_SUB_PROD_QTY",
                "HOLD_TM",
                "RELEASE_DUE_DATE",
                "HOLD_CD",
                "HOLD_USER_ID",
                "HOLD_DESC",
                "FAMILY_CD",
                "TECH_NM",
                "GEN_TYP",
                "ORGANIZ_CD",
                "PKG_TYP_2",
                "PKG_SIZE_VAL",
                "PROD_GRP_ID",
                "THK_CD",
                "MCP_SALE_CD",
                "HOLD_GRADE_CD",
                "FLOW_ID",
                "FAC_ID",
                "EVENT_CD",
            ],
            "filter_columns": {
                "LOT_ID": ["LOT_ID"],
                "OPER_NAME": ["OPER_SHORT_DESC", "OPER_ID"],
                "DEN": ["DEN_TYP"],
                "TECH": ["TECH_NM"],
                "PKG_TYPE2": ["PKG_TYP_2"],
                "MCP_NO": ["MCP_SALE_CD"],
            },
        },
        "equipment_status": {
            "display_name": "Equipment Status",
            "required_params": [],
            "columns": [
                "BAY_ID",
                "EQPID",
                "EQP_MODEL",
                "PRESS_CNT",
                "MODE",
                "DEN",
                "TECH",
                "PKG1",
                "PKG2",
                "LEAD",
                "ORG",
                "PKGSIZE",
                "MCPSALENO",
                "DEVICE",
                "DEVICE_DESC",
                "LOT_ID",
                "EQP_OPERATYN",
                "PI",
                "RECIPE_ID",
            ],
            "filter_columns": {
                "EQP_ID": ["EQPID"],
                "EQP_MODEL": ["EQP_MODEL"],
                "MODE": ["MODE"],
                "DEN": ["DEN"],
                "TECH": ["TECH"],
                "PKG_TYPE1": ["PKG1"],
                "PKG_TYPE2": ["PKG2"],
                "LEAD": ["LEAD"],
                "MCP_NO": ["MCPSALENO"],
                "DEVICE_DESC": ["DEVICE_DESC"],
                "LOT_ID": ["LOT_ID"],
                "RECIPE_ID": ["RECIPE_ID"],
            },
        },
        "capacity": {
            "display_name": "Equipment Recipe UPH",
            "required_params": [],
            "columns": [
                "FAC_ID",
                "EQP_OPER_GRP_CD",
                "EQP_OPER_DET_GRP_CD",
                "EQP_MODEL_CD",
                "OPER_ID",
                "OPER_DESC",
                "PRESS_CNT",
                "PROD_TYP",
                "TECH_NM",
                "DEN_TYP",
                "PKG_TYP",
                "PKG_TYP2",
                "LEAD_CNT",
                "MCP_SALE_CD",
                "RECIPE_ID",
                "AVG_UPH_VAL",
                "BASE_DT",
            ],
            "filter_columns": {
                "DATE": ["BASE_DT"],
                "EQP_MODEL": ["EQP_MODEL_CD"],
                "OPER_NAME": ["OPER_DESC"],
                "MODE": ["PROD_TYP"],
                "TECH": ["TECH_NM"],
                "DEN": ["DEN_TYP"],
                "PKG_TYPE1": ["PKG_TYP"],
                "PKG_TYPE2": ["PKG_TYP2"],
                "LEAD": ["LEAD_CNT"],
                "MCP_NO": ["MCP_SALE_CD"],
                "RECIPE_ID": ["RECIPE_ID"],
            },
        },
    }


def _load_component(filename: str):
    mapped_filename = {
        "09_dummy_data_retriever.py": "07_dummy_data_retriever.py",
        "10_oracle_query_retriever.py": "08_oracle_query_retriever.py",
        "11_h_api_retriever.py": "09_h_api_retriever.py",
        "12_datalake_retriever.py": "10_datalake_retriever.py",
        "13_goodocs_retriever.py": "11_goodocs_retriever.py",
        "14_source_retrieval_merger.py": "12_source_retrieval_merger.py",
    }.get(filename, filename)
    path = ROOT / "langflow_components" / "data_analysis_flow" / mapped_filename
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_main_component(filename: str):
    mapped_filename = {
        "15_retrieval_payload_adapter.py": "13_retrieval_payload_adapter.py",
    }.get(filename, filename)
    path = ROOT / "langflow_components" / "data_analysis_flow" / mapped_filename
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_flow_component(relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location("test_" + path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
