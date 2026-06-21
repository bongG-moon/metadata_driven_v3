# 파일 설명: 10 Datalake Retriever Langflow custom component 파일입니다.
# 흐름 역할: LakeHouse/Datalake 조회 job을 실행하고, 인증 정보가 없으면 dummy fallback으로 대체합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import importlib.util
import json
import os
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


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: LakeHouse/Datalake 조회 job을 실행하고, 인증 정보가 없으면 dummy fallback으로 대체합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
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


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: LakeHouse/Datalake 조회 job을 실행하고, 인증 정보가 없으면 dummy fallback으로 대체합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def retrieve_datalake_data(
    payload_value: Any,
    lakehouse_user_id: str = "",
    lakehouse_token: str = "",
    lakehouse_s3_access_key: str = "",
    lakehouse_s3_secret_key: str = "",
    fetch_limit: Any = "5000",
) -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else payload
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    jobs = _jobs_for_source(plan)
    if not jobs:
        return _retrieval_payload(plan, state, [], skipped=True, skip_reason="No datalake retrieval jobs.")
    limit = _fetch_limit(fetch_limit)
    credentials = {
        "user_id": lakehouse_user_id,
        "token": lakehouse_token,
        "s3_access_key": lakehouse_s3_access_key,
        "s3_secret_key": lakehouse_s3_secret_key,
    }
    results = [_run_datalake_job(job, credentials, limit) for job in jobs]
    return _retrieval_payload(plan, state, results)


def _run_datalake_job(job: dict[str, Any], credentials: dict[str, str], fetch_limit: int) -> dict[str, Any]:
    params = deepcopy(job.get("params", {})) if isinstance(job.get("params"), dict) else {}
    missing = _missing_required_params(params, job.get("required_params", []))
    if missing:
        return _error_result(job, f"Missing required parameter(s): {', '.join(missing)}", "missing_required_params")

    config = _source_config(job)
    query_template = str(config.get("query_template") or "").strip()
    if not query_template:
        return _error_result(job, "Datalake source_config must include query_template.", "missing_query_template")
    sql, missing_template_params = _render_template(query_template, params)
    if missing_template_params:
        return _error_result(job, f"Missing SQL template parameter(s): {', '.join(missing_template_params)}", "missing_template_params")

    if not any(str(value or "").strip() for value in credentials.values()):
        rows = _dummy_rows(job, params, sql)[:fetch_limit]
        return _standard_result(job, rows, {"executed_query": sql, "used_dummy_data": True})

    missing_creds = [key for key, value in credentials.items() if not str(value or "").strip()]
    if missing_creds:
        return _error_result(job, f"Missing LakeHouse credential(s): {', '.join(missing_creds)}", "missing_lakehouse_credentials")

    try:
        _set_lakehouse_env(
            credentials["user_id"],
            credentials["token"],
            credentials["s3_access_key"],
            credentials["s3_secret_key"],
        )
        lakes = _import_lakes()
        lake = lakes.LakeHouse(real_user_id=credentials["user_id"])
        lake.ensure_running(cluster_type=str(config.get("cluster_type") or "starrocks"))
        lake.auto_run_sync_paragraph(code=sql)
        rows = _frame_to_rows(lake.get_rst())[:fetch_limit]
        return _standard_result(job, rows, {"executed_query": sql, "cluster_type": str(config.get("cluster_type") or "starrocks"), "used_dummy_data": False})
    except Exception as exc:
        return _error_result(job, f"Datalake retrieval failed for {job.get('dataset_key')}: {exc}", "retrieval_failed")


def _import_lakes() -> Any:
    override = getattr(DatalakeRetriever, "lakes", None) if "DatalakeRetriever" in globals() else None
    if override is not None:
        return override
    ensure_package("lakes")
    return import_module("lakes")


def _set_lakehouse_env(user_id: str, token: str, access_key: str, secret_key: str) -> None:
    os.environ["LAKEHOUSE_USER_ID"] = str(user_id or "")
    os.environ["LAKEHOUSE_TOKEN"] = str(token or "")
    os.environ["LAKEHOUSE_S3_ACCESS_KEY"] = str(access_key or "")
    os.environ["LAKEHOUSE_S3_SECRET_KEY"] = str(secret_key or "")


