from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.message import Message


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _make_message(text: str) -> Message:
    try:
        return Message(text=text)
    except TypeError:
        return Message(content=text)


def selected_run_flow_message(
    route_response_value: Any,
    metadata_qa_output: Any = None,
    data_analysis_output: Any = None,
    report_generation_output: Any = None,
    operations_diagnosis_output: Any = None,
) -> dict[str, Any]:
    route_response = _as_dict(route_response_value)
    selected_flow = str(route_response.get("selected_flow") or "data_analysis_flow").strip()
    outputs = {
        "metadata_qa_flow": metadata_qa_output,
        "data_analysis_flow": data_analysis_output,
        "report_generation_flow": report_generation_output,
        "operations_diagnosis_flow": operations_diagnosis_output,
    }
    selected_output = outputs.get(selected_flow)
    text = _text_from_value(selected_output)
    if not text:
        text = _fallback_message(route_response)
    return {
        "selected_flow": selected_flow,
        "message": text,
        "has_selected_output": bool(_text_from_value(selected_output)),
    }


def _text_from_value(value: Any) -> str:
    if value is None:
        return ""
    for attr in ("text", "content", "message"):
        text = getattr(value, attr, None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    get_text = getattr(value, "get_text", None)
    if callable(get_text):
        try:
            text = get_text()
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            pass
    if isinstance(value, str):
        return value.strip()
    payload = _as_dict(value)
    if payload:
        return _text_from_payload(payload)
    return str(value or "").strip()


def _text_from_payload(payload: dict[str, Any]) -> str:
    for key in ("text", "content", "message", "answer_message", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("api_response", "data", "result", "results"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            text = _text_from_payload(nested)
            if text:
                return text
    outputs = payload.get("outputs")
    if isinstance(outputs, list):
        for item in outputs:
            if isinstance(item, dict):
                text = _text_from_payload(item)
                if text:
                    return text
    return json.dumps(payload, ensure_ascii=False, default=str) if payload else ""


def _fallback_message(route_response: dict[str, Any]) -> str:
    selected_flow = str(route_response.get("selected_flow") or "data_analysis_flow")
    route = str(route_response.get("route") or "")
    return f"Selected flow `{selected_flow}` did not return a message. Route: `{route}`"


class SelectedRunFlowMessageMerger(Component):
    display_name = "07 Selected Run Flow Message Merger"
    description = "Returns the message from the selected Run Flow as one Chat Output message."
    icon = "merge"
    name = "SelectedRunFlowMessageMerger"

    inputs = [
        DataInput(name="route_response", display_name="Route Response", required=True),
        MessageTextInput(name="metadata_qa_output", display_name="Metadata QA Output", required=False),
        MessageTextInput(name="data_analysis_output", display_name="Data Analysis Output", required=False),
        MessageTextInput(name="report_generation_output", display_name="Report Generation Output", required=False),
        MessageTextInput(name="operations_diagnosis_output", display_name="Operations Diagnosis Output", required=False),
    ]
    outputs = [Output(name="message", display_name="Message", method="build_message", types=["Message"])]

    def build_message(self) -> Message:
        result = selected_run_flow_message(
            getattr(self, "route_response", None),
            getattr(self, "metadata_qa_output", None),
            getattr(self, "data_analysis_output", None),
            getattr(self, "report_generation_output", None),
            getattr(self, "operations_diagnosis_output", None),
        )
        self.status = {
            "selected_flow": result["selected_flow"],
            "has_selected_output": result["has_selected_output"],
        }
        return _make_message(result["message"])
