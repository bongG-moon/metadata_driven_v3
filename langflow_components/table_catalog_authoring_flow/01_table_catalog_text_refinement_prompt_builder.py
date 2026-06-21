from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_table_catalog_refinement_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    prompt = "\n".join(
        [
            "You refine natural-language dataset/table catalog descriptions for a manufacturing data agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Do not invent dataset keys, source systems, SQL, API URLs, document IDs, sheet names, or physical column names.",
            "Preserve literal structured information in refined_text: dataset_key, source_type, db_key, query_template blocks, SELECT columns, filter_mappings, required params, date_format, and quantity columns.",
            "If the user pasted SQL or mappings, copy them verbatim or near-verbatim instead of summarizing them away.",
            "For Goodocs sources, document ID/doc_id is the retrieval identifier. sheet_name is optional and must not be requested unless the user says a specific sheet/tab is required.",
            "If the user says there are no required query parameters, preserve that exactly; DATE filter_mappings can still exist as optional filters.",
            "If retrieval essentials are missing, explain them in Korean in missing_information.",
            "",
            "Supported source_type values:",
            json.dumps(["dummy", "oracle", "h_api", "datalake", "goodocs"], ensure_ascii=False),
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
    return {"prompt": prompt, "payload": payload, "prompt_type": "table_catalog_text_refinement"}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class TableCatalogTextRefinementPromptBuilder(Component):
    display_name = "01 Table Catalog Text Refinement Prompt Builder"
    description = "Builds the prompt for the first Gemini/LLM node that cleans a dataset description."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="refinement_prompt", display_name="Refinement Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_table_catalog_refinement_prompt_payload(getattr(self, "payload", None))
        self.status = {"prompt_type": prompt_payload["prompt_type"], "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_table_catalog_refinement_prompt_payload(getattr(self, "payload", None)))
