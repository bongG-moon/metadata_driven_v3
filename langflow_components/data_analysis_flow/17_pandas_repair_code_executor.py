# File description: 17 Pandas Repair Code Executor Langflow custom component.
# Role: execute only the repaired pandas JSON/code produced after 16B repair prompt.

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data


def _load_pandas_executor_module() -> Any:
    module_path = Path(__file__).with_name("15_pandas_code_executor.py")
    spec = importlib.util.spec_from_file_location("data_analysis_flow_15_pandas_code_executor", module_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load pandas executor module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PANDAS_EXECUTOR = _load_pandas_executor_module()


def execute_repair_pandas_from_llm(
    payload_value: Any,
    llm_response_value: Any,
    specialized_functions_text: Any = "",
) -> dict[str, Any]:
    return _PANDAS_EXECUTOR.execute_repair_pandas_from_llm(
        payload_value,
        llm_response_value,
        specialized_functions_text,
    )


class PandasRepairCodeExecutor(Component):

    display_name = "17 Pandas Repair Code Executor"
    description = "Executes the 16B repair LLM response and writes the repair result into the payload."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
        MessageTextInput(
            name="specialized_functions_text",
            display_name="Specialized Functions",
            value="",
            required=False,
        ),
    ]
    outputs = [
        Output(name="payload_out", display_name="Payload", method="build_payload"),
    ]

    def build_payload(self) -> Data:
        return Data(data=self._result())

    def _result(self) -> dict[str, Any]:
        cached = getattr(self, "_cached_result", None)
        if isinstance(cached, dict):
            return cached
        result = execute_repair_pandas_from_llm(
            getattr(self, "payload", None),
            getattr(self, "llm_response", ""),
            getattr(self, "specialized_functions_text", ""),
        )
        self._cached_result = result
        self._set_status(result)
        return result

    def _set_status(self, result: dict[str, Any]) -> None:
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        repair = result.get("pandas_repair") if isinstance(result.get("pandas_repair"), dict) else {}
        self.status = {
            "status": analysis.get("status"),
            "rows": analysis.get("row_count", 0),
            "safety_passed": analysis.get("safety_passed", False),
            "executed": analysis.get("executed", False),
            "errors": len(analysis.get("errors", [])),
            "repair_required": repair.get("required", False),
            "repair_status": repair.get("status", ""),
            "repair_completed": repair.get("completed", False),
        }
