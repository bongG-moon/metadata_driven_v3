# 파일 설명: 20 Answer Message Adapter Langflow custom component 파일입니다.
# 흐름 역할: 답변, 결과 테이블, 의도 분석, pandas 코드가 포함된 Playground용 Message를 만듭니다.
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
GENERIC_REASONING_TEXT = "분석 계획에 따라 필요한 데이터를 처리합니다."
INTENT_FIELD_LABELS = {
    "route": "처리 경로",
    "intent_type": "의도 유형",
    "analysis_kind": "분석 유형",
    "datasets": "사용 데이터셋",
    "source_aliases": "소스 별칭",
}
PANDAS_FIELD_LABELS = {
    "status": "상태",
    "safety_passed": "안전성 검사",
    "executed": "실행 여부",
    "row_count": "결과 행 수",
    "output_columns": "출력 컬럼",
}
STEP_FIELD_LABELS = {
    "step_id": "단계 ID",
    "operation": "작업",
    "source_alias": "소스 별칭",
    "dataset_key": "데이터셋",
    "group_by": "그룹 기준",
    "metric": "집계 지표",
    "top_n": "상위 N",
    "bottom_n": "하위 N",
    "rank_order": "정렬 방향",
    "join_keys": "조인 키",
    "output_alias": "출력 별칭",
}
JOB_FIELD_LABELS = {
    "dataset_key": "데이터셋",
    "source_alias": "소스 별칭",
    "source_type": "소스 유형",
    "purpose": "조회 목적",
    "params": "조회 파라미터",
    "filters": "조회 필터",
}
NOTICE_LABELS = {
    "info": "안내",
    "warnings": "경고",
    "errors": "오류",
}
VALUE_LABELS = {
    "ok": "정상",
    "error": "오류",
    "failed": "실패",
    "success": "성공",
    "multi_retrieval": "다중 데이터 조회",
    "single_retrieval": "단일 데이터 조회",
    "metadata_qa": "메타데이터 질의",
    "data_analysis": "데이터 분석",
    "desc": "내림차순",
    "asc": "오름차순",
}


# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: 답변, 결과 테이블, 의도 분석, pandas 코드가 포함된 Playground용 Message를 만듭니다.
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
            return "### 결과 테이블\n표시할 결과 행은 없고, 컬럼만 확인되었습니다: " + ", ".join(str(item) for item in columns)
        return "### 결과 테이블\n표시할 결과 데이터가 없습니다."

    preview_rows = rows[:TABLE_PREVIEW_LIMIT]
    table = _markdown_table(preview_rows, columns)
    note = f"\n\n총 {row_count}건 중 {len(preview_rows)}건을 표시했습니다."
    if row_count <= len(preview_rows):
        note = f"\n\n총 {row_count}건입니다."
    return "### 결과 테이블\n" + table + note


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
            lines.append(f"- {INTENT_FIELD_LABELS.get(label, label)}: `{_display_value(value)}`")

    step_plan = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    if step_plan:
        lines.append("- 분석 단계:")
        for index, step in enumerate(step_plan, start=1):
            lines.append(f"  {index}. {_step_label(step)}")

    reasoning_steps = _intent_reasoning_steps(plan, applied_scope)
    if reasoning_steps:
        lines.append("- 의도 판단 근거:")
        for index, step in enumerate(reasoning_steps[:8], start=1):
            lines.append(f"  {index}. {step}")

    retrieval_jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    if retrieval_jobs:
        lines.append("- 조회 작업:")
        for job in retrieval_jobs[:8]:
            lines.append("  - " + _retrieval_job_label(job))

    filters = applied_scope.get("filters_by_source")
    params = applied_scope.get("params_by_source")
    if filters not in (None, "", [], {}):
        lines.append(f"- 적용 필터: `{_display_value(filters)}`")
    if params not in (None, "", [], {}):
        lines.append(f"- 적용 파라미터: `{_display_value(params)}`")

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
            lines.append(f"- {PANDAS_FIELD_LABELS.get(label, label)}: `{_display_value(value)}`")

    reasoning_steps = _display_reasoning_steps(analysis.get("reasoning_steps"))
    if reasoning_steps:
        lines.append("- Pandas 처리 근거:")
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
        lines.append("- 오류: `" + _display_value(errors) + "`")

    return "\n".join(lines)


