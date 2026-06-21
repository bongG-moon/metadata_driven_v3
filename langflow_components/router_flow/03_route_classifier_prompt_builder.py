from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


ALLOWED_ROUTES = ["direct_answer", "metadata_qa", "data_analysis", "report_generation", "operations_diagnosis"]
ALLOWED_METADATA_ACTIONS = [
    "greeting",
    "help",
    "catalog_list",
    "dataset_examples",
    "dataset_detail",
    "dataset_query",
    "domain_search",
]


def build_route_classifier_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    metadata_route = payload.get("metadata_route") if isinstance(payload.get("metadata_route"), dict) else {}
    if not metadata_route.get("route_llm_required"):
        prompt = json.dumps(
            {
                "route": metadata_route.get("route", "data_analysis"),
                "metadata_action": metadata_route.get("metadata_action", ""),
                "target_dataset": metadata_route.get("target_dataset", ""),
                "target_family": metadata_route.get("target_family", ""),
                "confidence": metadata_route.get("confidence", "high"),
                "reason": "The route is already direct; no LLM route classification is required.",
            },
            ensure_ascii=False,
        )
        return {"prompt": prompt, "payload": payload, "prompt_type": "route_classifier_skip", "route_llm_required": False}

    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    prompt = "\n".join(
        [
            "You are a lightweight route classifier for a metadata-driven manufacturing agent.",
            "Return one strict JSON object only. Do not wrap it in markdown.",
            "Your job is only to choose the high-level route. Do not create retrieval jobs, pandas code, or final answers.",
            "Classify by the user's goal, not by exact keyword matching.",
            "",
            "Allowed routes:",
            json.dumps(ALLOWED_ROUTES, ensure_ascii=False),
            "",
            "Allowed metadata actions:",
            json.dumps(ALLOWED_METADATA_ACTIONS, ensure_ascii=False),
            "",
            "Route meanings:",
            "- direct_answer: greeting/help style questions that do not need metadata tables or data analysis.",
            "- metadata_qa: questions about registered datasets, query templates, example questions, or domain metadata.",
            "- data_analysis: questions that ask to retrieve/compute/analyze manufacturing data.",
            "- report_generation: questions that ask to create, summarize, export, or schedule a report document.",
            "- operations_diagnosis: questions that ask to diagnose operational problems, abnormal signals, bottlenecks, root causes, or recommended actions.",
            "",
            "Metadata question types:",
            "- catalog_list: the user asks what datasets/sources are available or asks for a data catalog/list.",
            "- dataset_query: the user asks how a dataset is retrieved, such as SQL/query template/API/source query, not to run the query.",
            "- dataset_examples: the user asks what they can ask with a dataset or asks for usage/example questions.",
            "- dataset_detail: the user asks registered dataset metadata such as columns, filters, source type, required params, date format, or meaning.",
            "- domain_search: the user asks registered business/domain definitions, conditions, aliases, process/product/metric rules.",
            "",
            "Important distinctions:",
            "- '생산량 데이터를 조회하는 쿼리를 알려줘' is metadata_qa/dataset_query because the user wants the registered query/template.",
            "- '오늘 생산량을 보여줘' is data_analysis because the user wants actual production values.",
            "- '재공 데이터로 어떤 질문을 할 수 있어?' is metadata_qa/dataset_examples.",
            "- 'AUTO향 조건 알려줘' is metadata_qa/domain_search.",
            "- 'DA공정 재공이 가장 많은 제품 알려줘' is data_analysis.",
            "",
            "Target dataset rule:",
            "- target_dataset is only for metadata_qa questions about one registered dataset, such as dataset_query, dataset_examples, or dataset_detail.",
            "- Use the metadata summary to infer target_dataset from business terms. The user does not need to say a dataset_key.",
            "- Leave target_dataset empty for normal data_analysis; the later intent planner will choose analysis datasets.",
            "",
            "Route candidate context from deterministic metadata matching:",
            json.dumps(metadata_route, ensure_ascii=False, indent=2),
            "",
            "Available metadata summary:",
            json.dumps(_metadata_summary(metadata), ensure_ascii=False, indent=2),
            "",
            "User question:",
            question,
            "",
            "Required JSON schema:",
            json.dumps(
                {
                    "route": "direct_answer | metadata_qa | data_analysis",
                    "metadata_action": "one allowed metadata action, or empty for data_analysis",
                    "metadata_question_type": "same value as metadata_action when route is metadata_qa, else empty",
                    "target_dataset": "dataset_key from metadata if needed, else empty",
                    "target_family": "dataset_family if useful, else empty",
                    "target_term": "domain/search term if useful, else empty",
                    "confidence": "high | medium | low",
                    "reason": "short reason",
                },
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "route_classifier", "route_llm_required": True}


def _metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = table_catalog.get("datasets") if isinstance(table_catalog.get("datasets"), dict) else {}
    dataset_rows = []
    families: list[str] = []
    for key, item in sorted(datasets.items()):
        if not isinstance(item, dict):
            continue
        family = str(item.get("dataset_family") or "")
        if family and family not in families:
            families.append(family)
        dataset_rows.append(
            {
                "dataset_key": key,
                "display_name": item.get("display_name", ""),
                "dataset_family": family,
                "source_type": item.get("source_type", ""),
            }
        )
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    quantity_terms = domain.get("quantity_terms") if isinstance(domain.get("quantity_terms"), dict) else {}
    quantity_rows = []
    for key, item in sorted(quantity_terms.items()):
        if not isinstance(item, dict):
            continue
        aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
        quantity_rows.append(
            {
                "term_key": key,
                "aliases": aliases[:8],
                "dataset_key": item.get("dataset_key", ""),
                "dataset_family": item.get("dataset_family", ""),
                "quantity_column": item.get("quantity_column", ""),
                "output_column": item.get("output_column", ""),
            }
        )
    return {
        "datasets": dataset_rows,
        "dataset_families": families,
        "quantity_terms": quantity_rows,
        "domain_sections": sorted(str(key) for key in domain.keys()),
    }


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class RouteClassifierPromptBuilder(Component):
    display_name = "03 Route Classifier Prompt Builder"
    description = "Builds a tiny route-classification prompt only when rule routing is ambiguous."
    icon = "MessagesSquare"
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="route_prompt", display_name="Route Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_route_classifier_prompt_payload(getattr(self, "payload", None))
        self.status = {
            "prompt_type": prompt_payload.get("prompt_type", ""),
            "route_llm_required": prompt_payload.get("route_llm_required", False),
            "chars": len(prompt_payload.get("prompt", "")),
        }
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_route_classifier_prompt_payload(getattr(self, "payload", None)))
