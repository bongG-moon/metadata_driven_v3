from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


SINGLE_ORACLE_CONFIG_KEY = "__single_oracle_config__"


def ensure_package(package_name: str, import_name: str | None = None) -> None:
    module_name = import_name or package_name
    if importlib.util.find_spec(module_name) is None:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--trusted-host",
                "nexus.skhynix.com",
                package_name,
            ]
        )


def retrieve_oracle_data(payload_value: Any, oracle_config: Any = "", fetch_limit: Any = "5000") -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else payload
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    jobs = _jobs_for_source(plan, "oracle")
    if not jobs:
        return _retrieval_payload(plan, state, [], skipped=True, skip_reason="No oracle retrieval jobs.")
    limit = _fetch_limit(fetch_limit)
    config, config_errors = _oracle_config_from_value(oracle_config)
    if config_errors:
        results = [_error_result(job, f"Oracle config parse failed: {'; '.join(config_errors)}", "invalid_oracle_config") for job in jobs]
    else:
        oracle_module = getattr(OracleQueryRetriever, "oracledb", None) if "OracleQueryRetriever" in globals() else None
        results = [_run_oracle_job(job, config, limit, oracle_module) for job in jobs]
    return _retrieval_payload(plan, state, results)


def _run_oracle_job(job: dict[str, Any], oracle_config: dict[str, Any], fetch_limit: int, oracle_module: Any | None = None) -> dict[str, Any]:
    params = deepcopy(job.get("params", {})) if isinstance(job.get("params"), dict) else {}
    missing = _missing_required_params(params, job.get("required_params", []))
    if missing:
        return _error_result(job, f"Missing required parameter(s): {', '.join(missing)}", "missing_required_params")

    config = _source_config(job)
    query_template = str(
        config.get("query_template")
        or config.get("sql_template")
        or config.get("oracle_sql")
        or config.get("sql")
        or config.get("query")
        or ""
    ).strip()
    if not query_template:
        return _error_result(job, "Oracle source_config must include query_template.", "missing_query_template")
    sql, missing_template_params = _render_template(query_template, params)
    if missing_template_params:
        return _error_result(job, f"Missing SQL template parameter(s): {', '.join(missing_template_params)}", "missing_template_params")

    db_key = str(config.get("db_key") or job.get("db_key") or "").strip()
    if not db_key:
        return _error_result(job, "Oracle source_config must include db_key.", "missing_db_key")

    if not _config_has_values(oracle_config):
        rows = _dummy_rows(job, params, db_key, sql)[:fetch_limit]
        return _standard_result(job, rows, {"db_key": db_key, "executed_query": sql, "used_dummy_data": True})

    try:
        connector = OracleConnector(oracle_config, oracle_module)
        rows = connector.execute_query(db_key, sql, fetch_limit=fetch_limit)
        return _standard_result(job, _json_ready(rows), {"db_key": db_key, "executed_query": sql, "used_dummy_data": False})
    except Exception as exc:
        return _error_result(job, f"Oracle retrieval failed for {job.get('dataset_key')}: {exc}", "retrieval_failed")


class OracleConnector:
    def __init__(self, config: dict[str, Any], oracle_module: Any | None = None):
        self.config = config
        self.oracle_module = oracle_module

    def _oracledb(self) -> Any:
        if self.oracle_module is not None:
            return self.oracle_module
        ensure_package("oracledb")
        self.oracle_module = import_module("oracledb")
        return self.oracle_module

    def get_connection(self, target_db: str) -> Any:
        resolved = next((key for key in self.config if _normalize_key(key) == _normalize_key(target_db)), "")
        if not resolved and len(self.config) == 1:
            resolved = next(iter(self.config))
        if not resolved:
            raise ValueError(f"Unknown Oracle DB config: {target_db}")
        db_conf = self.config[resolved] if isinstance(self.config.get(resolved), dict) else {}
        user = str(db_conf.get("user") or db_conf.get("username") or db_conf.get("id") or "").strip()
        password = str(db_conf.get("password") or db_conf.get("pw") or "").strip()
        dsn = str(db_conf.get("dsn") or db_conf.get("tns") or db_conf.get("tns_name") or db_conf.get("tns_alias") or "").strip()
        if not dsn:
            raise ValueError(f"Oracle config for {target_db} must include dsn/tns.")
        if user and password:
            return self._oracledb().connect(user=user, password=password, dsn=dsn)
        return self._oracledb().connect(dsn=dsn)

    def execute_query(self, target_db: str, sql: str, fetch_limit: int | None = None) -> list[dict[str, Any]]:
        conn = None
        cursor = None
        try:
            conn = self.get_connection(target_db)
            cursor = conn.cursor()
            cursor.execute(sql)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchmany(fetch_limit) if fetch_limit else cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()


