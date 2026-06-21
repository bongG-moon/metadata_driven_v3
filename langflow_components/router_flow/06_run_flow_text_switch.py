from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
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


def run_flow_text_payload(route_response_value: Any, target_flow: str) -> dict[str, Any]:
    route_response = _as_dict(route_response_value)
    request = route_response.get("request") if isinstance(route_response.get("request"), dict) else {}
    selected_flow = str(route_response.get("selected_flow") or "data_analysis_flow").strip()
    question = str(request.get("question") or route_response.get("question") or "").strip()
    return {
        "selected": selected_flow == target_flow,
        "selected_flow": selected_flow,
        "target_flow": target_flow,
        "question": question,
    }


class RunFlowTextSwitch(Component):
    display_name = "06 Run Flow Text Switch"
    description = "Sends the user question as text to exactly one selected Run Flow."
    icon = "split"
    name = "RunFlowTextSwitch"

    inputs = [DataInput(name="route_response", display_name="Route Response", required=True)]
    outputs = [
        Output(
            name="metadata_qa_text",
            display_name="Metadata QA Text",
            method="build_metadata_qa_text",
            group_outputs=True,
            types=["Message"],
        ),
        Output(
            name="data_analysis_text",
            display_name="Data Analysis Text",
            method="build_data_analysis_text",
            group_outputs=True,
            types=["Message"],
        ),
        Output(
            name="report_generation_text",
            display_name="Report Generation Text",
            method="build_report_generation_text",
            group_outputs=True,
            types=["Message"],
        ),
        Output(
            name="operations_diagnosis_text",
            display_name="Operations Diagnosis Text",
            method="build_operations_diagnosis_text",
            group_outputs=True,
            types=["Message"],
        ),
    ]

    def _build(self, target_flow: str, output_name: str) -> Message:
        payload = run_flow_text_payload(getattr(self, "route_response", None), target_flow)
        if not payload["selected"]:
            self.stop(output_name)
        self.status = {
            "selected_flow": payload["selected_flow"],
            "target_flow": target_flow,
            "selected": payload["selected"],
        }
        return _make_message(payload["question"])

    def build_metadata_qa_text(self) -> Message:
        return self._build("metadata_qa_flow", "metadata_qa_text")

    def build_data_analysis_text(self) -> Message:
        return self._build("data_analysis_flow", "data_analysis_text")

    def build_report_generation_text(self) -> Message:
        return self._build("report_generation_flow", "report_generation_text")

    def build_operations_diagnosis_text(self) -> Message:
        return self._build("operations_diagnosis_flow", "operations_diagnosis_text")
