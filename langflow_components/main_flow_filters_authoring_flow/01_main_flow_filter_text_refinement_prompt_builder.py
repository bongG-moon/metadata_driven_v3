from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_main_flow_filter_refinement_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    prompt = "\n".join(
        [
            "You refine natural-language filter/parameter descriptions for a manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Do not invent physical column names, normalized formats, value mappings, or operators.",
            "If a filter cannot be used by retrieval/analysis yet, explain missing information in Korean.",
            "",
            "User text:",
            str(payload.get("raw_text") or ""),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "refined_text": "cleaned description",
                    "needs_more_input": False,
                    "missing_information": [
                        {
                            "field": "required field name",
                            "reason": "Korean reason",
                            "example_user_input": "Korean example",
                        }
                    ],
                    "assumptions": ["safe assumptions only"],
                    "remaining_questions": ["Korean question"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "main_flow_filter_text_refinement"}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class MainFlowFilterTextRefinementPromptBuilder(Component):
    display_name = "01 Main Flow Filter Text Refinement Prompt Builder"
    description = "Builds the prompt for the first Gemini/LLM node that cleans a filter description."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="refinement_prompt", display_name="Refinement Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_main_flow_filter_refinement_prompt_payload(getattr(self, "payload", None))
        self.status = {"prompt_type": prompt_payload["prompt_type"], "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_main_flow_filter_refinement_prompt_payload(getattr(self, "payload", None)))