def _jobs_for_source(plan: dict[str, Any], source_type: str) -> list[dict[str, Any]]:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    selected = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_source = _source_type(job.get("source_type") or _source_config(job).get("source_type") or "oracle")
        if job_source in {source_type, "oracle_db", "oracledb"}:
            selected.append(job)
    return selected


def _source_config(job: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(job.get("source_config")) if isinstance(job.get("source_config"), dict) else {}
    for key in ("db_key", "query_template", "sql_template", "oracle_sql", "sql", "query"):
        if job.get(key) not in (None, "", [], {}):
            config.setdefault(key, deepcopy(job[key]))
    return config


def _standard_result(job: dict[str, Any], rows: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "success": True,
        "dataset_key": job.get("dataset_key", ""),
        "source_alias": job.get("source_alias", job.get("dataset_key", "")),
        "source_type": "oracle",
        "data": rows,
        "columns": _rows_columns(rows),
        "row_count": len(rows),
        "summary": f"{job.get('dataset_key', 'source')} oracle retrieval complete: {len(rows)} rows",
        "applied_params": deepcopy(job.get("params", {})),
        "applied_filters": deepcopy(job.get("filters", [])),
        "source_execution": {"source_configured": bool(extra and not extra.get("used_dummy_data"))},
    }
    for key in ("job_id", "job_key", "purpose", "primary_quantity_column"):
        if job.get(key) not in (None, "", [], {}):
            result[key] = deepcopy(job[key])
    if extra:
        result.update(extra)
        result["source_execution"].update({key: value for key, value in extra.items() if key in {"db_key", "executed_query", "used_dummy_data"}})
    return result


def _error_result(job: dict[str, Any], message: str, failure_type: str) -> dict[str, Any]:
    return {
        "success": False,
        "dataset_key": job.get("dataset_key", "unknown"),
        "source_alias": job.get("source_alias", job.get("dataset_key", "unknown")),
        "source_type": "oracle",
        "data": [],
        "columns": [],
        "row_count": 0,
        "summary": "",
        "error_message": message,
        "failure_type": failure_type,
        "applied_params": deepcopy(job.get("params", {})),
        "applied_filters": deepcopy(job.get("filters", [])),
    }


def _dummy_rows(job: dict[str, Any], params: dict[str, Any], db_key: str, sql: str) -> list[dict[str, Any]]:
    row = {
        "source_type": "oracle",
        "source_name": str(job.get("dataset_key") or "oracle"),
        "dummy_data": True,
        "db_key": db_key,
        "executed_query": sql,
        "request_params": _json_ready(params),
    }
    row.update({str(key): _json_ready(value) for key, value in params.items()})
    return [row]


def _retrieval_payload(
    plan: dict[str, Any],
    state: dict[str, Any],
    results: list[dict[str, Any]],
    skipped: bool = False,
    skip_reason: str = "",
) -> dict[str, Any]:
    payload = {"route": plan.get("route", "multi_retrieval"), "source_type": "oracle", "source_results": results, "intent_plan": plan, "state": state}
    if skipped:
        payload.update({"skipped": True, "skip_reason": skip_reason})
    return {"retrieval_payload": payload}


def _oracle_config_from_value(value: Any) -> tuple[dict[str, Any], list[str]]:
    if value in (None, "", {}, []):
        return {}, []
    parsed, errors = _parse_jsonish(value)
    if isinstance(parsed, dict) and isinstance(parsed.get("oracle_config"), dict):
        parsed = parsed["oracle_config"]
    if isinstance(parsed, dict) and parsed:
        return parsed, []
    text = str(value or "").strip()
    named_tns = _parse_named_tns_blocks(text)
    if named_tns:
        return named_tns, []
    if _looks_like_tns(text):
        return {SINGLE_ORACLE_CONFIG_KEY: {"tns": text}}, []
    if errors and not parsed:
        return {}, errors
    return {}, ["Oracle config must be a JSON object or TNS block."]


def _parse_jsonish(value: Any) -> tuple[Any, list[str]]:
    if isinstance(value, (dict, list)):
        return deepcopy(value), []
    text = str(value or "").strip()
    if not text:
        return {}, []
    errors: list[str] = []
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text), []
        except Exception as exc:
            errors.append(str(exc))
    normalized = _normalize_triple_quoted_json(text)
    if normalized != text:
        for parser in (json.loads, ast.literal_eval):
            try:
                return parser(normalized), []
            except Exception as exc:
                errors.append(str(exc))
    return {}, errors


