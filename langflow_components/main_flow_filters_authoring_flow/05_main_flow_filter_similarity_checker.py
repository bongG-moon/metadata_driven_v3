from __future__ import annotations

from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, Output
from lfx.schema.data import Data


DUPLICATE_ACTION_OPTIONS = ["use_payload", "ask", "merge", "replace", "skip", "create_new"]


def check_main_flow_filter_similarity(payload_value: Any, duplicate_action: str = "") -> dict[str, Any]:
    payload = _payload(payload_value)
    action = _action_from_override(duplicate_action, payload)
    matches = []
    warnings = []
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        item_payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        item_key = _clean(item.get("filter_key")).lower()
        item_aliases = set(_lower_list(item_payload.get("aliases")))
        item_columns = set(_lower_list(item_payload.get("column_candidates")))
        for existing in payload.get("existing_items", []):
            if not isinstance(existing, dict):
                continue
            existing_key = _clean(existing.get("filter_key")).lower()
            alias_overlap = sorted(item_aliases.intersection(_lower_list(existing.get("aliases"))))
            column_overlap = sorted(item_columns.intersection(_lower_list(existing.get("column_candidates"))))
            same_role = _clean(item_payload.get("semantic_role")).lower() == _clean(existing.get("semantic_role")).lower()
            if item_key and item_key == existing_key:
                matches.append(_match(item, existing, "same_filter_key", "같은 filter_key의 기존 main flow filter 정보가 있습니다."))
            elif alias_overlap:
                warnings.append(_warning(item, existing, "alias_overlap", f"alias가 겹칩니다: {', '.join(alias_overlap[:5])}"))
            elif column_overlap and same_role:
                warnings.append(_warning(item, existing, "column_role_overlap", f"같은 역할의 column 후보가 겹칩니다: {', '.join(column_overlap[:5])}"))
    requires_choice = bool(matches) and action == "ask"
    next_payload = dict(payload)
    next_payload["existing_matches"] = matches
    next_payload["conflict_warnings"] = warnings
    next_payload["duplicate_decision"] = {
        "action": action,
        "requires_user_choice": requires_choice,
        "allowed_actions": ["merge", "replace", "skip", "create_new"],
        "message": "같은 filter_key의 기존 main flow filter 정보가 있어 저장 전 처리 방식을 선택해야 합니다." if requires_choice else "",
    }
    return next_payload


def _match(item: dict[str, Any], existing: dict[str, Any], match_type: str, reason: str) -> dict[str, Any]:
    return {
        "match_type": match_type,
        "reason": reason,
        "current": {"filter_key": item.get("filter_key")},
        "existing": {"filter_key": existing.get("filter_key"), "id": existing.get("id")},
    }


def _warning(item: dict[str, Any], existing: dict[str, Any], warning_type: str, reason: str) -> dict[str, Any]:
    return {
        "warning_type": warning_type,
        "reason": reason,
        "current": {"filter_key": item.get("filter_key")},
        "existing": {"filter_key": existing.get("filter_key"), "id": existing.get("id")},
    }


def _lower_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [_clean(item).lower() for item in value if _clean(item)]


def _action(value: Any) -> str:
    action = _clean(value).lower()
    return action if action in {"ask", "merge", "replace", "skip", "create_new"} else "ask"


def _action_from_override(value: Any, payload: dict[str, Any]) -> str:
    override = _clean(value).lower()
    if override in {"", "use_payload"}:
        return _action((payload.get("duplicate_decision") or {}).get("action") or "ask")
    return _action(override)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


class MainFlowFilterSimilarityChecker(Component):
    display_name = "05 Main Flow Filter Similarity Checker"
    description = "Warns about same or confusingly similar filter metadata before saving."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        DropdownInput(name="duplicate_action", display_name="Duplicate Action Override", options=DUPLICATE_ACTION_OPTIONS, value="use_payload", advanced=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    def build_payload(self) -> Data:
        result = check_main_flow_filter_similarity(getattr(self, "payload", None), getattr(self, "duplicate_action", ""))
        self.status = {
            "matches": len(result.get("existing_matches", [])),
            "warnings": len(result.get("conflict_warnings", [])),
            "requires_choice": (result.get("duplicate_decision") or {}).get("requires_user_choice", False),
        }
        return Data(data=result)
