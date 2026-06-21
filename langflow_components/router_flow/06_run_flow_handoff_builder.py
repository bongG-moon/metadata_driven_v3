from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return deepcopy(data)
    return {}


def _session_id(route_response: dict[str, Any], flow_inputs: dict[str, Any]) -> str:
    for source in (flow_inputs, route_response, _as_dict(route_response.get("request")), _as_dict(flow_inputs.get("state"))):
        value = source.get("session_id")
        if value not in (None, "", [], {}):
            return str(value)
    return "langflow-session"


def _question(route_response: dict[str, Any], flow_inputs: dict[str, Any]) -> str:
    for source in (flow_inputs, route_response, _as_dict(route_response.get("request"))):
        value = source.get("question")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _make_message(text: str) -> Message:
    try:
        return Message(text=text)
    except TypeError:
        return Message(content=text)


def build_handoff_payload(route_response_value: Any, target_flow: str) -> dict[str, Any]:
    route_response = _as_dict(route_response_value)
    flow_inputs = _as_dict(route_response.get("flow_inputs"))
    selected_flow = str(route_response.get("selected_flow") or "").strip() or "data_analysis_flow"
    selected = selected_flow == target_flow
    return {
        **deepcopy(route_response),
        "selected": selected,
        "selected_flow": selected_flow,
        "target_flow": target_flow,
        "question": _question(route_response, flow_inputs),
        "session_id": _session_id(route_response, flow_inputs),
        "route_response": route_response,
    }


class RunFlowHandoffBuilder(Component):
    display_name = "06 Run Flow Branch Router"
    description = "Routes a route_response to exactly one subflow Run Flow branch."
    icon = "split"
    name = "RunFlowBranchRouter"

    inputs = [DataInput(name="route_response", display_name="Route Response", required=True)]

    outputs = [
        Output(name="session_id", display_name="Session ID", method="build_session_id", group_outputs=True, types=["Message"]),
        Output(name="metadata_qa_request", display_name="Metadata QA Request", method="build_metadata_qa_handoff", group_outputs=True, types=["Data"]),
        Output(name="data_analysis_request", display_name="Data Analysis Request", method="build_data_analysis_handoff", group_outputs=True, types=["Data"]),
        Output(
            name="report_generation_request",
            display_name="Report Generation Request",
            method="build_report_generation_handoff",
            group_outputs=True,
            types=["Data"],
        ),
        Output(
            name="operations_diagnosis_request",
            display_name="Operations Diagnosis Request",
            method="build_operations_diagnosis_handoff",
            group_outputs=True,
            types=["Data"],
        ),
    ]

    def _build(self, target_flow: str, output_name: str) -> Data:
        payload = build_handoff_payload(getattr(self, "route_response", None), target_flow)
        if not payload["selected"]:
            self.stop(output_name)
        self.status = {
            "selected_flow": payload.get("selected_flow"),
            "target_flow": target_flow,
            "selected": payload.get("selected"),
        }
        return Data(data=payload)

    def build_session_id(self) -> Message:
        route_response = _as_dict(getattr(self, "route_response", None))
        flow_inputs = _as_dict(route_response.get("flow_inputs"))
        return _make_message(_session_id(route_response, flow_inputs))

    def build_metadata_qa_handoff(self) -> Data:
        return self._build("metadata_qa_flow", "metadata_qa_request")

    def build_data_analysis_handoff(self) -> Data:
        return self._build("data_analysis_flow", "data_analysis_request")

    def build_report_generation_handoff(self) -> Data:
        return self._build("report_generation_flow", "report_generation_request")

    def build_operations_diagnosis_handoff(self) -> Data:
        return self._build("operations_diagnosis_flow", "operations_diagnosis_request")
