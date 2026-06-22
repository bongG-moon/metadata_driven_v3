from __future__ import annotations

from copy import deepcopy
from typing import Any

from .metadata import get_dataset_catalog
from .source_retrievers import retrieve_rows_for_job

STANDARDIZED_ANALYSIS_FIELDS = {
    "DATE",
    "TECH",
    "DEN",
    "MODE",
    "PKG_TYPE1",
    "PKG_TYPE2",
    "LEAD",
    "MCP_NO",
    "OPER_NUM",
    "OPER_SEQ",
    "TSV_DIE_TYP",
    "DEVICE",
    "DEVICE_DESC",
}


def execute_retrieval_jobs(
    retrieval_jobs: list[dict[str, Any]],
    metadata: dict[str, Any],
    root: str | None = None,
) -> dict[str, Any]:
    source_results: list[dict[str, Any]] = []
    runtime_sources: dict[str, list[dict[str, Any]]] = {}

    for job in retrieval_jobs:
        dataset_key = job["dataset_key"]
        source_alias = job["source_alias"]
        catalog = get_dataset_catalog(metadata, dataset_key)
        source = retrieve_rows_for_job(job, catalog)
        rows = source.get("rows", [])
        filtered_rows = _apply_params(rows, job.get("params", {}), catalog)
        filtered_rows = _apply_filters(filtered_rows, job.get("filters", []), catalog)
        selected_rows = _select_columns(filtered_rows, job.get("required_columns"), catalog, job)
        analysis_rows = _standardize_rows(selected_rows, catalog, job)

        runtime_sources[source_alias] = analysis_rows
        source_results.append(
            {
                "job_id": job["job_id"],
                "source_alias": source_alias,
                "dataset_key": dataset_key,
                "source_type": source.get("source_type", catalog.get("source_type", "")),
                "data_ref": f"source://{source.get('source_type', catalog.get('source_type', 'dummy'))}/{dataset_key}/{source_alias}",
                "row_count": len(analysis_rows),
                "columns": _columns_for_rows(analysis_rows, catalog),
                "preview_rows": deepcopy(analysis_rows[:5]),
                "applied_params": deepcopy(job.get("params", {})),
                "applied_filters": deepcopy(job.get("filters", [])),
                "applied_column_filters": _applied_column_filters(job.get("filters", []), catalog),
                "used_dummy_data": bool(source.get("used_dummy_data")),
                "source_execution": deepcopy(source.get("source_execution", {})),
                "source_error": source.get("error", ""),
                "purpose": job.get("purpose", ""),
            }
        )

    return {"source_results": source_results, "runtime_sources": runtime_sources}


def _apply_params(rows: list[dict[str, Any]], params: dict[str, Any], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    result = rows
    mappings = catalog.get("required_param_mappings", {})
    for param_name, param_value in params.items():
        columns = mappings.get(param_name) or catalog.get("filter_mappings", {}).get(param_name) or [param_name]
        result = [row for row in result if _row_matches_any_column(row, columns, param_value)]
    return result


def _apply_filters(
    rows: list[dict[str, Any]],
    filters: list[dict[str, Any]],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    result = rows
    filter_mappings = catalog.get("filter_mappings", {})
    for condition in filters:
        op = condition.get("op", "eq")
        field = condition.get("field")
        if field == "PRODUCT_GRAIN":
            continue
        columns = filter_mappings.get(field, [field])
        if op == "eq":
            value = condition.get("value")
            result = [row for row in result if _row_matches_any_column(row, columns, value)]
        elif op == "in":
            values = set(condition.get("values", []))
            result = [row for row in result if any(row.get(column) in values for column in columns)]
        elif op == "not_empty":
            result = [row for row in result if any(row.get(column) not in (None, "") for column in columns)]
    return result


def _row_matches_any_column(row: dict[str, Any], columns: list[str], value: Any) -> bool:
    return any(row.get(column) == value for column in columns)


def _select_columns(
    rows: list[dict[str, Any]],
    columns: list[str] | None,
    catalog: dict[str, Any],
    job: dict[str, Any],
) -> list[dict[str, Any]]:
    if not columns:
        return deepcopy(rows)
    selected = []
    for row in rows:
        item: dict[str, Any] = {}
        for column in columns:
            if column in row:
                item[column] = row.get(column)
                continue
            for candidate in _source_column_candidates(column, catalog, job):
                if candidate in row:
                    item[candidate] = row.get(candidate)
                    break
        selected.append(item)
    return selected


def _source_column_candidates(column: str, catalog: dict[str, Any], job: dict[str, Any]) -> list[str]:
    result = [str(column or "").strip()]
    for source in (catalog, job):
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mappings = source.get(field) if isinstance(source.get(field), dict) else {}
            raw_candidates = mappings.get(column)
            if raw_candidates is None:
                continue
            candidates = raw_candidates if isinstance(raw_candidates, list) else [raw_candidates]
            result.extend(str(candidate) for candidate in candidates if str(candidate or "").strip())
    return _unique(result)


def _standardize_rows(rows: list[dict[str, Any]], catalog: dict[str, Any], job: dict[str, Any]) -> list[dict[str, Any]]:
    alias_map = _standard_aliases(catalog, job)
    if not alias_map:
        return deepcopy(rows)
    standardized = []
    for row in rows:
        item = deepcopy(row)
        for standard, candidates in alias_map.items():
            present_candidates = [candidate for candidate in candidates if candidate in item]
            if not present_candidates:
                continue
            if standard not in item:
                item[standard] = item[present_candidates[0]]
            for candidate in present_candidates:
                if candidate != standard and candidate in item:
                    item.pop(candidate, None)
        standardized.append(item)
    return standardized


def _standard_aliases(catalog: dict[str, Any], job: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for source in (catalog, job):
        for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
            mappings = source.get(field) if isinstance(source.get(field), dict) else {}
            for standard, raw_candidates in mappings.items():
                standard_text = str(standard or "").strip()
                if not standard_text or standard_text not in STANDARDIZED_ANALYSIS_FIELDS:
                    continue
                candidates = raw_candidates if isinstance(raw_candidates, list) else [raw_candidates]
                result.setdefault(standard_text, [])
                result[standard_text].extend(str(candidate) for candidate in candidates if str(candidate or "").strip())
    return {standard: _unique([candidate for candidate in candidates if candidate != standard]) for standard, candidates in result.items()}


def _columns_for_rows(rows: list[dict[str, Any]], catalog: dict[str, Any]) -> list[str]:
    if rows:
        return list(rows[0].keys())
    return list(catalog.get("columns", []))


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _applied_column_filters(filters: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    filter_mappings = catalog.get("filter_mappings", {})
    result = []
    for condition in filters:
        field = condition.get("field")
        if field == "PRODUCT_GRAIN":
            continue
        result.append({**condition, "columns": filter_mappings.get(field, [field])})
    return result
