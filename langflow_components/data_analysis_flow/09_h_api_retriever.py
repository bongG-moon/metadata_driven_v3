# 파일 설명: 09 H API Retriever Langflow custom component 파일입니다.
# 흐름 역할: metadata source_config의 H-API job을 실행하고, token 또는 URL이 없으면 dummy fallback으로 대체합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from copy import deepcopy
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: metadata source_config의 H-API job을 실행하고, token 또는 URL이 없으면 dummy fallback으로 대체합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def retrieve_h_api_data(payload_value: Any, api_token: str = "", fetch_limit: Any = "5000") -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else payload
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    jobs = _jobs_for_source(plan)
    if not jobs:
        return _retrieval_payload(plan, state, [], skipped=True, skip_reason="No h_api retrieval jobs.")
    limit = _fetch_limit(fetch_limit)
    results = [_run_h_api_job(job, str(api_token or ""), limit) for job in jobs]
    return _retrieval_payload(plan, state, results)


def _run_h_api_job(job: dict[str, Any], api_token: str, fetch_limit: int) -> dict[str, Any]:
    params = deepcopy(job.get("params", {})) if isinstance(job.get("params"), dict) else {}
    missing = _missing_required_params(params, job.get("required_params", []))
    if missing:
        return _error_result(job, f"Missing required parameter(s): {', '.join(missing)}", "missing_required_params")
    config = _source_config(job)
    api_url = str(config.get("api_url") or "").strip()
    if not api_url:
        return _error_result(job, "H-API source_config must include api_url.", "missing_api_url")
    body = {"bindParams": [_dict_get_ci(params, key) for key in _param_order(job)]}

    if not str(api_token or "").strip():
        rows = _dummy_rows(job, params, api_url, body)[:fetch_limit]
        return _standard_result(job, rows, {"api_url": api_url, "request_body": _json_ready(body), "used_dummy_data": True})

    try:
        requests = import_module("requests")
        headers = {"h-api-token": api_token.strip(), "Content-Type": "application/json"}
        timeout = float(config.get("timeout", 30))
        response = requests.post(api_url, headers=headers, json=body, timeout=timeout)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        parsed = response.json()
        rows = _rows_from_api_payload(parsed, str(config.get("response_path") or ""))[:fetch_limit]
        return _standard_result(job, rows, {"api_url": api_url, "request_body": _json_ready(body), "used_dummy_data": False})
    except Exception as exc:
        return _error_result(job, f"H-API retrieval failed for {job.get('dataset_key')}: {exc}", "retrieval_failed")


def _jobs_for_source(plan: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    selected = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        source = _source_type(job.get("source_type") or _source_config(job).get("source_type"))
        if source in {"h_api", "hapi", "h_api_retriever"}:
            selected.append(job)
    return selected


def _source_config(job: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(job.get("source_config")) if isinstance(job.get("source_config"), dict) else {}
    for key in ("api_url", "url", "timeout", "response_path"):
        if job.get(key) not in (None, "", [], {}):
            config.setdefault(key, deepcopy(job[key]))
    if config.get("url") and not config.get("api_url"):
        config["api_url"] = config["url"]
    return config


def _param_order(job: dict[str, Any]) -> list[str]:
    order = [str(item).strip() for item in _as_list(job.get("param_order")) if str(item).strip()]
    if order:
        return order
    return [str(item).strip() for item in _as_list(job.get("required_params")) if str(item).strip()]


def _rows_from_api_payload(payload: Any, response_path: str = "") -> list[dict[str, Any]]:
    if response_path:
        payload = _rows_from_path(payload, response_path)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data") or payload.get("rows") or payload.get("items") or payload.get("result") or payload.get("results") or []
        if isinstance(rows, dict):
            rows = [rows]
    else:
        rows = []
    return [_json_ready(dict(row)) for row in rows if isinstance(row, dict)]


def _rows_from_path(payload: Any, path: str) -> Any:
    current = payload
    for part in [item for item in str(path or "").split(".") if item]:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _standard_result(job: dict[str, Any], rows: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "success": True,
        "dataset_key": job.get("dataset_key", ""),
        "source_alias": job.get("source_alias", job.get("dataset_key", "")),
        "source_type": "h_api",
        "data": rows,
        "columns": _rows_columns(rows),
        "row_count": len(rows),
        "summary": f"{job.get('dataset_key', 'source')} h_api retrieval complete: {len(rows)} rows",
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
        "source_type": "h_api",
        "data": [],
        "columns": [],
        "row_count": 0,
        "summary": "",
        "error_message": message,
        "failure_type": failure_type,
        "applied_params": deepcopy(job.get("params", {})),
        "applied_filters": deepcopy(job.get("filters", [])),
    }


def _dummy_rows(job: dict[str, Any], params: dict[str, Any], api_url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    lot_id = _dict_get_ci(params, "LOT_ID", "T1234567GEN1")
    return [
        {
            "LOT_ID": lot_id,
            "HOLD_TM": "2026-06-12 09:10:00",
            "HOLD_CD": "QA_HOLD",
            "HOLD_DESC": "Dummy H-API hold history",
            "HOLD_USER_ID": "dummy",
            "EVENT_CD": "HOLD",
            "api_url": api_url,
            "request_body": _json_ready(body),
        }
    ]


def _retrieval_payload(
    plan: dict[str, Any],
    state: dict[str, Any],
    results: list[dict[str, Any]],
    skipped: bool = False,
    skip_reason: str = "",
) -> dict[str, Any]:
    payload = {"route": plan.get("route", "multi_retrieval"), "source_type": "h_api", "source_results": results, "intent_plan": plan, "state": state}
    if skipped:
        payload.update({"skipped": True, "skip_reason": skip_reason})
    return {"retrieval_payload": payload}


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


# 컴포넌트 설명: 09 H API Retriever
# Langflow 표시 설명: metadata source_config의 H-API job을 실행하고, token 또는 URL이 없으면 dummy fallback으로 대체합니다.
class HApiRetriever(Component):

    display_name = "09 H API Retriever"
    description = "metadata source_config의 H-API job을 실행하고, token 또는 URL이 없으면 dummy fallback으로 대체합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="api_token", display_name="H-API Token", value=""),
        MessageTextInput(name="fetch_limit", display_name="Fetch Limit", value="5000", advanced=True),
    ]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: metadata source_config의 H-API job을 실행하고, token 또는 URL이 없으면 dummy fallback으로 대체합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:

        return Data(data=retrieve_h_api_data(getattr(self, "payload", None), self.api_token, self.fetch_limit))
