from __future__ import annotations

from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


def merge_previous_result_restore(main_payload_value: Any, restored_payload_value: Any = None) -> dict[str, Any]:
    main_payload = _payload(main_payload_value)
    restored_payload = _payload(restored_payload_value)
    decision = main_payload.get("previous_result_restore") if isinstance(main_payload.get("previous_result_restore"), dict) else {}
    required = bool(decision.get("required"))

    if required and restored_payload:
        result = deepcopy(restored_payload)
        merged = deepcopy(result.get("previous_result_restore")) if isinstance(result.get("previous_result_restore"), dict) else deepcopy(decision)
        merged["used_loader_payload"] = True
        merged.setdefault("branch", "restore_full_previous_rows")
        result["previous_result_restore"] = merged
        return result

    result = deepcopy(main_payload)
    merged = deepcopy(decision)
    merged["used_loader_payload"] = False
    if not merged.get("branch"):
        merged["branch"] = "skip_restore"
    result["previous_result_restore"] = merged
    return result


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class PreviousResultRestoreMerger(Component):
    display_name = "06 Previous Result Restore Merger"
    description = "Merges the optional MongoDB previous-result restore branch back into the data-analysis payload."
    icon = "GitMerge"
    inputs = [
        DataInput(name="main_payload", display_name="Main Payload", required=True),
        DataInput(name="restored_payload", display_name="Restored Payload", required=False),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = merge_previous_result_restore(getattr(self, "main_payload", None), getattr(self, "restored_payload", None))
        self.status = result.get("previous_result_restore", {})
        return Data(data=result)
