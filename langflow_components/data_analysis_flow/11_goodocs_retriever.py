# 파일 설명: 11 Goodocs Retriever Langflow custom component 파일입니다.
# 흐름 역할: Goodocs 문서 기반 source job을 실행하고, 인증 또는 문서 설정이 없으면 dummy fallback으로 대체합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


GOODOCS_SYSTEM_COLUMNS = {"ROW_INDEX", "LastUser", "LastTime", "LastEditType", "FirstUser", "FirstTime", "ROW_ID"}


class Goodocs:
    def __init__(self, auth: dict[str, Any]):
        self.auth = auth

    def read_all(self) -> Any:
        raise RuntimeError("Goodocs class implementation is not configured. Paste the real class or set goodocs_module_name.")


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: Goodocs 문서 기반 source job을 실행하고, 인증 또는 문서 설정이 없으면 dummy fallback으로 대체합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def retrieve_goodocs_data(
    payload_value: Any,
    user_id: str = "",
    token_source: str = "",
    token_key: str = "",
    goodocs_module_name: str = "",
    fetch_limit: Any = "5000",
) -> dict[str, Any]:
    payload = _payload(payload_value)
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else payload
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    jobs = _jobs_for_source(plan)
    if not jobs:
        return _retrieval_payload(plan, state, [], skipped=True, skip_reason="No goodocs retrieval jobs.")
    limit = _fetch_limit(fetch_limit)
    results = [_run_goodocs_job(job, user_id, token_source, token_key, goodocs_module_name, limit) for job in jobs]
    return _retrieval_payload(plan, state, results)


def _run_goodocs_job(
    job: dict[str, Any],
    user_id: str,
    token_source: str,
    token_key: str,
    goodocs_module_name: str,
    fetch_limit: int,
) -> dict[str, Any]:
    config = _source_config(job)
    doc_id = str(config.get("doc_id") or "").strip()
    sheet_name = str(config.get("sheet_name") or "").strip()
    if not doc_id:
        return _error_result(job, "Goodocs source_config must include doc_id.", "missing_doc_id")

    credentials = {"USER_ID": user_id, "TOKEN_SOURCE": token_source, "TOKEN_KEY": token_key}
    if not any(str(value or "").strip() for value in credentials.values()):
        rows = _dummy_rows(job, doc_id)[:fetch_limit]
        return _standard_result(job, rows, {"doc_id": doc_id, "sheet_name": sheet_name, "used_dummy_data": True})

    missing_credentials = [key for key, value in credentials.items() if not str(value or "").strip()]
    if missing_credentials:
        return _error_result(job, f"Missing Goodocs credential(s): {', '.join(missing_credentials)}", "missing_goodocs_credentials")

    auth = {"USER_ID": user_id, "DOC_ID": doc_id, "TOKEN_SOURCE": token_source, "TOKEN_KEY": token_key}
    if sheet_name:
        auth["SHEET_NAME"] = sheet_name
    try:
        goodocs_cls = _goodocs_class(goodocs_module_name)
        goodocs = goodocs_cls(auth)
        if sheet_name and hasattr(goodocs, "read_sheet"):
            frame = goodocs.read_sheet(sheet_name)
        else:
            frame = goodocs.read_all()
        rows = _frame_to_rows(frame)[:fetch_limit]
        return _standard_result(job, rows, {"doc_id": doc_id, "sheet_name": sheet_name, "used_dummy_data": False})
    except Exception as exc:
        return _error_result(job, f"Goodocs retrieval failed for {job.get('dataset_key')}: {exc}", "retrieval_failed")


def _goodocs_class(module_name: str = "") -> Any:
    override = getattr(GoodocsRetriever, "goodocs_class", None) if "GoodocsRetriever" in globals() else None
    if override is not None:
        return override
    if str(module_name or "").strip():
        module = import_module(str(module_name).strip())
        return getattr(module, "Goodocs")
    return Goodocs


