# 파일 설명: 04 Metadata QA Message Adapter Langflow custom component 파일입니다.
# 흐름 역할: metadata QA 최종 payload를 Langflow Chat Output에 연결하기 좋은 Message로 변환합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


from lfx.custom.custom_component.component import Component

from lfx.io import DataInput, MessageTextInput, Output

from lfx.schema.data import Data
from lfx.schema.message import Message


TABLE_PREVIEW_LIMIT = 20
CELL_TEXT_LIMIT = 120
CODE_TEXT_LIMIT = 4000


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: metadata QA 최종 payload를 Langflow Chat Output에 연결하기 좋은 Message로 변환합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def build_playground_message(payload_value: Any) -> str:
    payload = _payload(payload_value)
    answer = _escape_markdown_tilde(str(payload.get("answer_message") or "").strip())
    if not payload:
        return ""

    sections: list[str] = []
    if answer:
        sections.append("### 답변\n" + answer)

    data_section = _result_table_section(payload)
    if data_section:
        sections.append(data_section)

    intent_section = _intent_section(payload)
    if intent_section:
        sections.append(intent_section)

    pandas_section = _pandas_section(payload)
    if pandas_section:
        sections.append(pandas_section)

    notice_section = _notice_section(payload)
    if notice_section:
        sections.append(notice_section)

    if sections:
        return "\n\n".join(sections)
    if payload:
        return json.dumps(payload, ensure_ascii=False, default=str)
    return ""


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    data = getattr(value, "data", None)
    return deepcopy(data) if isinstance(data, dict) else {}


