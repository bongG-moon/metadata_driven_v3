from __future__ import annotations

import importlib
import json
import os
import re
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .dummy_data import generate_dummy_rows


SUPPORTED_SOURCE_TYPES = {"oracle", "h_api", "datalake", "goodocs", "dummy"}


def retrieve_rows_for_job(job: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Return source rows using the catalog source_type."""

    source_type = _source_type(job, catalog)
    dataset_key = job["dataset_key"]
    params = deepcopy(job.get("params", {}))

    if source_type not in SUPPORTED_SOURCE_TYPES:
        return {"source_type": source_type, "rows": [], "used_dummy_data": False, "error": f"Unsupported source_type: {source_type}"}

    if source_type != "dummy" and _live_source_enabled():
        live_result = _retrieve_live_rows(source_type, job, catalog)
        if live_result.get("success"):
            return {
                "source_type": source_type,
                "rows": _limit_rows(live_result.get("rows", [])),
                "used_dummy_data": False,
                "source_execution": {**_execution_trace(source_type, job, catalog), **deepcopy(live_result.get("source_execution", {}))},
            }
        return _dummy_response(source_type, dataset_key, params, job, catalog, live_result.get("error", "live retrieval failed"))

    fallback_reason = "dummy source" if source_type == "dummy" else "RUN_LIVE_SOURCE_RETRIEVAL is false"
    return _dummy_response(source_type, dataset_key, params, job, catalog, fallback_reason)


def _dummy_response(
    source_type: str,
    dataset_key: str,
    params: dict[str, Any],
    job: dict[str, Any],
    catalog: dict[str, Any],
    fallback_reason: str,
) -> dict[str, Any]:
    rows = generate_dummy_rows(dataset_key, params)
    return {
        "source_type": source_type,
        "rows": rows,
        "used_dummy_data": True,
        "source_execution": {**_execution_trace(source_type, job, catalog), "fallback_reason": fallback_reason},
    }


def _source_type(job: dict[str, Any], catalog: dict[str, Any]) -> str:
    config = catalog.get("source_config") if isinstance(catalog.get("source_config"), dict) else {}
    return str(job.get("source_type") or catalog.get("source_type") or config.get("source_type") or "dummy").lower()


def _live_source_enabled() -> bool:
    return str(os.getenv("RUN_LIVE_SOURCE_RETRIEVAL", "")).strip().lower() in {"1", "true", "yes", "y", "on"}


def _retrieve_live_rows(source_type: str, job: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    try:
        if source_type == "oracle":
            return _retrieve_oracle_rows(job, catalog)
        if source_type == "h_api":
            return _retrieve_h_api_rows(job, catalog)
        if source_type == "datalake":
            return _retrieve_datalake_rows(job, catalog)
        if source_type == "goodocs":
            return _retrieve_goodocs_rows(job, catalog)
    except Exception as exc:
        return {"success": False, "rows": [], "error": f"{source_type} retrieval failed: {exc}"}
    return {"success": False, "rows": [], "error": f"No live retriever for {source_type}"}


def _retrieve_oracle_rows(job: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    config = _source_config(catalog)
    db_key = str(config.get("db_key") or "").strip()
    oracle_configs = _json_env("ORACLE_CONFIG_JSON")
    db_config = oracle_configs.get(db_key) if isinstance(oracle_configs, dict) else {}
    if not isinstance(db_config, dict) or not db_config:
        return {"success": False, "rows": [], "error": f"Missing Oracle config for db_key={db_key}"}

    query, missing = _render_template(str(config.get("query_template") or ""), deepcopy(job.get("params", {})))
    if missing:
        return {"success": False, "rows": [], "error": "Missing query param(s): " + ", ".join(missing)}
    if not query.strip():
        return {"success": False, "rows": [], "error": "Oracle query_template is empty"}

    driver = _import_first("oracledb", "cx_Oracle")
    if driver is None:
        return {"success": False, "rows": [], "error": "Install oracledb or cx_Oracle to run live Oracle retrieval"}

    connection = driver.connect(user=db_config.get("user"), password=db_config.get("password"), dsn=db_config.get("dsn") or db_config.get("tns"))
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        columns = [column[0] for column in cursor.description or []]
        rows = [dict(zip(columns, _json_ready(row))) for row in cursor.fetchmany(_fetch_limit())]
        return {"success": True, "rows": rows, "source_execution": {"query": query, "db_key": db_key}}
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _retrieve_h_api_rows(job: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("H_API_TOKEN", "").strip()
    if not token:
        return {"success": False, "rows": [], "error": "H_API_TOKEN is empty"}
    config = _source_config(catalog)
    api_url = str(config.get("api_url") or "").strip()
    if not api_url:
        return {"success": False, "rows": [], "error": "H-API api_url is empty"}

    requests = _import_first("requests")
    if requests is None:
        return {"success": False, "rows": [], "error": "Install requests to run live H-API retrieval"}

    params = deepcopy(job.get("params", {}))
    body = {"bindParams": [_param_value(params, key) for key in _param_order(job)], "params": params}
    response = requests.post(
        api_url,
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=float(config.get("timeout", 30)),
    )
    response.raise_for_status()
    rows = _rows_from_payload(response.json(), str(config.get("response_path") or ""))[: _fetch_limit()]
    return {"success": True, "rows": rows, "source_execution": {"api_url": api_url, "body": body}}


def _retrieve_datalake_rows(job: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    config = _source_config(catalog)
    query, missing = _render_template(str(config.get("query_template") or ""), deepcopy(job.get("params", {})))
    if missing:
        return {"success": False, "rows": [], "error": "Missing query param(s): " + ", ".join(missing)}

    module_name = os.getenv("DATALAKE_QUERY_MODULE", "").strip()
    if not module_name:
        return {
            "success": False,
            "rows": [],
            "error": "Set DATALAKE_QUERY_MODULE with run_query(query, fetch_limit) for live Datalake retrieval",
        }
    module = importlib.import_module(module_name)
    rows = module.run_query(query=query, fetch_limit=_fetch_limit())
    return {"success": True, "rows": _rows_from_frame(rows), "source_execution": {"query": query, "module": module_name}}


def _retrieve_goodocs_rows(job: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    config = _source_config(catalog)
    doc_id = str(config.get("doc_id") or "").strip()
    if not doc_id:
        return {"success": False, "rows": [], "error": "Goodocs doc_id is empty"}

    module_name = os.getenv("GOODOCS_MODULE_NAME", "").strip()
    if not module_name:
        return {"success": False, "rows": [], "error": "GOODOCS_MODULE_NAME is empty"}

    module = importlib.import_module(module_name)
    goodocs_cls = getattr(module, "Goodocs")
    auth = {
        "USER_ID": os.getenv("GOODOCS_USER_ID", ""),
        "DOC_ID": doc_id,
        "TOKEN_SOURCE": os.getenv("GOODOCS_TOKEN_SOURCE", ""),
        "TOKEN_KEY": os.getenv("GOODOCS_TOKEN_KEY", ""),
    }
    frame = goodocs_cls(auth).read_all()
    rows = _rows_from_frame(frame)[: _fetch_limit()]
    return {"success": True, "rows": rows, "source_execution": {"doc_id": doc_id, "module": module_name}}


def _execution_trace(source_type: str, job: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    config = catalog.get("source_config") if isinstance(catalog.get("source_config"), dict) else {}
    if source_type == "oracle":
        return {
            "db_key": config.get("db_key", ""),
            "query_template": config.get("query_template", ""),
            "params": deepcopy(job.get("params", {})),
        }
    if source_type == "h_api":
        return {
            "api_url": config.get("api_url", ""),
            "response_path": config.get("response_path", ""),
            "bind_params": deepcopy(job.get("params", {})),
        }
    if source_type == "datalake":
        return {
            "query_template": config.get("query_template", ""),
            "params": deepcopy(job.get("params", {})),
        }
    if source_type == "goodocs":
        return {
            "doc_id": config.get("doc_id", ""),
            "sheet_name": config.get("sheet_name", ""),
            "filters": deepcopy(job.get("filters", [])),
        }
    return {"dataset_key": job.get("dataset_key", "")}


def _source_config(catalog: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(catalog.get("source_config")) if isinstance(catalog.get("source_config"), dict) else {}


def _json_env(key: str) -> Any:
    value = os.getenv(key, "").strip()
    if not value:
        return {}
    return json.loads(value)


def _fetch_limit() -> int:
    try:
        return max(1, int(os.getenv("SOURCE_FETCH_LIMIT", "5000") or "5000"))
    except ValueError:
        return 5000


def _limit_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rows[: _fetch_limit()]


def _import_first(*module_names: str) -> Any:
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    return None


def _render_template(template: str, params: dict[str, Any]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = _param_value(params, key)
        if value in (None, "", []):
            missing.append(key)
            return match.group(0)
        return _sql_literal(value)

    return re.sub(r"\{([^{}]+)\}", replace, template), missing


def _param_order(job: dict[str, Any]) -> list[str]:
    order = job.get("param_order")
    if isinstance(order, list) and order:
        return [str(item) for item in order]
    required = job.get("required_params")
    if isinstance(required, list):
        return [str(item) for item in required]
    params = job.get("params")
    return list(params.keys()) if isinstance(params, dict) else []


def _param_value(params: dict[str, Any], key: str) -> Any:
    if key in params:
        return params[key]
    normalized = _normalize_key(key)
    for item_key, value in params.items():
        if _normalize_key(item_key) == normalized:
            return value
    return None


def _normalize_key(value: Any) -> str:
    return re.sub(r"[\s_-]+", "", str(value or "").strip().lower())


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (datetime, date)):
        return "'" + value.strftime("%Y%m%d") + "'"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _rows_from_payload(payload: Any, response_path: str = "") -> list[dict[str, Any]]:
    if response_path:
        for part in [item for item in response_path.split(".") if item]:
            payload = payload.get(part) if isinstance(payload, dict) else None
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data") or payload.get("rows") or payload.get("items") or payload.get("result") or []
        if isinstance(rows, dict):
            rows = [rows]
    else:
        rows = []
    return [_json_ready(dict(row)) for row in rows if isinstance(row, dict)]


def _rows_from_frame(frame: Any) -> list[dict[str, Any]]:
    if hasattr(frame, "toPandas"):
        frame = frame.toPandas()
    if hasattr(frame, "to_dict"):
        try:
            rows = frame.to_dict(orient="records")
        except TypeError:
            rows = frame.to_dict("records")
    elif isinstance(frame, list):
        rows = frame
    else:
        rows = []
    return [_json_ready(dict(row)) for row in rows if isinstance(row, dict)]


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return str(value)
