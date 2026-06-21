from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return deepcopy(data)
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if isinstance(text, str) and text.strip():
        try:
            parsed = json.loads(text)
        except Exception:
            return {"message": text, "answer_message": text}
        return deepcopy(parsed) if isinstance(parsed, dict) else {"message": text, "answer_message": text}
    return {}


def _walk(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(_walk(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk(child))
    else:
        data = getattr(value, "data", None)
        if isinstance(data, (dict, list)):
            values.extend(_walk(data))
        text = getattr(value, "text", None) or getattr(value, "content", None)
        if isinstance(text, str) and text.strip():
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            if isinstance(parsed, (dict, list)):
                values.extend(_walk(parsed))
    return values


def _extract_api_payload(value: Any) -> dict[str, Any]:
    for item in _walk(value):
        item = _as_dict(item)
        if not item:
            continue
        api_response = item.get("api_response")
        if isinstance(api_response, dict):
            return {"api_response": deepcopy(api_response)}
        if any(key in item for key in ("answer_message", "response_type", "state", "data", "metadata_qa", "analysis")):
            return {"api_response": deepcopy(item)}
    return {}


def _route_selected_flow(route_response_value: Any) -> str:
    route_response = _as_dict(route_response_value)
    return str(route_response.get("selected_flow") or "").strip()


class SelectedRunFlowResponseMerger(Component):
    display_name = "07 Selected Run Flow Response Merger"
    description = "Picks the response from the Run Flow branch selected by the router."
    icon = "merge"
    name = "SelectedRunFlowResponseMerger"

    inputs = [
        DataInput(name="route_response", display_name="Route Response", input_types=["Data", "JSON"], required=True),
        DataInput(name="metadata_qa_response", display_name="Metadata QA Run Outputs", input_types=["Data", "JSON", "Message"], required=False),
        DataInput(name="data_analysis_response", display_name="Data Analysis Run Outputs", input_types=["Data", "JSON", "Message"], required=False),
        DataInput(name="report_generation_response", display_name="Report Generation Run Outputs", input_types=["Data", "JSON", "Message"], required=False),
        DataInput(name="operations_diagnosis_response", display_name="Operations Diagnosis Run Outputs", input_types=["Data", "JSON", "Message"], required=False),
    ]

    outputs = [Output(name="api_response", display_name="API Response", method="build_api_response", types=["Data"])]

    def build_api_response(self) -> Data:
        selected_flow = _route_selected_flow(getattr(self, "route_response", None))
        response_by_flow = {
            "metadata_qa_flow": getattr(self, "metadata_qa_response", None),
            "data_analysis_flow": getattr(self, "data_analysis_response", None),
            "report_generation_flow": getattr(self, "report_generation_response", None),
            "operations_diagnosis_flow": getattr(self, "operations_diagnosis_response", None),
        }
        selected_payload = _extract_api_payload(response_by_flow.get(selected_flow))
        if not selected_payload:
            for flow_name, response in response_by_flow.items():
                selected_payload = _extract_api_payload(response)
                if selected_payload:
                    selected_flow = selected_flow or flow_name
                    break
        if not selected_payload:
            selected_payload = {
                "api_response": {
                    "status": "error",
                    "success": False,
                    "response_type": "run_flow_merge_error",
                    "message": "선택된 Run Flow branch의 응답을 찾지 못했습니다.",
                    "state": {},
                    "errors": ["selected Run Flow response is empty"],
                }
            }
        selected_payload["selected_flow"] = selected_flow
        self.status = {
            "selected_flow": selected_flow,
            "status": _as_dict(selected_payload.get("api_response")).get("status"),
        }
        return Data(data=selected_payload)
