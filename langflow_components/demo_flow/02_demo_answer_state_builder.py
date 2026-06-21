from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_answer_and_state(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis", {})
    data = {
        "columns": list(analysis.get("columns", [])),
        "rows": deepcopy(analysis.get("rows", [])),
        "row_count": int(analysis.get("row_count", 0)),
        "data_ref": f"memory://{payload['request']['session_id']}/current_data",
    }
    applied_scope = {
        "intent_type": payload.get("intent_plan", {}).get("intent_type"),
        "analysis_kind": payload.get("intent_plan", {}).get("analysis_kind"),
        "datasets": [result["dataset_key"] for result in payload.get("source_results", [])],
        "source_aliases": [result["source_alias"] for result in payload.get("source_results", [])],
        "step_ids": [step.get("step_id") for step in payload.get("intent_plan", {}).get("step_plan", [])],
        "metadata_refs": payload.get("metadata_context", {}),
    }
    answer_message = _answer_text(data, applied_scope, analysis)
    state = _next_state(payload, data, applied_scope, answer_message)
    next_payload = dict(payload)
    next_payload.pop("runtime_sources", None)
    next_payload["data"] = data
    next_payload["applied_scope"] = applied_scope
    next_payload["answer_message"] = answer_message
    next_payload["state"] = state
    next_payload["status"] = "ok" if not analysis.get("errors") else "warning"
    next_payload["errors"] = analysis.get("errors", [])
    return next_payload


def _answer_text(data: dict[str, Any], applied_scope: dict[str, Any], analysis: dict[str, Any]) -> str:
    if analysis.get("errors"):
        return "분석 단계에서 확인이 필요합니다: " + "; ".join(analysis["errors"])
    datasets = ", ".join(applied_scope.get("datasets", []))
    if data["row_count"] == 0:
        return f"조건에 맞는 데이터가 없습니다. 사용 dataset: {datasets}"
    preview = "; ".join(str(row) for row in data["rows"][:2])
    return f"{data['row_count']}건을 찾았습니다. 사용 dataset: {datasets}. 결과 예시: {preview}"


def _next_state(payload: dict[str, Any], data: dict[str, Any], applied_scope: dict[str, Any], answer_message: str) -> dict[str, Any]:
    state = deepcopy(payload.get("state", {}))
    history = list(state.get("chat_history", []))
    history.append({"role": "user", "content": payload["request"]["question"]})
    history.append({"role": "assistant", "content": answer_message})
    state["chat_history"] = history[-10:]
    state["context"] = {
        "last_intent_type": applied_scope.get("intent_type"),
        "last_analysis_kind": applied_scope.get("analysis_kind"),
        "last_datasets": applied_scope.get("datasets", []),
    }
    state["current_data"] = data
    state["followup_source_results"] = [
        {
            "source_alias": result["source_alias"],
            "dataset_key": result["dataset_key"],
            "data_ref": result["data_ref"],
            "row_count": result["row_count"],
        }
        for result in payload.get("source_results", [])
    ]
    return state



class AnswerStateBuilder(Component):
    display_name = "02 Demo Answer State Builder"
    description = "Fallback/demo answer builder for local checks without a Langflow LLM node."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        payload = getattr(self.payload, "data", self.payload)
        return Data(data=build_answer_and_state(payload))
