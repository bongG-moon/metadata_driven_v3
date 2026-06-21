from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


DEFAULT_STATE_PREVIEW_LIMIT = 5


def build_request_payload(question: Any, session_id: str = "", state: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_session_id = _resolve_session_id(session_id, state, question)
    return {
        "payload_version": "agent-v1",
        "status": "ok",
        "request": {"session_id": resolved_session_id, "question": _text_value(question), "timezone": "Asia/Seoul"},
        "state": _compact_previous_state(state),
        "info": [],
        "warnings": [],
        "errors": [],
    }


def _compact_previous_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict):
        state = {}
    result = deepcopy(state)
    result["chat_history"] = list(result.get("chat_history", [])) if isinstance(result.get("chat_history"), list) else []
    result["context"] = dict(result.get("context", {})) if isinstance(result.get("context"), dict) else {}
    result["current_data"] = _compact_current_data(result.get("current_data"))
    if not isinstance(result.get("followup_source_results"), list):
        result["followup_source_results"] = []
    return result


def _compact_current_data(current_data: Any, preview_limit: int = DEFAULT_STATE_PREVIEW_LIMIT) -> dict[str, Any]:
    if not isinstance(current_data, dict):
        return {}
    result = deepcopy(current_data)
    rows = _rows_from_current_data(result)
    row_count = _positive_int(result.get("row_count"), default=len(rows))
    if rows:
        result["rows"] = deepcopy(rows[:preview_limit])
        result.pop("data", None)
    result["row_count"] = row_count
    columns = result.get("columns") if isinstance(result.get("columns"), list) else []
    if not columns:
        columns = _rows_columns(rows)
    result["columns"] = columns
    if rows:
        result["data_is_preview"] = row_count > len(result["rows"])
        result.setdefault("data_ref_loaded", False)
        if isinstance(result.get("data_ref"), dict):
            result.setdefault("data_ref_load_mode", "preview")

    product_key_columns = [str(item) for item in result.get("product_key_columns", []) if str(item or "").strip()] if isinstance(result.get("product_key_columns"), list) else []
    result["product_key_columns"] = product_key_columns
    product_key_values = result.get("product_key_values") if isinstance(result.get("product_key_values"), list) else []
    if not product_key_values and product_key_columns:
        product_key_values = _product_key_values(rows, product_key_columns)
    result["product_key_values"] = deepcopy(product_key_values)
    result["product_key_count"] = _positive_int(result.get("product_key_count"), default=len(product_key_values))
    if not isinstance(result.get("source_dataset_keys"), list):
        result["source_dataset_keys"] = []
    if not isinstance(result.get("source_aliases"), list):
        result["source_aliases"] = []
    return result


def _rows_from_current_data(current_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = current_data.get("rows")
    if not isinstance(rows, list):
        rows = current_data.get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _rows_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _product_key_values(rows: list[dict[str, Any]], product_key_columns: list[str]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in rows:
        product = {key: row.get(key) for key in product_key_columns if row.get(key) not in {None, ""}}
        if product and product not in values:
            values.append(product)
    return values


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(0, parsed)


def _resolve_session_id(session_id: Any, state: Any = None, question: Any = None) -> str:
    explicit = str(session_id or "").strip()
    if explicit:
        return explicit
    state_data = state if isinstance(state, dict) else {}
    return _session_id_from_value(question) or _session_id_from_mapping(state_data) or "demo-session"


def _session_id_from_mapping(value: dict[str, Any]) -> str:
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    request = value.get("request") if isinstance(value.get("request"), dict) else {}
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(request.get(key) or "").strip()
        if text:
            return text
    context = value.get("context") if isinstance(value.get("context"), dict) else {}
    for key in ("session_id", "conversation_id", "chat_id"):
        text = str(context.get(key) or "").strip()
        if text:
            return text
    return ""


def _session_id_from_value(value: Any) -> str:
    for attr in ("session_id", "conversation_id", "chat_id"):
        text = str(getattr(value, attr, "") or "").strip()
        if text:
            return text
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return _session_id_from_mapping(data)
    return ""


def _text_value(value: Any) -> str:
    for attr in ("text", "content"):
        text = getattr(value, attr, None)
        if isinstance(text, str):
            return text
    get_text = getattr(value, "get_text", None)
    if callable(get_text):
        try:
            text = get_text()
            if isinstance(text, str):
                return text
        except Exception:
            pass
    if isinstance(value, str):
        return value
    return str(value or "")



class RequestStateLoader(Component):
    display_name = "00 Router Request Loader"
    description = "Builds the compact request payload from chat input and previous state."
    inputs = [
        MessageTextInput(name="question", display_name="Question", required=True),
        MessageTextInput(name="session_id", display_name="Session ID", value="", advanced=True),
        DataInput(name="state", display_name="Previous State", required=False),
    ]
    outputs = [Output(name="payload", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        state = getattr(self.state, "data", self.state) if getattr(self, "state", None) else None
        payload = build_request_payload(self.question, self.session_id, state)
        return Data(data=payload)
