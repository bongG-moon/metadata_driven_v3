from __future__ import annotations

import json
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_table_catalog_authoring_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    existing_summary = [
        {
            "dataset_key": item.get("dataset_key"),
            "display_name": item.get("display_name"),
            "dataset_family": item.get("dataset_family"),
            "date_scope": item.get("date_scope"),
            "source_type": item.get("source_type"),
            "columns": item.get("columns", [])[:12],
        }
        for item in payload.get("existing_items", [])[:80]
        if isinstance(item, dict)
    ]
    prompt = "\n".join(
        [
            "You convert a refined dataset description into MongoDB-storable table_catalog metadata.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Use only information present in the refined text. Put missing essentials in missing_information.",
            "Use the original user text as the authority for literal SQL, query_template blocks, SELECT columns, filter_mappings, dataset_key, db_key, and source_type.",
            "The refined text may be summarized; do not drop structured details that are present in the original user text.",
            "Do not invent query_template, API URL, document ID, sheet name, DB key, or physical columns.",
            "Capture date_format when a source expects dates in a specific representation such as YYYYMMDD or YYYY-MM-DD.",
            "Capture default_detail_columns when operators expect detail rows to show only a subset of columns.",
            "Source-specific essentials: oracle requires db_key and query_template; datalake requires query_template; h_api requires api_url; goodocs requires doc_id only.",
            "For goodocs, do not ask for db_key or query_template. sheet_name is optional; include it only when the user explicitly provides it or says a specific sheet/tab must be read.",
            "If the user says there are no required query parameters, set required_params=[] even when DATE appears in filter_mappings as an optional filter.",
            "Metadata has two mapping layers: main_flow_filters define standard filter keys, while table_catalog.filter_mappings maps those standard keys to this dataset's physical columns.",
            "Do not put dataset-specific mappings inside main_flow_filters. For each dataset, put DATE/OPER_NAME/product/equipment mappings in table_catalog.filter_mappings.",
            "The left side of filter_mappings must be a standard main flow filter key such as DATE, OPER_NAME, PKG_TYPE1, MCP_NO, EQP_ID, or RECIPE_ID; the right side must be actual source column candidates for this dataset.",
            "If a source uses physical column names that differ from the standard analysis column names, also capture standard_column_aliases as {standard_column: [physical columns]}.",
            "Examples: Goodocs target may use PKG1, MCP NO, OUT계획, so map PKG_TYPE1->PKG1 and OUT_PLAN->OUT계획. Equipment may use PKG1, PKG2, MCPSALENO, so map PKG_TYPE1->PKG1 and MCP_NO->MCPSALENO.",
            "",
            "Existing dataset summary for duplicate awareness:",
            json.dumps(existing_summary, ensure_ascii=False, indent=2),
            "",
            "Original user text:",
            str(payload.get("raw_text") or ""),
            "",
            "Refined text:",
            str(payload.get("refined_text") or ""),
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "items": [
                        {
                            "dataset_key": "stable_dataset_key",
                            "payload": {
                                "display_name": "business display name",
                                "dataset_family": "production | wip | target | lot | hold | equipment | capacity | other",
                                "date_scope": "current_day | history | snapshot | optional",
                                "source_type": "dummy | oracle | h_api | datalake | goodocs",
                                "source_config": {
                                    "source_type": "same as source_type",
                                    "db_key": "required for oracle when known",
                                    "query_template": "required for oracle/datalake when known",
                                    "api_url": "required for h_api when known",
                                    "doc_id": "required for goodocs",
                                    "sheet_name": "optional for goodocs only when explicitly known",
                                },
                                "required_params": ["DATE"],
                                "required_param_mappings": {"DATE": ["WORK_DT"]},
                                "date_format": "optional, e.g. YYYYMMDD or YYYY-MM-DD",
                                "primary_quantity_column": "column or list",
                                "filter_mappings": {"DATE": ["WORK_DT"]},
                                "standard_column_aliases": {"standard analysis column": ["physical columns"]},
                                "default_detail_columns": ["optional detail output columns"],
                                "columns": ["physical columns"],
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
    return {"prompt": prompt, "payload": payload, "prompt_type": "table_catalog_authoring_json"}


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class TableCatalogAuthoringPromptBuilder(Component):
    display_name = "03 Table Catalog Authoring Prompt Builder"
    description = "Builds the Gemini/LLM prompt that converts cleaned text into table catalog JSON."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="authoring_prompt", display_name="Authoring Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_table_catalog_authoring_prompt_payload(getattr(self, "payload", None))
        self.status = {"prompt_type": prompt_payload["prompt_type"], "chars": len(prompt_payload["prompt"])}
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_table_catalog_authoring_prompt_payload(getattr(self, "payload", None)))
