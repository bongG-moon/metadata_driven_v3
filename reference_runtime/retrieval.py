from __future__ import annotations

from copy import deepcopy
from typing import Any

from .metadata import get_dataset_catalog
from .source_retrievers import retrieve_rows_for_job


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
        selected_rows = _select_columns(filtered_rows, job.get("required_columns"))

        runtime_sources[source_alias] = selected_rows
        source_results.append(
            {
                "job_id": job["job_id"],
                "source_alias": source_alias,
                "dataset_key": dataset_key,
                "source_type": source.get("source_type", catalog.get("source_type", "")),
                "data_ref": f"source://{source.get('source_type', catalog.get('source_type', 'dummy'))}/{dataset_key}/{source_alias}",
                "row_count": len(selected_rows),
                "columns": _columns_for_rows(selected_rows, catalog),
                "preview_rows": deepcopy(selected_rows[:5]),
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


def _select_columns(rows: list[dict[str, Any]], columns: list[str] | None) -> list[dict[str, Any]]:
    if not columns:
        return deepcopy(rows)
    selected = []
    for row in rows:
        selected.append({column: row.get(column) for column in columns if column in row})
    return selected


def _columns_for_rows(rows: list[dict[str, Any]], catalog: dict[str, Any]) -> list[str]:
    if rows:
        return list(rows[0].keys())
    return list(catalog.get("columns", []))


def _applied_column_filters(filters: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    filter_mappings = catalog.get("filter_mappings", {})
    result = []
    for condition in filters:
        field = condition.get("field")
        if field == "PRODUCT_GRAIN":
            continue
        result.append({**condition, "columns": filter_mappings.get(field, [field])})
    return result
