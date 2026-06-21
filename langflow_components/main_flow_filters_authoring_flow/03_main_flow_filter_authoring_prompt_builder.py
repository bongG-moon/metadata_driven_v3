from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_main_flow_filter_authoring_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    existing_summary = [
        {
            "filter_key": item.get("filter_key"),
            "display_name": item.get("display_name"),
            "aliases": item.get("aliases", [])[:8],
            "column_candidates": item.get("column_candidates", [])[:8],
            "semantic_role": item.get("semantic_role"),
            "value_type": item.get("value_type"),
            "operator": item.get("operator"),
        }
        for item in payload.get("existing_items", [])[:80]
        if isinstance(item, dict)
    ]
    prompt = "\n".join(
        [
            "You convert a refined filter/parameter description into MongoDB-storable main_flow_filters metadata.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Use only information present in the refined text. Put missing essentials in missing_information.",
            "These filters help the main agent map user words to retrieval params, physical columns, and pandas filters.",
            "Use semantic_role consistently because runtime normalization uses it to distinguish date/process/product/status/equipment filters.",
            "Include sample_values or value_mappings when business words differ from stored values.",
            "Keep this metadata dataset-neutral. main_flow_filters.column_candidates are broad candidate column names only; dataset-specific mappings such as PKG_TYPE1->PKG1 or MCP_NO->MCPSALENO belong in table_catalog.filter_mappings.",
            "Do not include table_catalog filter_mappings, source_type, query_template, document ID, or DB key in main_flow_filter items.",
            "",
            "Existing filter summary for duplicate awareness:",
            json.dumps(existing_summary, ensure_ascii=False, indent=2),
            "",
            "Refined text:",
            str(payload.get("refined_text") or payload.get("raw_text") or ""),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "items": [
                        {
                            "filter_key": "stable_filter_key",
                            "payload": {
                                "display_name": "business display name",
                                "aliases": ["business words"],
                                "column_candidates": ["physical columns"],
                                "semantic_role": "date | process | product | lot | status | equipment | generic",
                                "value_type": "date | string | number | code",
                                "value_shape": "scalar | list | range",
                                "operator": "eq | in | not_empty | tuple_in | range",
                                "normalized_format": "optional, e.g. YYYYMMDD",
                                "required_params": ["optional retrieval params"],
                                "sample_values": ["optional stored values"],
                                "value_mappings": {"optional user value": "system value"},
                            },
                            "confidence": "high | medium | low",
                        }
                    ],
                    "missing_information": [
                        {"field": "field name", "reason": "Korean reason", "example_user_input": "Korean example"}
                    ],
                    "warnings": ["Korean warning"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "main_flow_filter_authoring_json"}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class MainFlowFilterAuthoringPromptBuilder(Component):
    display_name = "03 Main Flow Filter Authoring Prompt Builder"
    description = "Builds the Gemini/LLM prompt that converts cleaned text into main-flow-filter JSON."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="authoring_prompt", display_name="Authoring Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_main_flow_filter_authoring_prompt_payload(getattr(self, "payload", None))
        self.status = {"prompt_type": prompt_payload["prompt_type"], "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_main_flow_filter_authoring_prompt_payload(getattr(self, "payload", None)))
