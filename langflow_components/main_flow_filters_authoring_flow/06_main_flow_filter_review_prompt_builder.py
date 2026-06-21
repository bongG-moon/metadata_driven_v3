from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_main_flow_filter_review_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    review_input = {
        "items": payload.get("items", []),
        "missing_information": (payload.get("authoring") or {}).get("missing_information", []),
        "normalizer_errors": payload.get("errors", []),
        "existing_matches": payload.get("existing_matches", []),
        "conflict_warnings": payload.get("conflict_warnings", []),
        "duplicate_decision": payload.get("duplicate_decision", {}),
    }
    prompt = "\n".join(
        [
            "You review main flow filter metadata before MongoDB save.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Be practical, not overly strict. Block only when the filter cannot map user terms to columns/params, required fields are missing, or a duplicate decision is required.",
            "Explain supplement requests in Korean for a non-technical manufacturing user.",
            "",
            "Review input:",
            json.dumps(review_input, ensure_ascii=False, indent=2),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "ready_to_save": False,
                    "summary": "Korean summary",
                    "supplement_requests": [
                        {"field": "field", "reason": "Korean reason", "example_user_input": "Korean example"}
                    ],
                    "item_reviews": [{"filter_key": "key", "decision": "pass | needs_fix", "reason": "Korean reason"}],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "main_flow_filter_save_review"}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class MainFlowFilterReviewPromptBuilder(Component):
    display_name = "06 Main Flow Filter Review Prompt Builder"
    description = "Builds the final Gemini/LLM review prompt before saving main flow filter metadata."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="review_prompt", display_name="Review Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_main_flow_filter_review_prompt_payload(getattr(self, "payload", None))
        self.status = {"prompt_type": prompt_payload["prompt_type"], "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_main_flow_filter_review_prompt_payload(getattr(self, "payload", None)))
