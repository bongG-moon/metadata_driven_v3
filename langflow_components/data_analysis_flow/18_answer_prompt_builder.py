from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_answer_prompt_payload(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    if payload.get("direct_response_ready"):
        prompt = json.dumps(
            {"answer_message": payload.get("answer_message", "")},
            ensure_ascii=False,
        )
        return {
            "prompt": prompt,
            "payload": payload,
            "prompt_type": "direct_response_skip",
            "answer_context": {
                "question": (payload.get("request") or {}).get("question", "") if isinstance(payload.get("request"), dict) else "",
                "data": payload.get("data", {}),
                "metadata_qa": payload.get("metadata_qa", {}),
            },
        }
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    source_results = payload.get("source_results") if isinstance(payload.get("source_results"), list) else []
    metadata_context = payload.get("metadata_context") if isinstance(payload.get("metadata_context"), dict) else {}

    answer_context = {
        "question": request.get("question", ""),
        "intent_type": plan.get("intent_type"),
        "analysis_kind": plan.get("analysis_kind"),
        "reasoning_steps": plan.get("reasoning_steps", []),
        "pandas_reasoning_steps": analysis.get("reasoning_steps", []),
        "data": {
            "columns": analysis.get("columns", []),
            "rows": analysis.get("rows", [])[:50],
            "row_count": analysis.get("row_count", 0),
        },
        "source_results": _compact_source_results(source_results),
        "metadata_context": metadata_context,
        "info": payload.get("info", []),
        "warnings": payload.get("warnings", []),
        "errors": payload.get("errors", []) + analysis.get("errors", []),
    }
    prompt = "\n".join(
        [
            "You are the final answer node for a Langflow manufacturing data agent.",
            "Answer in Korean.",
            "Use only the provided result data and metadata context. Do not invent numbers.",
            "Be concise but include the applied conditions, datasets used, and any important caveat.",
            "Do not include Markdown tables, tab-separated tables, plain text tables, or row-by-row result listings in answer_message.",
            "The downstream Answer Message Adapter renders the result table deterministically from data.rows; answer_message must be narrative text only.",
            "If there are errors, explain what failed and what the user can retry.",
            "",
            "Return either plain Korean text or one strict JSON object with this schema:",
            json.dumps({"answer_message": "Korean narrative answer text without result tables"}, ensure_ascii=False, indent=2),
            "",
            "Answer context:",
            json.dumps(answer_context, ensure_ascii=False, indent=2),
        ]
    )
    return {"prompt": prompt, "payload": payload, "prompt_type": "final_answer", "answer_context": answer_context}


def _compact_source_results(source_results: list[Any]) -> list[dict[str, Any]]:
    compact = []
    for result in source_results:
        if not isinstance(result, dict):
            continue
        compact.append(
            {
                "source_alias": result.get("source_alias"),
                "dataset_key": result.get("dataset_key"),
                "source_type": result.get("source_type"),
                "row_count": result.get("row_count"),
                "columns": result.get("columns", []),
                "applied_params": result.get("applied_params", {}),
                "applied_filters": result.get("applied_filters", []),
                "data_ref": result.get("data_ref"),
            }
        )
    return compact


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


class AnswerPromptBuilder(Component):
    display_name = "18 Answer Prompt Builder"
    description = "Builds the prompt that should be sent to the Langflow Gemini/LLM node for final answer writing."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="answer_prompt", display_name="Answer Prompt", method="build_prompt"),
        Output(name="prompt_payload", display_name="Prompt Payload", method="build_prompt_payload"),
    ]

    def build_prompt(self) -> Message:
        prompt_payload = build_answer_prompt_payload(getattr(self, "payload", None))
        context = prompt_payload.get("answer_context", {})
        self.status = {
            "prompt_type": prompt_payload.get("prompt_type", "final_answer"),
            "chars": len(prompt_payload["prompt"]),
            "rows": (context.get("data") or {}).get("row_count", 0),
        }
        return Message(text=prompt_payload["prompt"])

    def build_prompt_payload(self) -> Data:
        return Data(data=build_answer_prompt_payload(getattr(self, "payload", None)))