def _notice_section(payload: dict[str, Any]) -> str:
    notices = []
    for key in ("info", "warnings", "errors"):
        values = payload.get(key)
        if isinstance(values, list) and values:
            notices.append(f"- {NOTICE_LABELS.get(key, key)}: `{_display_value(values)}`")
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
            parts.append(f"{STEP_FIELD_LABELS.get(key, key)}={_display_value(value)}")
    return ", ".join(parts) if parts else _inline_value(step)


def _retrieval_job_label(job: Any) -> str:
    if not isinstance(job, dict):
        return str(job)
    parts = []
    for key in ("dataset_key", "source_alias", "source_type", "purpose", "params", "filters"):
        value = job.get(key)
        if value not in (None, "", [], {}):
            display_value = _koreanize_reasoning_text(value) if key == "purpose" else _display_value(value)
            parts.append(f"{JOB_FIELD_LABELS.get(key, key)}={display_value}")
    return ", ".join(parts) if parts else _inline_value(job)


def _display_value(value: Any) -> str:
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in VALUE_LABELS:
            return f"{VALUE_LABELS[text.lower()]} ({text})"
        return text
    if isinstance(value, list):
        return _truncate(json.dumps([_display_scalar(item) for item in value], ensure_ascii=False, default=str), 900)
    if isinstance(value, dict):
        return _truncate(json.dumps(_display_dict_values(value), ensure_ascii=False, default=str), 900)
    return _inline_value(value)


def _display_scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, str):
        text = value.strip()
        return f"{VALUE_LABELS[text.lower()]} ({text})" if text.lower() in VALUE_LABELS else value
    if isinstance(value, list):
        return [_display_scalar(item) for item in value]
    if isinstance(value, dict):
        return _display_dict_values(value)
    return value


def _display_dict_values(value: dict[Any, Any]) -> dict[str, Any]:
    return {str(key): _display_scalar(item) for key, item in value.items()}


def _inline_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return _truncate(json.dumps(value, ensure_ascii=False, default=str), 900)


def _intent_reasoning_steps(plan: dict[str, Any], applied_scope: dict[str, Any]) -> list[str]:
    raw_steps = plan.get("reasoning_steps") if isinstance(plan.get("reasoning_steps"), list) else []
    cleaned = _display_reasoning_steps(raw_steps)
    if _should_replace_intent_reasoning(raw_steps, cleaned, plan):
        generated = _generated_intent_reasoning_steps(plan, applied_scope)
        if generated:
            return generated
    return cleaned


def _display_reasoning_steps(value: Any) -> list[str]:
    raw_steps = value if isinstance(value, list) else []
    result: list[str] = []
    for item in raw_steps:
        text = _koreanize_reasoning_text(item).strip()
        if not text:
            continue
        if text not in result:
            result.append(text)
    return result


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def _should_replace_intent_reasoning(raw_steps: list[Any], cleaned_steps: list[str], plan: dict[str, Any]) -> bool:
    if not (plan.get("retrieval_jobs") or plan.get("step_plan")):
        return False
    if not cleaned_steps:
        return True
    generic_count = sum(1 for item in raw_steps if _is_generic_reasoning(item))
    if generic_count >= 2 and generic_count >= len(raw_steps) // 2:
        return True
    if len(cleaned_steps) <= 1 and len(plan.get("step_plan") or []) >= 1:
        return True
    return False


