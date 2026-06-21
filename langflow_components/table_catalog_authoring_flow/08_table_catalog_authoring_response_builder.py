from __future__ import annotations

from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message


def build_table_catalog_authoring_response(payload_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    write_result = payload.get("write_result") if isinstance(payload.get("write_result"), dict) else {}
    message = _message(payload, review, write_result)
    return {
        "status": write_result.get("status", "skipped"),
        "message": message,
        "metadata_type": "table_catalog",
        "items": payload.get("items", []),
        "existing_matches": payload.get("existing_matches", []),
        "conflict_warnings": payload.get("conflict_warnings", []),
        "review": review,
        "write_result": write_result,
        "trace": {
            "raw_text": payload.get("raw_text", ""),
            "refined_text": payload.get("refined_text", ""),
            "duplicate_decision": payload.get("duplicate_decision", {}),
        },
    }


def _message(payload: dict[str, Any], review: dict[str, Any], write_result: dict[str, Any]) -> str:
    lines = ["### Table catalog authoring result"]
    if write_result.get("status") == "ok":
        saved = ", ".join(str(item.get("dataset_key")) for item in write_result.get("saved_items", []))
        lines.append(f"저장 완료: {saved or write_result.get('saved_count', 0)}")
    else:
        reason = write_result.get("skipped_reason") or "; ".join(write_result.get("errors", [])) or "저장 조건을 만족하지 못했습니다."
        lines.append(f"저장되지 않았습니다: {reason}")
    supplements = review.get("supplement_requests", []) if isinstance(review.get("supplement_requests"), list) else []
    if supplements:
        lines.append("")
        lines.append("부족하거나 선택이 필요한 정보:")
        for item in supplements:
            if isinstance(item, dict):
                lines.append(f"- {item.get('field')}: {item.get('reason')}")
            else:
                lines.append(f"- {item}")
    if payload.get("existing_matches") or payload.get("conflict_warnings"):
        lines.append("")
        lines.append("비슷한 기존 정보:")
        for item in payload.get("existing_matches", [])[:5]:
            lines.append(f"- {item.get('reason')} ({(item.get('existing') or {}).get('dataset_key')})")
        for item in payload.get("conflict_warnings", [])[:5]:
            lines.append(f"- 경고: {item.get('reason')} ({(item.get('existing') or {}).get('dataset_key')})")
    if payload.get("items"):
        lines.append("")
        lines.append("생성된 dataset item:")
        for item in payload.get("items", [])[:10]:
            lines.append(f"- {item.get('dataset_key')}")
    return "\n".join(lines)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


class TableCatalogAuthoringResponseBuilder(Component):
    display_name = "08 Table Catalog Authoring Response Builder"
    description = "Builds a playground-friendly Korean response for table catalog authoring."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [
        Output(name="api_response", display_name="API Response", method="build_api_response"),
        Output(name="message", display_name="Message", method="build_message"),
    ]

    def build_api_response(self) -> Data:
        result = build_table_catalog_authoring_response(getattr(self, "payload", None))
        self.status = {"status": result.get("status"), "items": len(result.get("items", []))}
        return Data(data=result)

    def build_message(self) -> Message:
        return Message(text=build_table_catalog_authoring_response(getattr(self, "payload", None))["message"])