def _normalize_triple_quoted_json(text: str) -> str:
    return re.sub(r'("""|\'\'\')(.*?)(\1)', lambda match: json.dumps(match.group(2)), str(text or ""), flags=re.DOTALL)


def _looks_like_tns(text: str) -> bool:
    upper_text = str(text or "").upper()
    return "(DESCRIPTION=" in upper_text or ("(ADDRESS=" in upper_text and "(CONNECT_DATA=" in upper_text)


def _parse_named_tns_blocks(text: str) -> dict[str, Any]:
    configs: dict[str, Any] = {}
    current_key = ""
    current_lines: list[str] = []

    def save_current() -> None:
        nonlocal current_key, current_lines
        tns = "\n".join(current_lines).strip()
        if current_key and _looks_like_tns(tns):
            configs[current_key] = {"tns": tns}
        current_key = ""
        current_lines = []

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        key_match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if key_match and not line.startswith("("):
            save_current()
            current_key = key_match.group(1).strip()
            possible_tns = key_match.group(2).strip()
            if possible_tns:
                current_lines.append(possible_tns)
            continue
        if current_key:
            current_lines.append(raw_line)
    save_current()
    return configs


def _render_template(template: str, params: dict[str, Any]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = _dict_get_ci(params, key)
        if value in (None, "", []):
            missing.append(key)
            return match.group(0)
        return _sql_literal(value)

    return re.sub(r"\{([^{}]+)\}", replace, str(template or "")), missing


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (datetime, date)):
        return f"'{value.strftime('%Y%m%d')}'"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _missing_required_params(params: dict[str, Any], required_params: Any) -> list[str]:
    missing = []
    for item in _as_list(required_params):
        key = str(item or "").strip()
        if key and _dict_get_ci(params, key) in (None, "", []):
            missing.append(key)
    return missing


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
    try:
        if value != value:
            return None
    except Exception:
        pass
    return str(value)


def _rows_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _fetch_limit(value: Any) -> int:
    try:
        return max(1, int(value or 5000))
    except Exception:
        return 5000


def _config_has_values(config: Any) -> bool:
    return isinstance(config, dict) and any(value not in (None, "", [], {}) for value in config.values())


def _source_type(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_key(value: Any) -> str:
    return re.sub(r"[\s_-]+", "", str(value or "").strip().lower())


def _dict_get_ci(mapping: dict[str, Any], key: Any, default: Any = None) -> Any:
    if not isinstance(mapping, dict):
        return default
    text = str(key or "").strip()
    if text in mapping:
        return mapping[text]
    normalized = _normalize_key(text)
    for item_key, value in mapping.items():
        if _normalize_key(item_key) == normalized:
            return value
    return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class OracleQueryRetriever(Component):
    oracledb = None

    display_name = "08 Oracle Query Retriever"
    description = "Executes Oracle jobs from metadata source_config, with dummy fallback when config is empty."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="oracle_config", display_name="Oracle Config / TNS", value=""),
        MessageTextInput(name="fetch_limit", display_name="Fetch Limit", value="5000", advanced=True),
    ]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(data=retrieve_oracle_data(getattr(self, "payload", None), self.oracle_config, self.fetch_limit))
