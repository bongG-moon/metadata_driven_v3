from __future__ import annotations
from copy import deepcopy
from typing import Any
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def merge_source_retrieval_payloads(*payload_values: Any) -> dict[str, Any]:
    merged_results = []
    intent_plan = {}
    state = {}
    for value in payload_values:
        payload = _payload(value)
        retrieval = payload.get("retrieval_payload") if isinstance(payload.get("retrieval_payload"), dict) else payload
        if retrieval.get("skipped"):
            continue
        if not intent_plan and isinstance(retrieval.get("intent_plan"), dict):
            intent_plan = deepcopy(retrieval["intent_plan"])
        if not state and isinstance(retrieval.get("state"), dict):
            state = deepcopy(retrieval["state"])
        for item in retrieval.get("source_results", []):
            if isinstance(item, dict):
                merged_results.append(deepcopy(item))
    return {"retrieval_payload": {"route": intent_plan.get("route", "multi_retrieval"), "source_results": merged_results, "intent_plan": intent_plan, "state": state}}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class SourceRetrievalMerger(Component):
    display_name = "12 Source Retrieval Merger"
    description = "Merges Dummy, Oracle, H-API, Datalake, and Goodocs retrieval payloads."
    inputs = [
        DataInput(name="dummy_retrieval", display_name="Dummy Retrieval", required=False),
        DataInput(name="oracle_retrieval", display_name="Oracle Retrieval", required=False),
        DataInput(name="h_api_retrieval", display_name="H-API Retrieval", required=False),
        DataInput(name="datalake_retrieval", display_name="Datalake Retrieval", required=False),
        DataInput(name="goodocs_retrieval", display_name="Goodocs Retrieval", required=False),
    ]
    outputs = [Output(name="retrieval_payload", display_name="Retrieval Payload", method="build_payload")]

    def build_payload(self) -> Data:
        return Data(
            data=merge_source_retrieval_payloads(
                getattr(self, "dummy_retrieval", None),
                getattr(self, "oracle_retrieval", None),
                getattr(self, "h_api_retrieval", None),
                getattr(self, "datalake_retrieval", None),
                getattr(self, "goodocs_retrieval", None),
            )
        )