def _is_generic_reasoning(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lower = text.lower()
    generic_fragments = [
        GENERIC_REASONING_TEXT,
        "according to the analysis plan",
        "according to analysis plan",
        "necessary data",
        "required data",
        "process the required data",
        "processes the required data",
        "분석 계획",
        "필요한 데이터를 처리",
    ]
    return any(fragment.lower() in lower for fragment in generic_fragments)


def _generated_intent_reasoning_steps(plan: dict[str, Any], applied_scope: dict[str, Any]) -> list[str]:
    steps: list[str] = []
    datasets = applied_scope.get("datasets") or plan.get("datasets") or []
    if datasets:
        steps.append(f"요청 처리에 필요한 데이터셋으로 `{_display_value(datasets)}`를 사용합니다.")

    params_by_source = applied_scope.get("params_by_source") if isinstance(applied_scope.get("params_by_source"), dict) else {}
    if not params_by_source:
        params_by_source = {
            str(job.get("source_alias") or job.get("dataset_key")): job.get("params", {})
            for job in plan.get("retrieval_jobs", [])
            if isinstance(job, dict) and isinstance(job.get("params"), dict)
        }
    date_values = _unique(
        [
            str(params.get("DATE"))
            for params in params_by_source.values()
            if isinstance(params, dict) and params.get("DATE") not in (None, "", [], {})
        ]
    )
    if date_values:
        steps.append(f"조회 기준일은 `{_display_value(date_values)}`로 설정합니다.")

    filters_by_source = applied_scope.get("filters_by_source") if isinstance(applied_scope.get("filters_by_source"), dict) else {}
    if not filters_by_source:
        filters_by_source = {
            str(job.get("source_alias") or job.get("dataset_key")): job.get("filters", [])
            for job in plan.get("retrieval_jobs", [])
            if isinstance(job, dict) and isinstance(job.get("filters"), list)
        }
    for message in _filter_reasoning_messages(plan, filters_by_source):
        steps.append(message)

    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        message = _step_reasoning_message(step)
        if message:
            steps.append(message)

    return _unique([step for step in steps if step])[:8]


def _filter_reasoning_messages(plan: dict[str, Any], filters_by_source: dict[str, Any]) -> list[str]:
    scope_by_field = {
        str(item.get("source_field") or ""): item
        for item in plan.get("result_scope_columns", [])
        if isinstance(item, dict) and item.get("source_field")
    }
    messages: list[str] = []
    for alias, filters in filters_by_source.items():
        if not isinstance(filters, list):
            continue
        for condition in filters:
            if not isinstance(condition, dict):
                continue
            field = str(condition.get("field") or "").strip()
            if not field or field == "DATE":
                continue
            scope = scope_by_field.get(field)
            if scope and scope.get("column") and scope.get("value"):
                messages.append(f"`{alias}` 데이터는 `{scope['column']}={scope['value']}` 범위로 해석된 조건을 적용합니다.")
                continue
            messages.append(f"`{alias}` 데이터에 `{field}` 필터 `{_filter_condition_value(condition)}`를 적용합니다.")
    return _unique(messages)


def _filter_condition_value(condition: dict[str, Any]) -> str:
    op = str(condition.get("op") or "eq").strip()
    if "value" in condition:
        return f"{op} {_display_value(condition.get('value'))}"
    if isinstance(condition.get("values"), list):
        return f"{op} {_display_value(condition.get('values'))}"
    return op


def _step_reasoning_message(step: Any) -> str:
    if not isinstance(step, dict):
        return ""
    operation = str(step.get("operation") or "").strip()
    source = str(step.get("source_alias") or "").strip()
    metric = str(step.get("metric") or step.get("value_column") or step.get("quantity_column") or "").strip()
    group_by = step.get("group_by") if isinstance(step.get("group_by"), list) else step.get("group_by_columns")
    group_text = _display_value(group_by) if group_by not in (None, "", [], {}) else "전체"
    if operation in {"rank_top_n", "rank_bottom_n"}:
        top_n = step.get("top_n") or step.get("bottom_n") or ""
        order = _display_value(step.get("rank_order") or ("asc" if operation == "rank_bottom_n" else "desc"))
        return f"`{source}`에서 `{group_text}` 기준으로 `{metric}`을 집계하고 `{order}` 정렬 후 상위 {top_n}개를 선택합니다."
    if operation in {"aggregate", "aggregate_sum", "aggregate_by_group", "aggregate_metric", "aggregate_sum_by_group", "sum_by_group"}:
        return f"`{source}`에서 `{group_text}` 기준으로 `{metric}` 값을 집계합니다."
    if operation in {"equipment_count_by_product", "unique_count_by_group", "nunique_by_group"}:
        count_column = str(step.get("count_column") or "").strip()
        return f"`{source}`에서 `{group_text}` 기준으로 `{count_column}` 고유 개수를 계산합니다."
    if operation == "hold_lot_in_tat_by_process":
        return f"`{source}`에서 공정 기준으로 HOLD LOT 수와 평균 IN_TAT를 계산합니다."
    if operation == "left_join":
        left = step.get("left_step")
        right = step.get("right_step")
        keys = step.get("join_keys") or step.get("join_key")
        return f"`{left}` 결과와 `{right}` 결과를 `{_display_value(keys)}` 기준으로 left join합니다."
    if operation == "detail_rows":
        return f"`{source}`의 상세 행을 결과로 반환합니다."
    return ""


def _koreanize_reasoning_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _strip_korean_action_prefix(text)
    if _contains_korean(text):
        return text

    patterns = [
        (
            r"^The user wants to see the top (\d+) products by production quantity in the ([A-Za-z0-9_/]+) process group\.?$",
            lambda match: f"사용자는 {match.group(2)} 공정군에서 생산량 기준 상위 {match.group(1)}개 제품을 확인하려고 합니다.",
        ),
        (
            r"^The user wants to see the top (\d+) products? by (.+?) in the ([A-Za-z0-9_/]+) process group\.?$",
            lambda match: f"사용자는 {match.group(3)} 공정군에서 {match.group(2)} 기준 상위 {match.group(1)}개 제품을 확인하려고 합니다.",
        ),
        (
            r"^First, I need to retrieve production data filtered by the ([A-Za-z0-9_/]+) process group and rank products by production quantity\.?$",
            lambda match: f"먼저 {match.group(1)} 공정군으로 필터링한 생산 데이터를 조회하고 생산량 기준으로 제품 순위를 계산합니다.",
        ),
        (
            r"^Then, for each of these top (\d+) products, I need to find the count of assigned equipment\.?$",
            lambda match: f"그 다음 선정된 상위 {match.group(1)}개 제품별 할당 장비 대수를 계산합니다.",
        ),
        (
            r"^This requires two datasets: '([^']+)' for ranking and '([^']+)' for equipment count\.?$",
            lambda match: f"이를 위해 순위 산정용 `{match.group(1)}` 데이터셋과 장비 대수 계산용 `{match.group(2)}` 데이터셋을 사용합니다.",
        ),
        (
            r"^The analysis involves multiple steps: ranking, aggregating equipment count, and then joining the results\.?$",
            lambda match: "분석은 생산량 순위 산정, 장비 대수 집계, 결과 조인 순서로 진행됩니다.",
        ),
        (
            r"^The ['\"]?top_n['\"]? is set to (\d+) and ['\"]?rank_order['\"]? to ['\"]?desc['\"]?.*$",
            lambda match: f"요청에 따라 상위 {match.group(1)}개를 내림차순으로 선택합니다.",
        ),
        (
            r"^The ['\"]?top_n['\"]? is set to (\d+) and ['\"]?rank_order['\"]? to ['\"]?asc['\"]?.*$",
            lambda match: f"요청에 따라 상위 {match.group(1)}개를 오름차순으로 선택합니다.",
        ),
        (
            r"^Get production data for ranking top products\.?$",
            lambda match: "상위 제품 순위를 계산하기 위한 생산 데이터를 조회합니다.",
        ),
        (
            r"^Get equipment status data for counting equipment for top products\.?$",
            lambda match: "상위 제품별 장비 대수를 계산하기 위한 장비 현황 데이터를 조회합니다.",
        ),
        (
            r"^Filter production data for ([A-Za-z0-9_/]+) process operations\.?$",
            lambda match: f"{match.group(1)} 공정에 해당하는 생산 데이터만 필터링합니다.",
        ),
        (
            r"^Group production data by product grain and sum production to identify top products, then rank and select top (\d+)\.?$",
            lambda match: f"제품 기준으로 생산량을 합산한 뒤 생산량 기준 상위 {match.group(1)}개 제품을 선택합니다.",
        ),
        (
            r"^Rename columns in equipment data to match product grain for joining\.?$",
            lambda match: "장비 데이터를 제품 기준으로 조인할 수 있도록 컬럼명을 맞춥니다.",
        ),
        (
            r"^Filter equipment data to include only the top (\d+) products identified\.?$",
            lambda match: f"선정된 상위 {match.group(1)}개 제품에 해당하는 장비 데이터만 남깁니다.",
        ),
        (
            r"^Group filtered equipment data by product grain and count unique equipment IDs to get the equipment count for each product\.?$",
            lambda match: "필터링된 장비 데이터를 제품 기준으로 그룹화하고 고유 장비 ID를 세어 제품별 장비 대수를 계산합니다.",
        ),
        (
            r"^Left join the top products with their total production and the corresponding equipment counts\.?$",
            lambda match: "상위 제품별 생산량 결과에 제품별 장비 대수를 left join합니다.",
        ),
        (
            r"^Fill any missing equipment counts with 0 and ensure the final output columns match the plan\.?$",
            lambda match: "장비 대수가 없는 경우 0으로 채우고 최종 출력 컬럼을 분석 계획에 맞춥니다.",
        ),
        (
            r"^Filter the '([^']+)' DataFrame to include only rows where '([^']+)' is in (.+)\.?$",
            lambda match: f"`{match.group(1)}` 데이터프레임에서 `{match.group(2)}` 값이 {match.group(3)}에 포함되는 행만 필터링합니다.",
        ),
        (
            r"^Filter the (.+?) data to include only (.+)\.?$",
            lambda match: f"{match.group(1)} 데이터에서 {match.group(2)} 조건에 맞는 행만 필터링합니다.",
        ),
        (
            r"^Group the filtered DataFrame by (.+?) and sum the '([^']+)' .*$",
            lambda match: f"필터링된 데이터프레임을 {match.group(1)} 기준으로 그룹화하고 `{match.group(2)}` 값을 합산합니다.",
        ),
        (
            r"^Aggregate (.+?) data by '([^']+)' and sum '([^']+)'.*$",
            lambda match: f"{match.group(1)} 데이터를 `{match.group(2)}` 기준으로 집계하고 `{match.group(3)}` 값을 합산합니다.",
        ),
        (
            r"^Sort the (.+?) by '([^']+)' in descending order.*$",
            lambda match: f"{match.group(1)}을 `{match.group(2)}` 기준 내림차순으로 정렬합니다.",
        ),
        (
            r"^Rank the (.+?) by '([^']+)' in descending order and select the top (\d+) .*$",
            lambda match: f"{match.group(1)}을 `{match.group(2)}` 기준 내림차순으로 순위화하고 상위 {match.group(3)}개를 선택합니다.",
        ),
        (
            r"^Select the top (\d+) .*$",
            lambda match: f"정렬된 결과에서 상위 {match.group(1)}개를 선택합니다.",
        ),
        (
            r"^Rename '([^']+)' to '([^']+)'.*$",
            lambda match: f"`{match.group(1)}` 컬럼명을 `{match.group(2)}`로 변경합니다.",
        ),
        (
            r"^Group the filtered lot status data by '([^']+)' and calculate (.+)\.?$",
            lambda match: f"필터링된 lot status 데이터를 `{match.group(1)}` 기준으로 그룹화하고 {match.group(2)} 값을 계산합니다.",
        ),
        (
            r"^Perform a left join between (.+?) and (.+?) using '([^']+)' as the key.*$",
            lambda match: f"`{match.group(3)}` 키를 사용해 {match.group(1)}와 {match.group(2)}를 left join합니다.",
        ),
        (
            r"^Assign the final (.+?) DataFrame to 'result_df'.*$",
            lambda match: f"최종 {match.group(1)} 데이터프레임을 `result_df`로 지정합니다.",
        ),
        (
            r"^Create an empty DataFrame.*$",
            lambda match: "빈 데이터프레임을 생성합니다.",
        ),
    ]
    for pattern, builder in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return builder(match)

    action_prefixes = {
        "filter": "필터링",
        "group": "그룹화",
        "aggregate": "집계",
        "sort": "정렬",
        "rank": "순위 계산",
        "select": "선택",
        "calculate": "계산",
        "sum": "합산",
        "count": "개수 계산",
        "join": "조인",
        "merge": "병합",
        "rename": "컬럼명 변경",
        "create": "생성",
        "assign": "최종 결과 지정",
    }
    first_word = text.split(" ", 1)[0].lower().rstrip(":")
    if first_word in action_prefixes:
        return f"{action_prefixes[first_word]} 단계입니다."
    return text


def _contains_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text))


