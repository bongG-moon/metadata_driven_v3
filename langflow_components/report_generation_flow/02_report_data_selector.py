from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


def select_report_data(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    data_refs = []
    if isinstance(current_data.get("data_ref"), dict):
        data_refs.append(deepcopy(current_data["data_ref"]))
    if isinstance(state.get("followup_source_results"), list):
        for item in state["followup_source_results"]:
            if isinstance(item, dict) and isinstance(item.get("data_ref"), dict):
                data_refs.append(deepcopy(item["data_ref"]))

    report = deepcopy(payload.get("report")) if isinstance(payload.get("report"), dict) else {}
    report["data_selection"] = {
        "mode": "previous_state" if current_data else "needs_analysis_source",
        "columns": list(current_data.get("columns", [])) if isinstance(current_data.get("columns"), list) else [],
        "row_count": int(current_data.get("row_count") or 0),
        "data_refs": data_refs,
    }
    result = deepcopy(payload)
    result["report"] = report
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class ReportDataSelector(Component):
    display_name = "02 Report Data Selector"
    description = "Selects previous analysis data references that can be used to build a report."
    icon = "Database"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = select_report_data(getattr(self, "payload", None))
        self.status = (result.get("report") or {}).get("data_selection", {})
        return Data(data=result)