def _jobs_for_source(plan: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    selected = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        source = _source_type(job.get("source_type") or _source_config(job).get("source_type"))
        if source in {"datalake", "lakehouse", "lake"}:
            selected.append(job)
    return selected


def _source_config(job: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(job.get("source_config")) if isinstance(job.get("source_config"), dict) else {}
    for key in ("query_template", "sql_template", "sql", "query", "cluster_type"):
        if job.get(key) not in (None, "", [], {}):
            config.setdefault(key, deepcopy(job[key]))
    for alias in ("sql_template", "sql", "query"):
        if config.get(alias) and not config.get("query_template"):
            config["query_template"] = config[alias]
    return config


def _standard_result(job: dict[str, Any], rows: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "success": True,
        "dataset_key": job.get("dataset_key", ""),
        "source_alias": job.get("source_alias", job.get("dataset_key", "")),
        "source_type": "datalake",
        "data": rows,
        "columns": _rows_columns(rows),
        "row_count": len(rows),
        "summary": f"{job.get('dataset_key', 'source')} datalake retrieval complete: {len(rows)} rows",
        "applied_params": deepcopy(job.get("params", {})),
        "applied_filters": deepcopy(job.get("filters", [])),
        "source_execution": {},
    }
    if extra:
        result.update(extra)
        result["source_execution"].update(extra)
    return result


def _error_result(job: dict[str, Any], message: str, failure_type: str) -> dict[str, Any]:
    return {
        "success": False,
        "dataset_key": job.get("dataset_key", "unknown"),
        "source_alias": job.get("source_alias", job.get("dataset_key", "unknown")),
        "source_type": "datalake",
        "data": [],
        "columns": [],
        "row_count": 0,
        "summary": "",
        "error_message": message,
        "failure_type": failure_type,
        "applied_params": deepcopy(job.get("params", {})),
        "applied_filters": deepcopy(job.get("filters", [])),
    }


def _dummy_rows(job: dict[str, Any], params: dict[str, Any], sql: str) -> list[dict[str, Any]]:
    row = {
        "source_type": "datalake",
        "source_name": str(job.get("dataset_key") or "datalake"),
        "dummy_data": True,
        "executed_query": sql,
        "request_params": _json_ready(params),
    }
    row.update({str(key): _json_ready(value) for key, value in params.items()})
    return [row]


def _frame_to_rows(frame: Any) -> list[dict[str, Any]]:
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


def _retrieval_payload(
    plan: dict[str, Any],
    state: dict[str, Any],
    results: list[dict[str, Any]],
    skipped: bool = False,
    skip_reason: str = "",
) -> dict[str, Any]:
    payload = {"route": plan.get("route", "multi_retrieval"), "source_type": "datalake", "source_results": results, "intent_plan": plan, "state": state}
    if skipped:
        payload.update({"skipped": True, "skip_reason": skip_reason})
    return {"retrieval_payload": payload}


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


def _source_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return {"lake": "datalake", "lakehouse": "datalake"}.get(text, text)


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
    if isinstance(data, dict):
        return deepcopy(data)
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"text": text}
        except Exception:
            return {"text": text}
    return {}


# 컴포넌트 설명: 10 Datalake Retriever
# Langflow 표시 설명: LakeHouse/Datalake 조회 job을 실행하고, 인증 정보가 없으면 dummy fallback으로 대체합니다.
class DatalakeRetriever(Component):

    lakes = None

    display_name = "10 Datalake Retriever"
    description = "LakeHouse/Datalake 조회 job을 실행하고, 인증 정보가 없으면 dummy fallback으로 대체합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="lakehouse_user_id", display_name="LAKEHOUSE_USER_ID", value=""),
        MessageTextInput(name="lakehouse_token", display_name="LAKEHOUSE_TOKEN", value=""),
        MessageTextInput(name="lakehouse_s3_access_key", display_name="LAKEHOUSE_S3_ACCESS_KEY", value=""),
        MessageTextInput(name="lakehouse_s3_secret_key", display_name="LAKEHOUSE_S3_SECRET_KEY", value=""),
        MessageTextInput(name="fetch_limit", display_name="Fetch Limit", value="5000", advanced=True),
    ]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: LakeHouse/Datalake 조회 job을 실행하고, 인증 정보가 없으면 dummy fallback으로 대체합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:

        return Data(
            data=retrieve_datalake_data(
                getattr(self, "payload", None),
                self.lakehouse_user_id,
                self.lakehouse_token,
                self.lakehouse_s3_access_key,
                self.lakehouse_s3_secret_key,
                self.fetch_limit,
            )
        )