def _jobs_for_source(plan: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    selected = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        source = _source_type(job.get("source_type") or _source_config(job).get("source_type"))
        if source in {"goodocs", "goodoc"}:
            selected.append(job)
    return selected


def _source_config(job: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(job.get("source_config")) if isinstance(job.get("source_config"), dict) else {}
    for key in ("doc_id", "document_id", "sheet_name"):
        if job.get(key) not in (None, "", [], {}):
            config.setdefault(key, deepcopy(job[key]))
    if config.get("document_id") and not config.get("doc_id"):
        config["doc_id"] = config["document_id"]
    return config


def _standard_result(job: dict[str, Any], rows: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "success": True,
        "dataset_key": job.get("dataset_key", ""),
        "source_alias": job.get("source_alias", job.get("dataset_key", "")),
        "source_type": "goodocs",
        "data": rows,
        "columns": _rows_columns(rows),
        "row_count": len(rows),
        "summary": f"{job.get('dataset_key', 'source')} goodocs retrieval complete: {len(rows)} rows",
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
        "source_type": "goodocs",
        "data": [],
        "columns": [],
        "row_count": 0,
        "summary": "",
        "error_message": message,
        "failure_type": failure_type,
        "applied_params": deepcopy(job.get("params", {})),
        "applied_filters": deepcopy(job.get("filters", [])),
    }


def _dummy_rows(job: dict[str, Any], doc_id: str) -> list[dict[str, Any]]:
    rows = []
    for index in range(20):
        rows.append(
            {
                "DATE": (job.get("params") or {}).get("DATE", "2026-06-12"),
                "TECH": "TSV" if index % 4 == 0 else "FC",
                "DEN": "2048G" if index % 4 == 0 else "128G",
                "MODE": "HBM3E" if index % 4 == 0 else "LPDDR5",
                "PKG_TYPE1": "HBM" if index % 4 == 0 else "UFBGA",
                "PKG_TYPE2": "HBM" if index % 4 == 0 else "MOBILE",
                "LEAD": "LF",
                "MCP_NO": "H-HBM16E" if index % 4 == 0 else "EMPTY",
                "INPUT_PLAN": 120000 + index * 2000,
                "OUT_PLAN": 90000 + index * 1500,
                "doc_id": doc_id,
            }
        )
    return rows


def _frame_to_rows(frame: Any) -> list[dict[str, Any]]:
    if hasattr(frame, "reset_index"):
        try:
            frame = frame.reset_index(drop=True)
        except Exception:
            pass
    if hasattr(frame, "drop"):
        try:
            drop_columns = [column for column in GOODOCS_SYSTEM_COLUMNS if column in getattr(frame, "columns", [])]
            if drop_columns:
                frame = frame.drop(columns=drop_columns)
        except Exception:
            pass
    if hasattr(frame, "to_dict"):
        try:
            rows = frame.to_dict(orient="records")
        except TypeError:
            rows = frame.to_dict("records")
    elif isinstance(frame, list):
        rows = frame
    else:
        rows = []
    return _drop_system_columns([_json_ready(dict(row)) for row in rows if isinstance(row, dict)])


def _drop_system_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in row.items() if str(key) not in GOODOCS_SYSTEM_COLUMNS} for row in rows]


def _retrieval_payload(
    plan: dict[str, Any],
    state: dict[str, Any],
    results: list[dict[str, Any]],
    skipped: bool = False,
    skip_reason: str = "",
) -> dict[str, Any]:
    payload = {"route": plan.get("route", "multi_retrieval"), "source_type": "goodocs", "source_results": results, "intent_plan": plan, "state": state}
    if skipped:
        payload.update({"skipped": True, "skip_reason": skip_reason})
    return {"retrieval_payload": payload}


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
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


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


# 컴포넌트 설명: 11 Goodocs Retriever
# Langflow 표시 설명: Goodocs 문서 기반 source job을 실행하고, 인증 또는 문서 설정이 없으면 dummy fallback으로 대체합니다.
class GoodocsRetriever(Component):

    goodocs_class = None

    display_name = "11 Goodocs Retriever"
    description = "Goodocs 문서 기반 source job을 실행하고, 인증 또는 문서 설정이 없으면 dummy fallback으로 대체합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="user_id", display_name="USER_ID", value=""),
        MessageTextInput(name="token_source", display_name="TOKEN_SOURCE", value=""),
        MessageTextInput(name="token_key", display_name="TOKEN_KEY", value=""),
        MessageTextInput(name="goodocs_module_name", display_name="Goodocs Module Name", value="", advanced=True),

        MessageTextInput(name="fetch_limit", display_name="Fetch Limit", value="5000", advanced=True),
    ]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: Goodocs 문서 기반 source job을 실행하고, 인증 또는 문서 설정이 없으면 dummy fallback으로 대체합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        return Data(
            data=retrieve_goodocs_data(
                getattr(self, "payload", None),
                self.user_id,
                self.token_source,
                self.token_key,
                self.goodocs_module_name,
                self.fetch_limit,
            )
        )