def _strip_korean_action_prefix(text: str) -> str:
    prefixes = [
        "필터링",
        "그룹화",
        "컬럼명 변경",
        "정렬",
        "순위 계산",
        "선택",
        "계산",
        "합산",
        "개수 계산",
        "조인",
        "병합",
        "생성",
        "최종 결과 지정",
    ]
    for prefix in prefixes:
        pattern = rf"^{re.escape(prefix)}\s*:\s*(.+)$"
        match = re.match(pattern, text)
        if match:
            return match.group(1).strip()
    return text


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... truncated ..."



# 컴포넌트 설명: 20 Answer Message Adapter
# Langflow 표시 설명: 답변, 결과 테이블, 의도 분석, pandas 코드가 포함된 Playground용 Message를 만듭니다.
class AnswerMessageAdapter(Component):

    display_name = "20 Answer Message Adapter"
    description = "답변, 결과 테이블, 의도 분석, pandas 코드가 포함된 Playground용 Message를 만듭니다."
    inputs = [DataInput(name="payload", display_name="Payload", required=True)]
    outputs = [Output(name="message", display_name="Message", method="build_message")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: 답변, 결과 테이블, 의도 분석, pandas 코드가 포함된 Playground용 Message를 만듭니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_message(self) -> Message:
        return Message(text=build_playground_message(self.payload))