def _result_table_section(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    columns = data.get("columns") if isinstance(data.get("columns"), list) else []
    row_count = int(data.get("row_count") or len(rows) or 0)

    if not columns:
        columns = _columns_from_rows(rows)

    if not rows:
        if columns:
            return "### 참고 정보\n표시할 참고 행은 없고, 컬럼만 확인되었습니다: " + ", ".join(str(item) for item in columns)
        return "### 참고 정보\n표시할 참고 데이터가 없습니다."

    preview_rows = rows[:TABLE_PREVIEW_LIMIT]
    table = _markdown_table(preview_rows, columns)
    note = f"\n\n총 {row_count}건 중 {len(preview_rows)}건을 표시했습니다."
    if row_count <= len(preview_rows):
        note = f"\n\n총 {row_count}건입니다."
    return "### 참고 정보\n" + table + note


def _intent_section(payload: dict[str, Any]) -> str:
    plan = payload.get("intent_plan") if isinstance(payload.get("intent_plan"), dict) else {}
    applied_scope = payload.get("applied_scope") if isinstance(payload.get("applied_scope"), dict) else {}
    if not plan and not applied_scope:
        return ""

    lines = ["### 의도 분석"]
    route = plan.get("route")
    intent_type = plan.get("intent_type") or applied_scope.get("intent_type")
    analysis_kind = plan.get("analysis_kind") or applied_scope.get("analysis_kind")
    datasets = applied_scope.get("datasets") or plan.get("datasets") or []
    source_aliases = applied_scope.get("source_aliases") or []

    for label, value in (
        ("route", route),
        ("intent_type", intent_type),
        ("analysis_kind", analysis_kind),
        ("datasets", datasets),
        ("source_aliases", source_aliases),
    ):
        if value not in (None, "", [], {}):
            lines.append(f"- {label}: `{_inline_value(value)}`")

    step_plan = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    if step_plan:
        lines.append("- step_plan:")
        for index, step in enumerate(step_plan, start=1):
            lines.append(f"  {index}. {_step_label(step)}")

    reasoning_steps = plan.get("reasoning_steps") if isinstance(plan.get("reasoning_steps"), list) else []
    if reasoning_steps:
        lines.append("- intent_reasoning:")
        for index, step in enumerate(reasoning_steps[:8], start=1):
            lines.append(f"  {index}. {step}")

    retrieval_jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    if retrieval_jobs:
        lines.append("- retrieval_jobs:")
        for job in retrieval_jobs[:8]:
            lines.append("  - " + _retrieval_job_label(job))

    filters = applied_scope.get("filters_by_source")
    params = applied_scope.get("params_by_source")
    if filters not in (None, "", [], {}):
        lines.append(f"- applied_filters: `{_inline_value(filters)}`")
    if params not in (None, "", [], {}):
        lines.append(f"- applied_params: `{_inline_value(params)}`")

    return "\n".join(lines)


def _pandas_section(payload: dict[str, Any]) -> str:
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    if not analysis:
        return ""

    lines = ["### Pandas 처리"]
    for label, value in (
        ("status", analysis.get("status")),
        ("safety_passed", analysis.get("safety_passed")),
        ("executed", analysis.get("executed")),
        ("row_count", analysis.get("row_count")),
        ("output_columns", analysis.get("output_columns") or analysis.get("columns")),
    ):
        if value not in (None, "", [], {}):
            lines.append(f"- {label}: `{_inline_value(value)}`")

    reasoning_steps = analysis.get("reasoning_steps") if isinstance(analysis.get("reasoning_steps"), list) else []
    if reasoning_steps:
        lines.append("- pandas_reasoning:")
        for index, step in enumerate(reasoning_steps[:8], start=1):
            lines.append(f"  {index}. {step}")

    code = str(analysis.get("analysis_code") or "").strip()
    if not code:
        pandas_json = analysis.get("pandas_code_json") if isinstance(analysis.get("pandas_code_json"), dict) else {}
        code = str(pandas_json.get("code") or "").strip()
    if code:
        code = _truncate(code, CODE_TEXT_LIMIT)
        lines.append("\n```python\n" + code + "\n```")

    errors = analysis.get("errors") if isinstance(analysis.get("errors"), list) else []
    if errors:
        lines.append("- errors: `" + _inline_value(errors) + "`")

    return "\n".join(lines)


def _notice_section(payload: dict[str, Any]) -> str:
    notices = []
    for key in ("info", "warnings", "errors"):
        values = payload.get(key)
        if isinstance(values, list) and values:
            notices.append(f"- {key}: `{_inline_value(values)}`")
    if not notices:
        return ""
    return "### 참고\n" + "\n".join(notices)


def _markdown_table(rows: list[Any], columns: list[Any]) -> str:
    cleaned_columns = [str(column) for column in columns if str(column or "").strip()]
    if not cleaned_columns:
        cleaned_columns = _columns_from_rows(rows)
    header = "| " + " | ".join(_escape_table_cell(column) for column in cleaned_columns) + " |"
    divider = "| " + " | ".join("---" for _ in cleaned_columns) + " |"
    body = []
    for row in rows:
        row_dict = row if isinstance(row, dict) else {}
        body.append("| " + " | ".join(_escape_table_cell(row_dict.get(column, "")) for column in cleaned_columns) + " |")
    return "\n".join([header, divider] + body)


def _columns_from_rows(rows: list[Any]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            text = str(key)
            if text not in columns:
                columns.append(text)
    return columns


def _escape_table_cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = "" if value is None else str(value)
    text = _truncate(text.replace("\n", "<br>"), CELL_TEXT_LIMIT)
    return _escape_markdown_tilde(text.replace("|", "\\|"))


def _escape_markdown_tilde(text: str) -> str:
    return re.sub(r"(?<!\\)~", r"\\~", text)


def _step_label(step: Any) -> str:
    if not isinstance(step, dict):
        return str(step)
    parts = []
    for key in (
        "step_id",
        "operation",
        "source_alias",
        "dataset_key",
        "group_by",
        "metric",
        "top_n",
        "bottom_n",
        "rank_order",
        "join_keys",
        "output_alias",
    ):
        value = step.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{key}={_inline_value(value)}")
    return ", ".join(parts) if parts else _inline_value(step)


def _retrieval_job_label(job: Any) -> str:
    if not isinstance(job, dict):
        return str(job)
    parts = []
    for key in ("dataset_key", "source_alias", "source_type", "purpose", "params", "filters"):
        value = job.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{key}={_inline_value(value)}")
    return ", ".join(parts) if parts else _inline_value(job)


def _inline_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _truncate(json.dumps(value, ensure_ascii=False, default=str), 900)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... truncated ..."



# 컴포넌트 설명: 04 Metadata QA Message Adapter
# Langflow 표시 설명: metadata QA 최종 payload를 Langflow Chat Output에 연결하기 좋은 Message로 변환합니다.
class AnswerMessageAdapter(Component):

    display_name = "04 Metadata QA Message Adapter"
    description = "metadata QA 최종 payload를 Langflow Chat Output에 연결하기 좋은 Message로 변환합니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="message", display_name="Message", method="build_message")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: metadata QA 최종 payload를 Langflow Chat Output에 연결하기 좋은 Message로 변환합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_message(self) -> Message:
        return Message(text=build_playground_message(self.payload))
