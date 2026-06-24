# 파일 설명: 03 Intent Plan Normalizer Langflow custom component 파일입니다.
# 흐름 역할: LLM의 의도 분석 JSON을 정규화해 조회 작업, 필터, pandas 분석 계획으로 변환합니다.
# 아래 public 함수와 output 메서드 주석은 Langflow 캔버스에서 노드 역할을 추적하기 쉽게 하기 위한 설명입니다.

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timedelta
from importlib import import_module
from typing import Any

from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, MessageTextInput, Output
from lfx.schema.data import Data

# 함수 설명: 이 컴포넌트의 핵심 실행 함수입니다.
# 처리 역할: LLM의 의도 분석 JSON을 정규화해 조회 작업, 필터, pandas 분석 계획으로 변환합니다.
# Langflow wrapper와 단위 테스트가 같은 로직을 재사용할 수 있도록 순수 dict/string 결과를 만듭니다.
def normalize_intent_payload(payload_value: Any, llm_response_value: Any) -> dict[str, Any]:
    payload = _payload(payload_value)
    if payload.get("direct_response_ready"):
        return payload
    llm_text = _text(llm_response_value)
    llm_json = _extract_json_object(llm_text)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    product_grain = ((metadata.get("domain_items") or {}).get("product_key_columns") or []) if isinstance(metadata, dict) else []

    errors: list[str] = []
    notes: list[str] = []
    if not llm_json:
        errors.append("의도 분석 LLM 응답에서 JSON 객체를 찾지 못했습니다.")
    plan = _base_plan(llm_json, product_grain)
    _attach_state_product_keys(plan, payload)
    plan["llm_intent_json"] = llm_json
    plan["llm_text_preview"] = llm_text[:1200]

    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    request_date = _request_date(payload)
    if _wants_detail_rows(question):
        _prefer_detail_rows(plan, notes)
    recipe_key, recipe = _matching_analysis_recipe(question, metadata, plan)
    if recipe:
        _apply_analysis_recipe(plan, recipe_key, recipe, metadata, question, request_date, notes)
    _repair_metric_grain_plan(plan, metadata, question, notes)
    _repair_quantity_term_plan(plan, metadata, question, notes)
    _repair_product_production_wip_join_plan(plan, metadata, question, request_date, notes)
    _repair_explicit_grain_plan(plan, metadata, question, notes)
    normalized_jobs = []
    raw_jobs = plan.get("retrieval_jobs", [])
    if not raw_jobs and plan.get("intent_type") != "finish":
        raw_jobs = _fallback_retrieval_jobs(plan, llm_json, metadata, payload)
        if raw_jobs:
            notes.append("retrieval_jobs가 없어 LLM이 지정한 datasets, 메타데이터, 요청 문맥을 기준으로 조회 작업을 보완했습니다.")
        else:
            errors.append("retrieval_jobs가 없고 LLM이 지정한 datasets도 없어 조회 작업을 보완할 수 없습니다.")
    raw_jobs = _repair_lot_count_plan(plan, raw_jobs, catalog, question, notes)
    raw_jobs = _repair_followup_equipment_plan(plan, raw_jobs, catalog, question, notes)
    _repair_followup_analysis_kind(plan, raw_jobs, catalog, notes)
    for index, raw_job in enumerate(raw_jobs):
        if not isinstance(raw_job, dict):
            continue
        dataset_key = str(raw_job.get("dataset_key") or "").strip()
        if not dataset_key:
            errors.append(f"retrieval_jobs[{index}]에 dataset_key가 없습니다.")
            continue
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        job = deepcopy(raw_job)
        job.setdefault("job_id", f"job_{index + 1}_{dataset_key}")
        job.setdefault("source_alias", dataset_key)
        params = _params_for_dataset(llm_json, dataset_key)
        if isinstance(job.get("params"), dict):
            params.update(deepcopy(job["params"]))
        original_params = deepcopy(params)
        _fill_required_params(params, dataset_key, dataset_catalog, question, request_date, job)
        job["params"] = params
        original_filters = deepcopy(job.get("filters")) if isinstance(job.get("filters"), list) else []
        job["filters"] = _augmented_filters_for_job(job, plan, metadata, question, request_date)
        if params != original_params or job["filters"] != original_filters:
            _append_once(notes, "메타데이터를 기준으로 조회 params/filters를 보완했습니다.")
        raw_required_columns = job.get("required_columns")
        metric_source_columns = _metric_source_columns_for_dataset(plan, dataset_catalog)
        if metric_source_columns:
            raw_required_columns = _unique(
                [
                    *(raw_required_columns if isinstance(raw_required_columns, list) else []),
                    *metric_source_columns,
                ]
            )
        job["required_columns"] = _normalize_required_columns(
            raw_required_columns,
            dataset_catalog,
            _required_product_grain(plan, dataset_catalog),
            metadata,
        )
        job["source_type"] = dataset_catalog.get("source_type", job.get("source_type", "dummy"))
        if isinstance(dataset_catalog.get("source_config"), dict):
            source_config = deepcopy(dataset_catalog["source_config"])
            if isinstance(job.get("source_config"), dict):
                source_config.update(deepcopy(job["source_config"]))
            job["source_config"] = source_config
        if "required_params" not in job and isinstance(dataset_catalog.get("required_params"), list):
            job["required_params"] = deepcopy(dataset_catalog["required_params"])
        if "required_param_mappings" not in job and isinstance(dataset_catalog.get("required_param_mappings"), dict):
            job["required_param_mappings"] = deepcopy(dataset_catalog["required_param_mappings"])
        if "date_format" not in job and dataset_catalog.get("date_format"):
            job["date_format"] = deepcopy(dataset_catalog["date_format"])
        if "primary_quantity_column" not in job and dataset_catalog.get("primary_quantity_column"):
            job["primary_quantity_column"] = deepcopy(dataset_catalog["primary_quantity_column"])
        _attach_column_standardization_contract(job, dataset_catalog)
        normalized_jobs.append(job)
    plan["retrieval_jobs"] = normalized_jobs
    plan["datasets"] = _unique([job["dataset_key"] for job in normalized_jobs] or llm_json.get("datasets", []))
    if normalized_jobs:
        plan["pandas_preprocessing"] = {
            "standardize_columns": True,
            "source": "retrieval_jobs.filter_mappings/required_param_mappings/standard_column_aliases",
            "note": "Retrievers preserve physical source columns; pandas execution standardizes them to plan column names.",
        }
    _attach_result_scope_columns(plan, normalized_jobs, metadata, question)
    if not plan.get("step_plan"):
        fallback_steps = _fallback_step_plan(plan, metadata, payload)
        if fallback_steps:
            plan["step_plan"] = fallback_steps
            notes.append("step_plan이 없어 조회 alias를 기준으로 기본 분석 단계를 보완했습니다.")
    _normalize_step_plan_columns(plan, normalized_jobs, catalog)
    _augment_step_plan_defaults(plan, normalized_jobs, metadata, payload)
    _normalize_intent_type_for_analysis(plan, normalized_jobs)
    _mark_previous_result_restore_need(plan, payload, question, notes)
    normalized_jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else normalized_jobs
    plan["datasets"] = _unique([job["dataset_key"] for job in normalized_jobs if isinstance(job, dict) and job.get("dataset_key")] or plan.get("datasets", []))
    plan["route"] = _route_for_intent(plan.get("intent_type"), len(normalized_jobs))
    plan["normalizer_errors"] = errors
    plan["normalizer_notes"] = notes

    next_payload = dict(payload)
    next_payload["intent_plan"] = plan
    next_payload["retrieval_jobs"] = normalized_jobs
    next_payload["metadata_context"] = _metadata_context(plan)
    if errors:
        next_payload["warnings"] = list(next_payload.get("warnings", [])) + [f"의도 정규화 오류: {item}" for item in errors]
    if notes:
        next_payload["info"] = list(next_payload.get("info", [])) + [f"의도 정규화: {item}" for item in notes]
    return next_payload


def _base_plan(llm_json: dict[str, Any], product_grain: list[str]) -> dict[str, Any]:
    intent_type = str(llm_json.get("intent_type") or "single_retrieval_analysis").strip()
    analysis_kind = str(llm_json.get("analysis_kind") or "none").strip()
    step_plan = llm_json.get("step_plan") if isinstance(llm_json.get("step_plan"), list) else []
    retrieval_jobs = llm_json.get("retrieval_jobs") if isinstance(llm_json.get("retrieval_jobs"), list) else []
    product_grain_value = _normalized_product_grain(llm_json, product_grain)
    plan = {
        "intent_type": intent_type,
        "analysis_kind": analysis_kind,
        "product_grain": product_grain_value,
        "datasets": _unique(llm_json.get("datasets", [])),
        "params_by_dataset": llm_json.get("params_by_dataset", {}) if isinstance(llm_json.get("params_by_dataset"), dict) else {},
        "filters": llm_json.get("filters", []) if isinstance(llm_json.get("filters"), list) else [],
        "retrieval_jobs": retrieval_jobs,
        "step_plan": step_plan,
        "depends_on_state": bool(llm_json.get("depends_on_state", False)),
        "reasoning_steps": llm_json.get("reasoning_steps", []) if isinstance(llm_json.get("reasoning_steps"), list) else [],
    }
    for key in (
        "analysis_output_shape",
        "rank_groups",
        "scope_label",
        "state_product_keys",
        "target_column",
        "metric",
        "rank_order",
        "analysis_output_columns",
        "threshold",
        "threshold_percent",
        "top_n",
        "bottom_n",
        "requires_full_previous_result_restore",
        "previous_result_restore_mode",
    ):
        if key in llm_json:
            plan[key] = deepcopy(llm_json[key])
    _absorb_loose_llm_fields(plan, llm_json)
    return plan


def _normalized_product_grain(llm_json: dict[str, Any], default_product_grain: list[str]) -> list[str]:
    if isinstance(llm_json.get("product_grain"), list):
        return _unique(llm_json["product_grain"])
    if "group_by" in llm_json and isinstance(llm_json.get("group_by"), list):
        return _unique(llm_json["group_by"])
    return _unique(default_product_grain)


def _absorb_loose_llm_fields(plan: dict[str, Any], llm_json: dict[str, Any]) -> None:
    rank = llm_json.get("rank") if isinstance(llm_json.get("rank"), dict) else {}
    if rank:
        if not plan.get("metric"):
            for key in ("metric", "rank_column", "quantity_column"):
                value = rank.get(key)
                if isinstance(value, str) and value.strip():
                    plan["metric"] = value.strip()
                    break
        if "top_n" not in plan and rank.get("top_n") not in (None, "", [], {}):
            plan["top_n"] = deepcopy(rank["top_n"])
        if "bottom_n" not in plan and rank.get("bottom_n") not in (None, "", [], {}):
            plan["bottom_n"] = deepcopy(rank["bottom_n"])
        if not plan.get("rank_order"):
            order = _canonical_rank_order(rank.get("sort_order") or rank.get("order") or rank.get("rank_order"))
            if order:
                plan["rank_order"] = order
    if "group_by" in llm_json and isinstance(llm_json.get("group_by"), list) and not isinstance(llm_json.get("product_grain"), list):
        plan["product_grain"] = _unique(llm_json["group_by"])
    if "analysis_output_columns" not in plan and isinstance(llm_json.get("output_columns"), list):
        plan["analysis_output_columns"] = _unique(llm_json["output_columns"])


def _canonical_rank_order(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"desc", "descending", "top", "highest", "most", "max", "maximum"}:
        return "desc"
    if text in {"asc", "ascending", "bottom", "lowest", "least", "min", "minimum"}:
        return "asc"
    return ""


def _wants_detail_rows(question: str) -> bool:
    text = str(question or "").strip()
    lower = text.lower()
    no_aggregation_terms = [
        "집계하지 말고",
        "집계 없이",
        "합산하지 말고",
        "합산 없이",
        "그룹핑하지 말고",
        "그룹화하지 말고",
        "groupby 없이",
        "group by 없이",
        "without aggregation",
        "without groupby",
        "without group by",
    ]
    if _mentions_any(text, no_aggregation_terms):
        return True
    detail_patterns = [
        r"(상세|세부|원본)\s*(데이터|자료|row|rows|로우|레코드)",
        r"(전체|모든)\s*(row|rows|로우|레코드)",
        r"(raw|detail)\s*(data|rows?|records?)",
    ]
    return any(re.search(pattern, lower, re.IGNORECASE) for pattern in detail_patterns)


def _prefer_detail_rows(plan: dict[str, Any], notes: list[str]) -> None:
    plan["detail_rows_requested"] = True
    if str(plan.get("analysis_kind") or "") != "detail_rows":
        plan["original_analysis_kind"] = plan.get("analysis_kind")
        plan["analysis_kind"] = "detail_rows"
    if str(plan.get("intent_type") or "") not in {"finish", "followup_transform"}:
        plan["intent_type"] = "detail_lookup"
    plan["product_grain"] = []
    step_plan = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    if step_plan and not any(_is_detail_step(step) for step in step_plan):
        plan["step_plan"] = []
        _append_once(notes, "상세 row 요청이므로 recipe 집계 대신 원본 row를 유지하도록 조정했습니다.")


def _is_detail_step(step: Any) -> bool:
    if not isinstance(step, dict):
        return False
    return str(step.get("operation") or step.get("step_id") or "") == "detail_rows"


def _params_for_dataset(llm_json: dict[str, Any], dataset_key: str) -> dict[str, Any]:
    params_by_dataset = llm_json.get("params_by_dataset")
    if isinstance(params_by_dataset, dict) and isinstance(params_by_dataset.get(dataset_key), dict):
        return deepcopy(params_by_dataset[dataset_key])
    return {}


def _matching_analysis_recipe(question: str, metadata: dict[str, Any], plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    recipes = domain.get("analysis_recipes") if isinstance(domain.get("analysis_recipes"), dict) else {}
    best_key = ""
    best_recipe: dict[str, Any] = {}
    best_score = 0
    for recipe_key, recipe in recipes.items():
        if not isinstance(recipe, dict):
            continue
        forbidden = recipe.get("forbidden_question_cues") if isinstance(recipe.get("forbidden_question_cues"), list) else []
        if forbidden and _mentions_any(question, forbidden):
            continue
        required = recipe.get("required_question_cues") if isinstance(recipe.get("required_question_cues"), list) else []
        if required and not _required_question_cues_match(question, required):
            continue
        score = _recipe_match_score(str(recipe_key), recipe, question, metadata, plan)
        if score > best_score:
            best_key = str(recipe_key)
            best_recipe = recipe
            best_score = score
    return (best_key, best_recipe) if best_score >= 3 else ("", {})


def _recipe_match_score(
    recipe_key: str,
    recipe: dict[str, Any],
    question: str,
    metadata: dict[str, Any],
    plan: dict[str, Any],
) -> int:
    score = 0
    default_kind = str(recipe.get("default_analysis_kind") or recipe_key)
    if default_kind and str(plan.get("analysis_kind") or "") == default_kind:
        score += 5
    aliases = recipe.get("aliases") if isinstance(recipe.get("aliases"), list) else []
    if _mentions_any(question, [recipe_key, recipe.get("display_name"), *aliases]):
        score += 4
    cues = recipe.get("question_cues") if isinstance(recipe.get("question_cues"), list) else []
    matched_cues = [cue for cue in cues if _alias_in_text(question, cue)]
    score += len(matched_cues)
    if cues and len(matched_cues) == len(cues):
        score += 2
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    metric_terms = domain.get("metric_terms") if isinstance(domain.get("metric_terms"), dict) else {}
    recipe_metric_terms = recipe.get("metric_terms") if isinstance(recipe.get("metric_terms"), list) else []
    for metric_key in recipe_metric_terms:
        metric = metric_terms.get(metric_key) if isinstance(metric_terms.get(metric_key), dict) else {}
        metric_aliases = metric.get("aliases") if isinstance(metric.get("aliases"), list) else []
        if _mentions_any(question, [metric_key, metric.get("display_name"), *metric_aliases]):
            score += 3
    return score


def _repair_metric_grain_plan(
    plan: dict[str, Any],
    metadata: dict[str, Any],
    question: str,
    notes: list[str],
) -> None:
    matched_terms = _matched_metric_terms(question, metadata, plan)
    if matched_terms:
        plan["matched_metric_terms"] = matched_terms
        plan["metric_definitions"] = matched_terms
    output_columns = _metric_output_columns(plan, matched_terms)
    if matched_terms and output_columns:
        group_by = _explicit_grain_from_question(question, metadata)
        if group_by is None:
            group_by = [] if _metric_question_defaults_to_total(question) else plan.get("product_grain", [])
        group_by = _unique(group_by)
        plan["analysis_output_columns"] = _unique([*group_by, *output_columns])
        if str(plan.get("analysis_kind") or "") == "detail_rows" and not bool(plan.get("detail_rows_requested")):
            source_alias = _primary_planned_source_alias(plan)
            plan["original_analysis_kind"] = plan.get("analysis_kind")
            plan["analysis_kind"] = "generic_aggregate_recipe"
            if str(plan.get("intent_type") or "") not in {"finish", "followup_transform"}:
                plan["intent_type"] = "single_retrieval_analysis"
            plan["product_grain"] = group_by
            plan["step_plan"] = [
                {
                    "step_id": "aggregate_metric_outputs",
                    "operation": "aggregate_sum_by_group",
                    "source_alias": source_alias,
                    "group_by": group_by,
                    "metrics": output_columns,
                    "aggregation": "sum",
                    "output_columns": [*group_by, *output_columns],
                }
            ]
            plan["metric_grain_policy"] = "question_grain_or_total"
            _append_once(notes, "명시적 원본/상세 데이터 요청이 아니므로 metric detail_rows 계획을 요청 grain 기준 집계로 보정했습니다.")


def _repair_quantity_term_plan(
    plan: dict[str, Any],
    metadata: dict[str, Any],
    question: str,
    notes: list[str],
) -> None:
    if plan.get("matched_analysis_recipe"):
        return
    matched_terms = _matched_quantity_terms(question, metadata, plan)
    if not matched_terms:
        return
    plan["matched_quantity_terms"] = matched_terms
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    for term in matched_terms:
        aggregation = str(term.get("aggregation") or "").strip().lower()
        source_column = str(term.get("quantity_column") or "").strip()
        output_column = str(term.get("output_column") or source_column).strip()
        if aggregation != "nunique" or not source_column or not output_column:
            continue
        if str(plan.get("analysis_kind") or "") in {"equipment_by_model"}:
            continue
        dataset_key = _quantity_term_dataset_key(term, catalog, question)
        if not dataset_key:
            continue
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        source_alias = _ensure_quantity_term_job(plan, dataset_key, dataset_catalog, catalog, source_column)
        if not source_alias:
            continue
        group_by = _explicit_grain_from_question(question, metadata)
        if group_by is None:
            group_by = [] if _metric_question_defaults_to_total(question) else plan.get("product_grain", [])
        group_by = _unique(group_by)
        plan["analysis_kind"] = "unique_count_by_group"
        if str(plan.get("intent_type") or "") not in {"finish", "followup_transform"}:
            plan["intent_type"] = "single_retrieval_analysis"
        plan["datasets"] = _unique([dataset_key, *(plan.get("datasets") if isinstance(plan.get("datasets"), list) else [])])
        plan["analysis_output_columns"] = _unique([*group_by, output_column])
        plan["step_plan"] = [
            {
                "step_id": f"count_{term.get('key') or output_column}",
                "operation": "unique_count_by_group",
                "source_alias": source_alias,
                "group_by": group_by,
                "count_column": source_column,
                "output_column": output_column,
                "output_columns": [*group_by, output_column],
            }
        ]
        _append_once(notes, "quantity_terms metadata converted a distinct-count request into a unique_count_by_group plan.")
        return


def _matched_quantity_terms(question: str, metadata: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    quantity_terms = domain.get("quantity_terms") if isinstance(domain.get("quantity_terms"), dict) else {}
    if not quantity_terms:
        return []
    plan_text_parts: list[str] = [
        str(plan.get("metric") or ""),
        str(plan.get("target_column") or ""),
        " ".join(str(item) for item in plan.get("analysis_output_columns", []) if str(item or "").strip())
        if isinstance(plan.get("analysis_output_columns"), list)
        else "",
    ]
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if not isinstance(step, dict):
            continue
        plan_text_parts.extend(
            [
                str(step.get("metric") or ""),
                str(step.get("count_column") or ""),
                str(step.get("output_column") or ""),
                " ".join(str(item) for item in step.get("output_columns", []) if str(item or "").strip())
                if isinstance(step.get("output_columns"), list)
                else "",
            ]
        )
    plan_text = " ".join(plan_text_parts)
    matched: list[dict[str, Any]] = []
    for quantity_key, term in quantity_terms.items():
        if not isinstance(term, dict):
            continue
        aliases = term.get("aliases") if isinstance(term.get("aliases"), list) else []
        output_column = str(term.get("output_column") or "").strip()
        quantity_column = str(term.get("quantity_column") or "").strip()
        match_values = [quantity_key, term.get("display_name"), *aliases, output_column]
        if not (_mentions_any(question, match_values) or _mentions_any(plan_text, match_values)):
            continue
        matched.append(
            {
                "key": str(quantity_key),
                "display_name": term.get("display_name", ""),
                "aliases": deepcopy(aliases),
                "dataset_key": term.get("dataset_key"),
                "dataset_family": term.get("dataset_family"),
                "quantity_column": quantity_column,
                "aggregation": term.get("aggregation"),
                "output_column": output_column,
                "condition": deepcopy(term.get("condition", {})) if isinstance(term.get("condition"), dict) else {},
            }
        )
    return matched


def _quantity_term_dataset_key(term: dict[str, Any], catalog: dict[str, Any], question: str) -> str:
    dataset_key = str(term.get("dataset_key") or "").strip()
    if dataset_key and isinstance(catalog.get(dataset_key), dict):
        return dataset_key
    family = str(term.get("dataset_family") or "").strip()
    if family:
        return _dataset_for_family(family, catalog, question)
    return ""


def _ensure_quantity_term_job(
    plan: dict[str, Any],
    dataset_key: str,
    dataset_catalog: dict[str, Any],
    catalog: dict[str, Any],
    source_column: str,
) -> str:
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    family = str(dataset_catalog.get("dataset_family") or "")
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_key = str(job.get("dataset_key") or "").strip()
        if job_key == dataset_key:
            alias = str(job.get("source_alias") or dataset_key).strip()
            job["source_alias"] = alias
            required_columns = job.get("required_columns") if isinstance(job.get("required_columns"), list) else []
            job["required_columns"] = _unique([*_source_required_columns(required_columns, dataset_catalog), source_column])
            return alias
        job_catalog = catalog.get(job_key) if isinstance(catalog.get(job_key), dict) else {}
        job_family = str(job_catalog.get("dataset_family") or "")
        if family and job_family == family:
            # Keep an existing job for the same metadata family but align it to the matched term dataset.
            job["dataset_key"] = dataset_key
            alias = str(job.get("source_alias") or dataset_key).strip()
            job["source_alias"] = alias
            required_columns = job.get("required_columns") if isinstance(job.get("required_columns"), list) else []
            job["required_columns"] = _unique([*_source_required_columns(required_columns, dataset_catalog), source_column])
            return alias
    alias = dataset_key
    jobs.append(
        {
            "dataset_key": dataset_key,
            "source_alias": alias,
            "required_columns": [source_column],
            "filters": [],
            "params": {},
            "purpose": "quantity_term_unique_count",
        }
    )
    plan["retrieval_jobs"] = jobs
    return alias


def _source_required_columns(columns: list[Any], dataset_catalog: dict[str, Any]) -> list[str]:
    catalog_columns = set(str(item) for item in _unique(dataset_catalog.get("columns", [])) if str(item or "").strip())
    mapped_columns: set[str] = set()
    for field in ("filter_mappings", "standard_column_aliases", "required_param_mappings"):
        mapping = dataset_catalog.get(field) if isinstance(dataset_catalog.get(field), dict) else {}
        for value in mapping.values():
            candidates = value if isinstance(value, list) else [value]
            mapped_columns.update(str(item) for item in candidates if str(item or "").strip())
    result: list[str] = []
    for column in columns:
        text = str(column or "").strip()
        if not text:
            continue
        if text in catalog_columns or text in mapped_columns:
            result.append(text)
    return _unique(result)


def _repair_product_production_wip_join_plan(
    plan: dict[str, Any],
    metadata: dict[str, Any],
    question: str,
    request_date: str,
    notes: list[str],
) -> None:
    if not _product_production_wip_join_requested(question):
        return
    process_values = _metadata_process_values(question, metadata)
    if not process_values:
        return
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    use_history = _mentions_any(question, ["어제", "전일", "yesterday", "history"]) and not _mentions_any(question, ["오늘", "현재", "금일", "today", "current"])
    production_key = "production" if use_history and "production" in catalog else "production_today"
    wip_key = "wip" if use_history and "wip" in catalog else "wip_today"
    if production_key not in catalog or wip_key not in catalog:
        return
    date_value = _shift_date(request_date, -1) if use_history else request_date
    product_grain = _unique(plan.get("product_grain", []))
    if not product_grain:
        domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
        product_grain = _unique(domain.get("product_key_columns", []))
    filters = [{"field": "OPER_NAME", "op": "in", "values": process_values}]
    plan["original_analysis_kind"] = plan.get("analysis_kind")
    plan["intent_type"] = "multi_source_analysis"
    plan["analysis_kind"] = "aggregate_join"
    plan["datasets"] = [production_key, wip_key]
    plan["product_grain"] = product_grain
    plan["requested_measures"] = [
        {"metric": "PRODUCTION", "dataset_key": production_key, "aggregation": "sum"},
        {"metric": "WIP", "dataset_key": wip_key, "aggregation": "sum"},
    ]
    plan["analysis_output_columns"] = [*product_grain, "PRODUCTION", "WIP"]
    plan["retrieval_jobs"] = [
        {
            "job_id": f"job_{production_key}_product_production_wip",
            "dataset_key": production_key,
            "source_alias": "production_data",
            "purpose": "제품별 생산량 집계를 위한 생산 데이터 조회",
            "params": {"DATE": _date_param(production_key, date_value, catalog.get(production_key, {}))},
            "filters": deepcopy(filters),
            "required_columns": ["DATE", "OPER_NAME", *product_grain, "PRODUCTION"],
        },
        {
            "job_id": f"job_{wip_key}_product_production_wip",
            "dataset_key": wip_key,
            "source_alias": "wip_data",
            "purpose": "제품별 재공 집계를 위한 WIP 데이터 조회",
            "params": {"DATE": _date_param(wip_key, date_value, catalog.get(wip_key, {}))},
            "filters": deepcopy(filters),
            "required_columns": ["DATE", "OPER_NAME", *product_grain, "WIP"],
        },
    ]
    plan["step_plan"] = [
        {
            "step_id": "aggregate_production_by_product",
            "operation": "aggregate_sum_by_group",
            "source_alias": "production_data",
            "group_by": product_grain,
            "metrics": ["PRODUCTION"],
            "aggregation": "sum",
            "output_columns": [*product_grain, "PRODUCTION"],
        },
        {
            "step_id": "aggregate_wip_by_product",
            "operation": "aggregate_sum_by_group",
            "source_alias": "wip_data",
            "group_by": product_grain,
            "metrics": ["WIP"],
            "aggregation": "sum",
            "output_columns": [*product_grain, "WIP"],
        },
        {
            "step_id": "join_production_and_wip_by_product",
            "operation": "left_join",
            "left_step": "aggregate_production_by_product",
            "right_step": "aggregate_wip_by_product",
            "join_keys": product_grain,
            "output_columns": [*product_grain, "PRODUCTION", "WIP"],
        },
    ]
    _append_once(notes, "생산량과 재공을 제품별로 함께 묻는 공정 범위 질문을 production/wip 제품 grain 조인 계획으로 보정했습니다.")


def _product_production_wip_join_requested(question: str) -> bool:
    text = str(question or "")
    if not (_mentions_any(text, ["재공", "wip"]) and _mentions_any(text, ["생산", "생산량", "실적", "production"])):
        return False
    if not _mentions_any(text, ["제품별", "제품", "product"]):
        return False
    if _mentions_any(text, ["목표", "계획", "달성", "target", "plan"]):
        return False
    if _mentions_any(text, ["상위", "하위", "top", "rank", "랭크", "랭킹", "가장", "많은", "적은", "최대", "최소"]):
        return False
    return True


def _matched_metric_terms(question: str, metadata: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    metric_terms = domain.get("metric_terms") if isinstance(domain.get("metric_terms"), dict) else {}
    if not metric_terms:
        return []
    plan_text_parts: list[str] = [
        str(plan.get("metric") or ""),
        " ".join(str(item) for item in plan.get("analysis_output_columns", []) if str(item or "").strip())
        if isinstance(plan.get("analysis_output_columns"), list)
        else "",
    ]
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if not isinstance(step, dict):
            continue
        plan_text_parts.extend(
            [
                str(step.get("metric") or ""),
                " ".join(str(item) for item in step.get("metrics", []) if str(item or "").strip())
                if isinstance(step.get("metrics"), list)
                else "",
                " ".join(str(item) for item in step.get("output_columns", []) if str(item or "").strip())
                if isinstance(step.get("output_columns"), list)
                else "",
            ]
        )
    plan_text = " ".join(plan_text_parts)
    matched: list[dict[str, Any]] = []
    for metric_key, metric in metric_terms.items():
        if not isinstance(metric, dict):
            continue
        aliases = metric.get("aliases") if isinstance(metric.get("aliases"), list) else []
        output_columns = _unique(metric.get("output_columns", [])) if isinstance(metric.get("output_columns"), list) else []
        match_values = [metric_key, metric.get("display_name"), *aliases, *output_columns]
        if not (_mentions_any(question, match_values) or _mentions_any(plan_text, match_values)):
            continue
        matched.append(
            {
                "key": str(metric_key),
                "display_name": metric.get("display_name", ""),
                "aliases": deepcopy(aliases),
                "dataset_family": metric.get("dataset_family"),
                "required_dataset_families": deepcopy(metric.get("required_dataset_families", [])),
                "required_quantity_terms": deepcopy(metric.get("required_quantity_terms", [])),
                "source_columns": deepcopy(metric.get("source_columns", [])),
                "output_columns": deepcopy(output_columns),
                "formula": metric.get("formula", ""),
                "calculation_rule": metric.get("calculation_rule", ""),
                "zero_division_rule": metric.get("zero_division_rule", ""),
                "pandas_code_instructions": metric.get("pandas_code_instructions", ""),
            }
        )
    return matched


def _metric_output_columns(plan: dict[str, Any], matched_terms: list[dict[str, Any]]) -> list[str]:
    output_columns: list[str] = []
    for term in matched_terms:
        if isinstance(term.get("output_columns"), list):
            output_columns.extend(str(item) for item in term["output_columns"] if str(item or "").strip())
    if isinstance(plan.get("analysis_output_columns"), list):
        output_columns.extend(str(item) for item in plan["analysis_output_columns"] if str(item or "").strip())
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if not isinstance(step, dict):
            continue
        if isinstance(step.get("output_columns"), list):
            output_columns.extend(str(item) for item in step["output_columns"] if str(item or "").strip())
        for key in ("metric", "value_column", "measure_column", "quantity_column"):
            value = str(step.get(key) or "").strip()
            if value:
                output_columns.append(value)
        if isinstance(step.get("metrics"), list):
            output_columns.extend(str(item) for item in step["metrics"] if str(item or "").strip())
    excluded = set(_product_grain_columns_from_plan(plan))
    excluded.update({"DATE", "WORK_DT", "BASE_DT", "OPER_NAME", "OPER_NUM", "OPER_SEQ", "OPER_SHORT_DESC"})
    return _unique([column for column in output_columns if column not in excluded])


def _metric_source_columns_for_dataset(plan: dict[str, Any], dataset_catalog: dict[str, Any]) -> list[str]:
    terms = plan.get("matched_metric_terms") if isinstance(plan.get("matched_metric_terms"), list) else []
    if not terms:
        return []
    family = str(dataset_catalog.get("dataset_family") or "")
    result: list[str] = []
    for term in terms:
        if not isinstance(term, dict):
            continue
        term_family = str(term.get("dataset_family") or "")
        required_families = [str(item) for item in term.get("required_dataset_families", [])] if isinstance(term.get("required_dataset_families"), list) else []
        if family and (term_family == family or family in required_families or not term_family and not required_families):
            result.extend(str(item) for item in term.get("source_columns", []) if str(item or "").strip())
    return _unique(result)


def _product_grain_columns_from_plan(plan: dict[str, Any]) -> list[str]:
    result: list[str] = []
    if isinstance(plan.get("product_grain"), list):
        result.extend(str(item) for item in plan["product_grain"] if str(item or "").strip())
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if isinstance(step, dict) and isinstance(step.get("group_by"), list):
            result.extend(str(item) for item in step["group_by"] if str(item or "").strip())
    return _unique(result)


def _metric_question_defaults_to_total(question: str) -> bool:
    text = str(question or "")
    if _wants_detail_rows(text):
        return False
    if _explicit_grain_from_question(text, {}) is not None:
        return False
    return not _mentions_any(text, ["별", "별로", "per ", " by ", "rank", "top", "상위", "하위", "가장"])


def _primary_planned_source_alias(plan: dict[str, Any]) -> str:
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if isinstance(step, dict) and str(step.get("source_alias") or "").strip():
            return str(step["source_alias"]).strip()
    for job in plan.get("retrieval_jobs", []) if isinstance(plan.get("retrieval_jobs"), list) else []:
        if isinstance(job, dict):
            alias = str(job.get("source_alias") or job.get("dataset_key") or "").strip()
            if alias:
                return alias
    datasets = plan.get("datasets") if isinstance(plan.get("datasets"), list) else []
    return str(datasets[0]) if datasets else ""


def _required_question_cues_match(question: str, required_cues: list[Any]) -> bool:
    for cue in required_cues:
        if isinstance(cue, list):
            if not _mentions_any(question, cue):
                return False
            continue
        if isinstance(cue, dict):
            aliases = cue.get("any")
            if isinstance(aliases, list) and aliases:
                if not _mentions_any(question, aliases):
                    return False
                continue
            aliases = cue.get("all")
            if isinstance(aliases, list) and aliases:
                if not all(_alias_in_text(question, alias) for alias in aliases):
                    return False
                continue
        if not _alias_in_text(question, cue):
            return False
    return True


def _apply_analysis_recipe(
    plan: dict[str, Any],
    recipe_key: str,
    recipe: dict[str, Any],
    metadata: dict[str, Any],
    question: str,
    request_date: str,
    notes: list[str],
) -> None:
    default_kind = str(recipe.get("default_analysis_kind") or recipe_key).strip()
    current_kind = str(plan.get("analysis_kind") or "none")
    detail_requested = bool(plan.get("detail_rows_requested"))
    override_kinds = _as_recipe_text_list(recipe.get("override_analysis_kinds"))
    force_kind = bool(recipe.get("force_analysis_kind"))
    if not detail_requested and default_kind and (
        force_kind
        or current_kind in override_kinds
        or current_kind in {"", "none", "aggregate", "aggregate_join", "generic_analysis"}
    ):
        plan["analysis_kind"] = default_kind
    if not detail_requested and default_kind and (not plan.get("datasets") or not plan.get("retrieval_jobs")):
        plan["analysis_kind"] = default_kind
    intent_type = str(recipe.get("intent_type") or "").strip()
    if not detail_requested and intent_type and str(plan.get("intent_type") or "") not in {"finish", "followup_transform"}:
        plan["intent_type"] = intent_type
    plan["matched_analysis_recipe"] = recipe_key
    plan["recipe_grain_policy"] = recipe.get("grain_policy", "")
    plan["product_grain"] = [] if detail_requested else _resolve_recipe_grain(question, recipe, metadata, plan)
    if not detail_requested:
        _apply_recipe_defaults(plan, recipe, question)
        _apply_recipe_filter_policy(plan, recipe)

    selected = _recipe_datasets(recipe, metadata, question)
    replace_retrieval_jobs = bool(recipe.get("replace_retrieval_jobs")) and not detail_requested
    if selected:
        selected_datasets = [item["dataset_key"] for item in selected]
        if replace_retrieval_jobs or bool(recipe.get("replace_datasets")):
            plan["datasets"] = _unique(selected_datasets)
        else:
            existing_datasets = _unique(plan.get("datasets", []))
            plan["datasets"] = _unique([*existing_datasets, *selected_datasets])
    existing_jobs = [] if replace_retrieval_jobs else plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    _align_existing_jobs_to_recipe_families(plan, existing_jobs, selected, metadata, recipe_key, recipe, notes)
    existing_dataset_keys = {str(job.get("dataset_key") or "") for job in existing_jobs if isinstance(job, dict)}
    jobs_to_add = []
    for item in selected:
        dataset_key = item["dataset_key"]
        if dataset_key in existing_dataset_keys:
            continue
        dataset_catalog = item["catalog"]
        alias = _recipe_source_alias(recipe, item["family"], dataset_key, len(existing_jobs) + len(jobs_to_add))
        jobs_to_add.append(
            {
                "job_id": f"recipe_{recipe_key}_{dataset_key}",
                "dataset_key": dataset_key,
                "source_alias": alias,
                "purpose": f"recipe:{recipe_key}:{item['family']}",
                "params": {},
                "filters": [],
                "required_columns": _recipe_required_columns(plan, recipe, item["family"], dataset_catalog),
            }
        )
    if jobs_to_add or replace_retrieval_jobs:
        plan["retrieval_jobs"] = [*existing_jobs, *jobs_to_add]
    if not detail_requested and (not plan.get("step_plan") or bool(recipe.get("override_step_plan"))):
        steps = _recipe_step_plan(plan, recipe_key, recipe, question)
        if steps:
            plan["step_plan"] = steps
    if selected or jobs_to_add:
        _append_once(notes, f"분석 recipe '{recipe_key}' 기준으로 누락된 datasets/retrieval_jobs를 메타데이터에서 보완했습니다.")


def _align_existing_jobs_to_recipe_families(
    plan: dict[str, Any],
    existing_jobs: list[Any],
    selected: list[dict[str, Any]],
    metadata: dict[str, Any],
    recipe_key: str,
    recipe: dict[str, Any],
    notes: list[str],
) -> None:
    if not existing_jobs or not selected:
        return
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    selected_by_family = {item["family"]: item for item in selected if item.get("family") and item.get("dataset_key")}
    params_by_dataset = plan.get("params_by_dataset") if isinstance(plan.get("params_by_dataset"), dict) else {}
    changed = False
    for job in existing_jobs:
        if not isinstance(job, dict):
            continue
        dataset_key = str(job.get("dataset_key") or "")
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        family = str(dataset_catalog.get("dataset_family") or "")
        selected_item = selected_by_family.get(family)
        if not selected_item:
            continue
        selected_dataset_key = str(selected_item.get("dataset_key") or "")
        if not selected_dataset_key or selected_dataset_key == dataset_key:
            continue
        selected_catalog = selected_item.get("catalog") if isinstance(selected_item.get("catalog"), dict) else {}
        job["dataset_key"] = selected_dataset_key
        job["job_id"] = f"recipe_{recipe_key}_{selected_dataset_key}"
        job["purpose"] = f"recipe:{recipe_key}:{family}"
        job["required_columns"] = _recipe_required_columns(plan, recipe, family, selected_catalog)
        if dataset_key in params_by_dataset and selected_dataset_key not in params_by_dataset:
            params_by_dataset[selected_dataset_key] = deepcopy(params_by_dataset[dataset_key])
        params_by_dataset.pop(dataset_key, None)
        changed = True
    if changed:
        plan["params_by_dataset"] = params_by_dataset
        plan["datasets"] = _unique([str(job.get("dataset_key") or "") for job in existing_jobs if isinstance(job, dict)])
        _append_once(notes, f"분석 recipe '{recipe_key}' 기준으로 dataset family를 메타데이터의 날짜/소스 범위에 맞게 정렬했습니다.")


def _apply_recipe_defaults(plan: dict[str, Any], recipe: dict[str, Any], question: str) -> None:
    if str(recipe.get("top_n_policy") or "") == "question_or_default":
        detected_top_n = _rank_n_from_question(question)
        if detected_top_n:
            plan["top_n"] = detected_top_n
    defaults = recipe.get("defaults") if isinstance(recipe.get("defaults"), dict) else {}
    for key, value in defaults.items():
        if key == "input_target_column":
            continue
        if key not in plan:
            plan[key] = deepcopy(value)
    if "input_target_column" in defaults and _mentions_any(question, ["INPUT계획", "INPUT 계획", "input plan"]):
        plan["target_column"] = deepcopy(defaults["input_target_column"])
    if recipe.get("output_columns") and "analysis_output_shape" not in plan:
        plan["analysis_output_columns"] = deepcopy(recipe.get("output_columns"))


def _apply_recipe_filter_policy(plan: dict[str, Any], recipe: dict[str, Any]) -> None:
    blocked_fields = _as_recipe_text_list(recipe.get("blocked_filter_fields"))
    if not blocked_fields:
        return
    plan["blocked_filter_fields"] = _unique([*(_as_recipe_text_list(plan.get("blocked_filter_fields"))), *blocked_fields])
    if isinstance(plan.get("filters"), list):
        plan["filters"] = _remove_filter_fields(plan["filters"], blocked_fields)
    for job in plan.get("retrieval_jobs", []) if isinstance(plan.get("retrieval_jobs"), list) else []:
        if isinstance(job, dict) and isinstance(job.get("filters"), list):
            job["filters"] = _remove_filter_fields(job["filters"], blocked_fields)


def _rank_n_from_question(question: str) -> int:
    match = re.search(r"\b(\d{1,2})\b", str(question or ""))
    return int(match.group(1)) if match else 0


def _resolve_recipe_grain(
    question: str,
    recipe: dict[str, Any],
    metadata: dict[str, Any],
    plan: dict[str, Any],
) -> list[str]:
    policy = str(recipe.get("grain_policy") or "").strip()
    if policy == "aggregate_total":
        return []
    if policy in {"no_product_grain", "recipe_step_grain", "explicit_process_grain"}:
        return []
    explicit_grain = _explicit_grain_from_question(question, metadata)
    if explicit_grain is not None:
        return explicit_grain
    if _mentions_any(question, ["전체", "총", "합계", "total", "overall"]):
        return []
    current = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    if current:
        return current
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    return domain.get("product_key_columns", []) if isinstance(domain.get("product_key_columns"), list) else []


def _explicit_grain_from_question(question: str, metadata: dict[str, Any]) -> list[str] | None:
    text = str(question or "")
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    product_grain = domain.get("product_key_columns", []) if isinstance(domain.get("product_key_columns"), list) else []
    if _mentions_any(text, ["DEVICE", "device", "DEVICE by", "by DEVICE"]):
        return ["DEVICE"]
    if _mentions_any(text, ["제품별", "제품 별", "제품 단위", "제품마다"]):
        return product_grain
    if _mentions_any(text, ["MODE별", "MODE 별", "모드별"]):
        return ["MODE"]
    if _mentions_any(text, ["차수별", "차수 별", "공정 차수별", "공정차수별"]):
        return ["OPER_NUM"]
    if _mentions_any(text, ["세부공정별", "세부 공정별", "상세공정별", "상세 공정별"]):
        return ["OPER_NAME"]
    if _mentions_any(text, ["공정별", "공정 별"]):
        return ["OPER_NAME"]
    return None


def _repair_explicit_grain_plan(plan: dict[str, Any], metadata: dict[str, Any], question: str, notes: list[str]) -> None:
    explicit_grain = _explicit_grain_from_question(question, metadata)
    if explicit_grain is None:
        return
    if not explicit_grain:
        return
    current_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    if current_grain == explicit_grain:
        return
    should_override = (
        str(plan.get("analysis_kind") or "") in {"rank_top_n", "rank_bottom_n", "aggregate_join", "generic_aggregate_recipe", "aggregate_wip_total"}
        or _mentions_any(question, ["top", "rank", "상위", "많은", "가장", "별로", "별"])
    )
    if not should_override:
        return
    plan["product_grain"] = deepcopy(explicit_grain)
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if not isinstance(step, dict):
            continue
        operation = str(step.get("operation") or "").strip()
        if operation in {"rank_top_n", "rank_bottom_n", "aggregate_sum", "aggregate_by_group", "aggregate_total"}:
            step["group_by"] = deepcopy(explicit_grain)
            metric = str(step.get("metric") or plan.get("metric") or "").strip()
            if metric and "output_columns" not in step:
                step["output_columns"] = [*deepcopy(explicit_grain), metric]
    if isinstance(plan.get("analysis_output_columns"), list):
        metric_columns = [
            str(column)
            for column in plan["analysis_output_columns"]
            if str(column or "").strip() and str(column) not in current_grain
        ]
        plan["analysis_output_columns"] = _unique([*deepcopy(explicit_grain), *metric_columns])
    _append_once(notes, "질문에 명시된 집계/랭킹 축을 기준으로 group_by를 보정했습니다.")


def _recipe_datasets(recipe: dict[str, Any], metadata: dict[str, Any], question: str) -> list[dict[str, Any]]:
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    families = _unique(recipe.get("required_dataset_families", []))
    families.extend(_families_from_quantity_terms(recipe.get("required_quantity_terms", []), metadata))
    selected = []
    for family in _unique(families):
        dataset_key = _dataset_for_family(family, catalog, question)
        if not dataset_key:
            continue
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        selected.append({"family": family, "dataset_key": dataset_key, "catalog": dataset_catalog})
    return selected


def _families_from_quantity_terms(quantity_keys: Any, metadata: dict[str, Any]) -> list[str]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    terms = domain.get("quantity_terms") if isinstance(domain.get("quantity_terms"), dict) else {}
    families = []
    quantity_list = quantity_keys if isinstance(quantity_keys, list) else []
    for key in quantity_list:
        term = terms.get(key) if isinstance(terms.get(key), dict) else {}
        family = str(term.get("dataset_family") or "").strip()
        if family:
            families.append(family)
    return families


def _dataset_for_family(family: str, catalog: dict[str, Any], question: str) -> str:
    candidates = [
        (dataset_key, item)
        for dataset_key, item in catalog.items()
        if isinstance(item, dict) and str(item.get("dataset_family") or "") == family
    ]
    if not candidates:
        return ""
    mentions_yesterday = _mentions_any(question, ["어제", "전일", "yesterday"])
    mentions_today = _mentions_any(question, ["오늘", "현재", "금일", "today", "current"])
    if mentions_yesterday:
        for dataset_key, item in candidates:
            if str(item.get("date_scope") or "") == "history":
                return str(dataset_key)
    if mentions_today:
        for dataset_key, item in candidates:
            if str(item.get("date_scope") or "") == "current_day":
                return str(dataset_key)
    for dataset_key, item in candidates:
        if str(item.get("date_scope") or "") == "current_day":
            return str(dataset_key)
    return str(candidates[0][0])


def _recipe_source_alias(recipe: dict[str, Any], family: str, dataset_key: str, index: int) -> str:
    aliases = recipe.get("source_aliases_by_family") if isinstance(recipe.get("source_aliases_by_family"), dict) else {}
    alias = str(aliases.get(family) or "").strip()
    return alias or f"{dataset_key}_{index + 1}"


def _recipe_required_columns(
    plan: dict[str, Any],
    recipe: dict[str, Any],
    family: str,
    dataset_catalog: dict[str, Any],
) -> list[str]:
    overrides = recipe.get("required_columns_by_family") if isinstance(recipe.get("required_columns_by_family"), dict) else {}
    if isinstance(overrides.get(family), list) and overrides[family]:
        return _unique(overrides[family])
    if plan.get("detail_rows_requested") or str(plan.get("analysis_kind") or "") == "detail_rows":
        detail_columns = dataset_catalog.get("default_detail_columns")
        if isinstance(detail_columns, list) and detail_columns:
            return _unique(detail_columns)
        return _unique(dataset_catalog.get("columns", []))
    columns = []
    date_columns = (dataset_catalog.get("filter_mappings") or {}).get("DATE") if isinstance(dataset_catalog.get("filter_mappings"), dict) else []
    columns.extend(_unique(date_columns))
    product_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    columns.extend(product_grain)
    quantity = dataset_catalog.get("primary_quantity_column")
    columns.extend(quantity if isinstance(quantity, list) else [quantity] if quantity else [])
    if family == "target":
        target_column = str(plan.get("target_column") or "").strip()
        if target_column:
            columns.append(target_column)
    return _unique(columns)


def _recipe_step_plan(plan: dict[str, Any], recipe_key: str, recipe: dict[str, Any], question: str) -> list[dict[str, Any]]:
    template = recipe.get("step_plan_template") if isinstance(recipe.get("step_plan_template"), list) else []
    if template:
        aliases = recipe.get("source_aliases_by_family") if isinstance(recipe.get("source_aliases_by_family"), dict) else {}
        top_n = plan.get("top_n")
        if not isinstance(top_n, int) or top_n <= 0:
            top_n = _rank_n_from_question(question) or int((recipe.get("defaults") or {}).get("top_n") or 0) or 5
        steps = []
        for raw_step in template:
            if not isinstance(raw_step, dict):
                continue
            step = deepcopy(raw_step)
            source_family = str(step.pop("source_family", "") or "")
            if source_family and not step.get("source_alias"):
                step["source_alias"] = str(aliases.get(source_family) or "")
            step = _expand_recipe_step_value(step, top_n, plan)
            steps.append(step)
        return steps
    kind = str(plan.get("analysis_kind") or recipe.get("default_analysis_kind") or "").strip()
    if not kind:
        return []
    return [
        {
            "step_id": f"apply_{recipe_key}",
            "operation": kind,
            "recipe_key": recipe_key,
            "grain_policy": recipe.get("grain_policy", ""),
            "group_by": plan.get("product_grain", []),
            "output_columns": deepcopy(recipe.get("output_columns", [])),
        }
    ]


def _expand_recipe_step_value(value: Any, top_n: int, plan: dict[str, Any]) -> Any:
    if value == "$top_n":
        return top_n
    if value == "$analysis_output_columns":
        return deepcopy(plan.get("analysis_output_columns", []))
    if isinstance(value, list):
        return [_expand_recipe_step_value(item, top_n, plan) for item in value]
    if isinstance(value, dict):
        return {key: _expand_recipe_step_value(item, top_n, plan) for key, item in value.items()}
    return value


def _fallback_retrieval_jobs(
    plan: dict[str, Any],
    llm_json: dict[str, Any],
    metadata: dict[str, Any],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    datasets = _unique(plan.get("datasets"))
    if not datasets:
        return []
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    request_date = _request_date(payload)

    jobs = []
    for index, dataset_key in enumerate(datasets):
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        params = _params_for_dataset(llm_json, dataset_key)
        shell_job = {"dataset_key": dataset_key, "source_alias": _fallback_alias(plan, dataset_key, index, len(datasets))}
        _fill_required_params(params, dataset_key, dataset_catalog, question, request_date, shell_job)
        alias = _fallback_alias(plan, dataset_key, index, len(datasets))
        shell_job.update({"source_alias": alias, "params": params, "filters": []})
        filters = _augmented_filters_for_job(shell_job, plan, metadata, question, request_date)
        jobs.append(
            {
                "job_id": f"fallback_{index + 1}_{dataset_key}",
                "dataset_key": dataset_key,
                "source_alias": alias,
                "purpose": _fallback_purpose(plan.get("analysis_kind"), dataset_key),
                "params": params,
                "filters": filters,
                "required_columns": dataset_catalog.get("columns", []),
                "source_type": dataset_catalog.get("source_type", "dummy"),
                "source_config": deepcopy(dataset_catalog.get("source_config", {})),
                "required_params": deepcopy(dataset_catalog.get("required_params", [])),
                "required_param_mappings": deepcopy(dataset_catalog.get("required_param_mappings", {})),
                "date_format": deepcopy(dataset_catalog.get("date_format", "")),
                "primary_quantity_column": deepcopy(dataset_catalog.get("primary_quantity_column")),
                "filter_mappings": deepcopy(dataset_catalog.get("filter_mappings", {})),
                "standard_column_aliases": deepcopy(dataset_catalog.get("standard_column_aliases", {})),
                "pandas_preprocessing": {"standardize_columns": True},
            }
        )
    return jobs


def _normalize_required_columns(
    raw_columns: Any,
    catalog: dict[str, Any],
    product_grain: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    catalog_columns = _unique(catalog.get("columns", []))
    filter_mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    standard_aliases = catalog.get("standard_column_aliases") if isinstance(catalog.get("standard_column_aliases"), dict) else {}
    columns = _unique(raw_columns if isinstance(raw_columns, list) and raw_columns else catalog_columns)
    normalized: list[str] = []
    for column in columns:
        if column in catalog_columns:
            normalized.append(column)
            continue
        standard_column = _standard_column_for_required_column(str(column), catalog, product_grain, metadata)
        mapped_columns = _source_columns_for_standard_column(standard_column, catalog)
        if mapped_columns:
            normalized.extend(item for item in mapped_columns if item in catalog_columns or item not in normalized)
        elif column:
            normalized.append(column)
    quantity = catalog.get("primary_quantity_column")
    quantity_columns = quantity if isinstance(quantity, list) else [quantity] if quantity else []
    normalized.extend(_source_columns_for_standard_columns(quantity_columns, catalog))
    supported_product_columns = [
        column
        for column in _unique(product_grain or [])
        if column in filter_mappings or column in standard_aliases or column in catalog_columns
    ]
    normalized.extend(_source_columns_for_standard_columns(supported_product_columns, catalog))
    return _unique(normalized)


def _standard_column_for_required_column(
    column: str,
    catalog: dict[str, Any],
    product_grain: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    text = str(column or "").strip()
    if not text:
        return ""
    aliases = _standard_column_aliases(catalog, product_grain, metadata)
    for alias, standard in aliases:
        if text == alias:
            return standard
    normalized_text = _column_identity(text)
    if not normalized_text:
        return text
    for alias, standard in aliases:
        if _column_identity(alias) == normalized_text:
            return standard
    return text


def _standard_column_aliases(
    catalog: dict[str, Any],
    product_grain: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    main_filters = metadata.get("main_flow_filters") if isinstance(metadata, dict) and isinstance(metadata.get("main_flow_filters"), dict) else {}
    for standard, spec in main_filters.items():
        standard_text = str(standard or "").strip()
        if not standard_text:
            continue
        _append_standard_alias(aliases, standard_text, standard_text)
        if isinstance(spec, dict):
            candidates = spec.get("column_candidates") if isinstance(spec.get("column_candidates"), list) else []
            for candidate in candidates:
                _append_standard_alias(aliases, candidate, standard_text)

    domain = metadata.get("domain_items") if isinstance(metadata, dict) and isinstance(metadata.get("domain_items"), dict) else {}
    domain_product_keys = domain.get("product_key_columns") if isinstance(domain.get("product_key_columns"), list) else []
    for standard in _unique([*(product_grain or []), *domain_product_keys]):
        _append_standard_alias(aliases, standard, standard)

    for field in ("filter_mappings", "standard_column_aliases", "required_param_mappings"):
        mapping = catalog.get(field) if isinstance(catalog.get(field), dict) else {}
        for standard, candidates in mapping.items():
            standard_text = str(standard or "").strip()
            if not standard_text:
                continue
            _append_standard_alias(aliases, standard_text, standard_text)
            candidate_list = candidates if isinstance(candidates, list) else [candidates]
            for candidate in candidate_list:
                _append_standard_alias(aliases, candidate, standard_text)
    return aliases


def _append_standard_alias(aliases: list[tuple[str, str]], alias: Any, standard: Any) -> None:
    alias_text = str(alias or "").strip()
    standard_text = str(standard or "").strip()
    if alias_text and standard_text and (alias_text, standard_text) not in aliases:
        aliases.append((alias_text, standard_text))


def _column_identity(value: Any) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def _required_product_grain(plan: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    kind = str(plan.get("analysis_kind") or "")
    product_grain_kinds = {
        "rank_wip_then_join_production",
        "rank_top_n",
        "aggregate_join",
        "aggregate_sum",
        "generic_aggregate_recipe",
        "production_wip_target_rate",
        "low_output_vs_target",
        "date_split_production_plan_gap",
        "equipment_for_previous_products",
        "equipment_count_for_previous_products",
    }
    if kind not in product_grain_kinds:
        return []
    mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    standard_aliases = catalog.get("standard_column_aliases") if isinstance(catalog.get("standard_column_aliases"), dict) else {}
    product_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    catalog_columns = _unique(catalog.get("columns", []))
    return [column for column in product_grain if column in mappings or column in standard_aliases or column in catalog_columns]


def _attach_column_standardization_contract(job: dict[str, Any], dataset_catalog: dict[str, Any]) -> None:
    catalog_columns = set(_unique(dataset_catalog.get("columns", [])))
    for field in ("filter_mappings", "required_param_mappings", "standard_column_aliases"):
        merged = _merged_mapping_dict(dataset_catalog.get(field), job.get(field))
        merged = _filter_mapping_candidates_to_catalog_columns(merged, catalog_columns)
        if merged:
            job[field] = merged
    has_mapping = any(
        isinstance(job.get(key), dict) and job.get(key)
        for key in ("filter_mappings", "required_param_mappings", "standard_column_aliases")
    )
    if has_mapping:
        job["pandas_preprocessing"] = {
            "standardize_columns": True,
            "source": "table_catalog filter/alias mappings",
        }


def _merged_mapping_dict(catalog_value: Any, job_value: Any) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for mapping in (catalog_value, job_value):
        if not isinstance(mapping, dict):
            continue
        for key, raw_candidates in mapping.items():
            key_text = str(key or "").strip()
            if not key_text:
                continue
            candidates = raw_candidates if isinstance(raw_candidates, list) else [raw_candidates]
            merged.setdefault(key_text, [])
            merged[key_text].extend(str(item) for item in candidates if str(item or "").strip())
    return {key: _unique(values) for key, values in merged.items()}


def _filter_mapping_candidates_to_catalog_columns(
    mapping: dict[str, list[str]],
    catalog_columns: set[str],
) -> dict[str, list[str]]:
    if not mapping or not catalog_columns:
        return mapping
    filtered: dict[str, list[str]] = {}
    for standard, candidates in mapping.items():
        kept = [candidate for candidate in candidates if candidate in catalog_columns]
        if standard in catalog_columns:
            kept.append(standard)
        if kept:
            filtered[standard] = _unique(kept)
    return filtered


def _source_columns_for_standard_columns(columns: Any, catalog: dict[str, Any]) -> list[str]:
    result: list[str] = []
    values = columns if isinstance(columns, list) else [columns] if columns else []
    for column in values:
        result.extend(_source_columns_for_standard_column(str(column or "").strip(), catalog))
    return _unique(result)


def _source_columns_for_standard_column(column: str, catalog: dict[str, Any]) -> list[str]:
    text = str(column or "").strip()
    if not text:
        return []
    catalog_columns = _unique(catalog.get("columns", []))
    catalog_column_set = set(catalog_columns)
    mappings: list[str] = []
    for field in ("filter_mappings", "standard_column_aliases", "required_param_mappings"):
        mapping = catalog.get(field) if isinstance(catalog.get(field), dict) else {}
        candidates = mapping.get(text)
        if candidates is None:
            continue
        if not isinstance(candidates, list):
            candidates = [candidates]
        mappings.extend(str(item) for item in candidates if str(item or "").strip())
    mappings = _unique(mappings)
    mapped_existing = [item for item in mappings if item in catalog_column_set]
    if mapped_existing:
        return mapped_existing
    if text in catalog_column_set:
        return [text]
    if mappings:
        return mappings
    return [text]


def _normalize_step_plan_columns(plan: dict[str, Any], jobs: list[dict[str, Any]], catalog: dict[str, Any]) -> None:
    alias_to_catalog: dict[str, dict[str, Any]] = {}
    for job in jobs:
        dataset_key = str(job.get("dataset_key") or "")
        alias = str(job.get("source_alias") or dataset_key)
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        alias_to_catalog[alias] = dataset_catalog
    for step in plan.get("step_plan", []):
        if not isinstance(step, dict):
            continue
        source_alias = str(step.get("source_alias") or "")
        dataset_catalog = alias_to_catalog.get(source_alias, {})
        if not dataset_catalog:
            continue
        for key in ("group_by_columns",):
            if isinstance(step.get(key), list):
                step[key] = _map_logical_columns(step[key], dataset_catalog)
        for key in ("count_column", "metric", "target_column"):
            if isinstance(step.get(key), str):
                mapped = _map_logical_columns([step[key]], dataset_catalog)
                if mapped:
                    step[key] = mapped[0]


def _augment_step_plan_defaults(
    plan: dict[str, Any],
    jobs: list[dict[str, Any]],
    metadata: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    steps = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
    if not steps:
        return
    alias_to_job = {str(job.get("source_alias") or job.get("dataset_key") or ""): job for job in jobs if isinstance(job, dict)}
    first_job = jobs[0] if jobs else {}
    analysis_kind = str(plan.get("analysis_kind") or "")
    for step in steps:
        if not isinstance(step, dict):
            continue
        operation = str(step.get("operation") or analysis_kind)
        if operation not in {"rank_top_n", "rank_bottom_n"} and analysis_kind not in {"rank_top_n", "rank_bottom_n"}:
            continue
        rank_kind = operation if operation in {"rank_top_n", "rank_bottom_n"} else analysis_kind
        source_alias = str(step.get("source_alias") or "")
        job = alias_to_job.get(source_alias) or first_job
        if not step.get("metric"):
            metric = _fallback_metric(plan, job, metadata) if isinstance(job, dict) else ""
            if metric:
                step["metric"] = metric
        if "top_n" not in step and "bottom_n" not in step:
            step["top_n"] = _fallback_rank_n(plan, payload)
        if not step.get("rank_order"):
            step["rank_order"] = _fallback_rank_order(plan, payload, rank_kind)
        if "group_by" not in step and isinstance(plan.get("product_grain"), list):
            step["group_by"] = deepcopy(plan["product_grain"])
        if "output_columns" not in step and isinstance(plan.get("analysis_output_columns"), list):
            step["output_columns"] = deepcopy(plan["analysis_output_columns"])


def _map_logical_columns(columns: list[Any], catalog: dict[str, Any]) -> list[str]:
    catalog_columns = set(_unique(catalog.get("columns", [])))
    mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    result: list[str] = []
    for column in columns:
        text = str(column or "").strip()
        if not text:
            continue
        if text in catalog_columns:
            result.append(text)
            continue
        mapped = _unique(mappings.get(text, []))
        if mapped:
            result.append(mapped[0])
        else:
            result.append(text)
    return _unique(result)


def _fallback_alias(plan: dict[str, Any], dataset_key: str, index: int, dataset_count: int) -> str:
    if dataset_count == 1:
        step_plan = plan.get("step_plan") if isinstance(plan.get("step_plan"), list) else []
        for step in step_plan:
            if isinstance(step, dict) and step.get("source_alias"):
                return str(step["source_alias"])
        return dataset_key
    return f"{dataset_key}_{index + 1}"


def _fallback_purpose(analysis_kind: Any, dataset_key: str) -> str:
    kind = str(analysis_kind or "")
    return f"{kind or 'analysis'}_source:{dataset_key}"


def _fallback_step_plan(plan: dict[str, Any], metadata: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(plan.get("analysis_kind") or "")
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    first_alias = jobs[0].get("source_alias") if jobs and isinstance(jobs[0], dict) else ""
    if kind in {"rank_top_n", "rank_bottom_n"} and first_alias:
        step = {
            "step_id": "rank_items",
            "operation": kind,
            "source_alias": first_alias,
            "metric": _fallback_metric(plan, jobs[0], metadata),
            "top_n": _fallback_rank_n(plan, payload),
            "rank_order": _fallback_rank_order(plan, payload, kind),
        }
        if isinstance(plan.get("product_grain"), list):
            step["group_by"] = deepcopy(plan["product_grain"])
        if isinstance(plan.get("analysis_output_columns"), list):
            step["output_columns"] = deepcopy(plan["analysis_output_columns"])
        return [step]
    if kind == "detail_rows" and first_alias:
        aliases = _unique([str(job.get("source_alias") or "") for job in jobs if isinstance(job, dict) and job.get("source_alias")])
        step = {"step_id": "detail_rows", "operation": "detail_rows", "source_alias": first_alias}
        if len(aliases) > 1:
            step["source_aliases"] = aliases
        return [step]
    return []


def _fallback_metric(plan: dict[str, Any], job: dict[str, Any], metadata: dict[str, Any]) -> str:
    for key in ("metric", "target_column"):
        value = plan.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    quantity = job.get("primary_quantity_column")
    if isinstance(quantity, str) and quantity.strip():
        return quantity.strip()
    if isinstance(quantity, list):
        for item in quantity:
            text = str(item or "").strip()
            if text:
                return text
    catalog = ((metadata.get("table_catalog") or {}).get("datasets") or {}) if isinstance(metadata, dict) else {}
    dataset_key = str(job.get("dataset_key") or "")
    dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
    quantity = dataset_catalog.get("primary_quantity_column")
    if isinstance(quantity, str) and quantity.strip():
        return quantity.strip()
    if isinstance(quantity, list):
        for item in quantity:
            text = str(item or "").strip()
            if text:
                return text
    return ""


def _fallback_rank_n(plan: dict[str, Any], payload: dict[str, Any]) -> int:
    for key in ("top_n", "bottom_n"):
        value = plan.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit() and int(value) > 0:
            return int(value)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    match = re.search(r"\b(\d{1,2})\b", question)
    if match:
        return int(match.group(1))
    if _mentions_any(question, ["가장", "최대", "최고", "제일", "most", "highest", "top"]):
        return 1
    return 5


def _fallback_rank_order(plan: dict[str, Any], payload: dict[str, Any], kind: str) -> str:
    order = _canonical_rank_order(plan.get("rank_order"))
    if order:
        return order
    question = ""
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    if isinstance(request, dict):
        question = str(request.get("question") or "")
    text = question.lower()
    if kind == "rank_bottom_n" or "bottom" in text or "lowest" in text or "하위" in question or "낮은" in question:
        return "asc"
    return "desc"


def _fill_required_params(
    params: dict[str, Any],
    dataset_key: str,
    catalog: dict[str, Any],
    question: str,
    request_date: str,
    job: dict[str, Any] | None = None,
) -> None:
    required = catalog.get("required_params") if isinstance(catalog.get("required_params"), list) else []
    has_date_param = bool(params.get("DATE"))
    supports_date_filter = _catalog_has_filter(catalog, "DATE")
    if "DATE" in required or has_date_param or supports_date_filter:
        date_value = _date_value_for_job(question, dataset_key, catalog, job or {}, request_date)
        if date_value:
            params["DATE"] = _date_param(dataset_key, date_value, catalog)
        elif not params.get("DATE"):
            params["DATE"] = _date_param(dataset_key, request_date, catalog)
    if "LOT_ID" in required and not params.get("LOT_ID"):
        lot_id = _extract_lot_id(question)
        if lot_id:
            params["LOT_ID"] = lot_id


def _augmented_filters_for_job(
    job: dict[str, Any],
    plan: dict[str, Any],
    metadata: dict[str, Any],
    question: str,
    request_date: str,
) -> list[dict[str, Any]]:
    table_catalog = metadata.get("table_catalog") if isinstance(metadata.get("table_catalog"), dict) else {}
    datasets = table_catalog.get("datasets") if isinstance(table_catalog.get("datasets"), dict) else {}
    dataset_key = str(job.get("dataset_key") or "")
    dataset_catalog = datasets.get(dataset_key) if isinstance(datasets.get(dataset_key), dict) else {}
    raw_filters = job.get("filters") if isinstance(job.get("filters"), list) else []
    plan_filters = plan.get("filters") if isinstance(plan.get("filters"), list) else []
    inferred_filters = _infer_filters(
        question,
        metadata,
        plan.get("analysis_kind"),
        request_date,
        dataset_key=dataset_key,
        dataset_catalog=dataset_catalog,
        job=job,
        blocked_filter_fields=_blocked_filter_fields(plan),
    )
    merged = [deepcopy(item) for item in raw_filters if isinstance(item, dict)]
    source_specific_fields = _filter_fields(merged)
    merged.extend(deepcopy(item) for item in plan_filters if isinstance(item, dict) and str(item.get("field") or "").strip() not in source_specific_fields)
    if any(str(item.get("field") or "").strip() == "DATE" for item in inferred_filters if isinstance(item, dict)):
        merged = [item for item in merged if str(item.get("field") or "").strip() != "DATE"]
        source_specific_fields.discard("DATE")
    merged.extend(deepcopy(item) for item in inferred_filters if isinstance(item, dict) and str(item.get("field") or "").strip() not in source_specific_fields)
    if plan.get("state_product_keys") and _supports_product_grain_filter(dataset_catalog, plan):
        merged.append({"field": "PRODUCT_GRAIN", "op": "from_state"})
    blocked_fields = _blocked_filter_fields(plan)
    if blocked_fields:
        merged = _remove_filter_fields(merged, blocked_fields)
    if _all_process_scope_for_job(question, job, dataset_catalog):
        merged = _remove_filter_fields(merged, ["OPER_NAME"])
    else:
        process_scope_values = _job_process_scope_values(job, metadata)
        if process_scope_values and _catalog_has_filter(dataset_catalog, "OPER_NAME"):
            merged = _replace_include_filters_for_field(merged, "OPER_NAME", process_scope_values)
    merged = _drop_conflicting_product_alias_filters(merged, inferred_filters, metadata)
    return _filters_for_dataset(_dedupe_filters(merged), dataset_key, dataset_catalog)


def _filters_for_dataset(filters: list[Any], dataset_key: str, catalog: dict[str, Any]) -> list[dict[str, Any]]:
    mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    result = []
    for item in filters:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        if not field:
            continue
        if field == "PRODUCT_GRAIN" or field in mappings:
            clean_item = deepcopy(item)
            if field == "DATE":
                _normalize_date_filter(clean_item, dataset_key, catalog)
            result.append(clean_item)
    return _dedupe_filters(result)


def _filter_fields(filters: list[Any]) -> set[str]:
    return {str(item.get("field") or "").strip() for item in filters if isinstance(item, dict) and str(item.get("field") or "").strip()}


def _all_process_scope_for_job(question: str, job: dict[str, Any], dataset_catalog: dict[str, Any]) -> bool:
    if not _mentions_any(question, ["전 공정", "전공정", "전체 공정", "전체공정", "all process", "all processes", "all operation", "all operations"]):
        return False
    job_text = " ".join(
        str(job.get(key) or "")
        for key in ("source_alias", "purpose", "job_id", "dataset_key")
    ).lower()
    family = str(dataset_catalog.get("dataset_family") or "").lower()
    return any(token in job_text for token in ("all", "current", "wip", "전체", "전공정")) or family in {"wip", "inventory"}


def _job_process_scope_values(job: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    for keys in (("source_alias", "job_id"), ("purpose",)):
        text = " ".join(str(job.get(key) or "") for key in keys)
        values = _single_process_scope_values_from_text(text, metadata)
        if values:
            return values
    return []


def _single_process_scope_values_from_text(text: str, metadata: dict[str, Any]) -> list[str]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    groups = domain.get("process_groups") if isinstance(domain.get("process_groups"), dict) else {}
    exact_matches: list[str] = []
    for group in groups.values():
        if not isinstance(group, dict):
            continue
        for value in group.get("processes") if isinstance(group.get("processes"), list) else []:
            process = str(value or "").strip()
            if process and _alias_in_text(text, process):
                exact_matches.append(process)
    if exact_matches:
        return _unique(exact_matches)

    matched_group_values: list[list[str]] = []
    for group_key, group in groups.items():
        if not isinstance(group, dict):
            continue
        aliases = group.get("aliases") if isinstance(group.get("aliases"), list) else []
        match_values = [group_key, group.get("display_name"), *aliases]
        if not _mentions_any(text, match_values):
            continue
        values = [str(item) for item in group.get("processes", []) if str(item or "").strip()] if isinstance(group.get("processes"), list) else []
        if values:
            matched_group_values.append(values)
    if len(matched_group_values) == 1:
        return _unique(matched_group_values[0])
    return []


def _replace_include_filters_for_field(filters: list[Any], field_name: str, values: list[Any]) -> list[dict[str, Any]]:
    replacement_values = _unique([str(value) for value in values if str(value or "").strip()])
    if not replacement_values:
        return [deepcopy(item) for item in filters if isinstance(item, dict)]
    result: list[dict[str, Any]] = []
    inserted = False
    for item in filters:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        op = str(item.get("op") or ("eq" if "value" in item else "")).strip().lower()
        if field == field_name and op in {"eq", "in"}:
            if not inserted:
                result.append({"field": field_name, "op": "in", "values": replacement_values})
                inserted = True
            continue
        result.append(deepcopy(item))
    if not inserted:
        result.append({"field": field_name, "op": "in", "values": replacement_values})
    return result


def _infer_filters(
    question: str,
    metadata: dict[str, Any],
    analysis_kind: Any,
    request_date: str,
    dataset_key: str = "",
    dataset_catalog: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
    blocked_filter_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    text = str(question or "")
    catalog = dataset_catalog or {}
    filters: list[dict[str, Any]] = []
    date_value = _date_value_for_job(text, dataset_key, catalog, job or {}, request_date)
    if date_value and _metadata_has_filter(metadata, "DATE") and _catalog_has_filter(catalog, "DATE"):
        filters.append({"field": "DATE", "op": "eq", "value": date_value})
    term_filters = _metadata_term_filters(text, metadata, dataset_key, catalog)
    filters.extend(_remove_filter_fields(term_filters, blocked_filter_fields or []))
    process_values = _metadata_process_values(text, metadata)
    if process_values and _metadata_has_filter(metadata, "OPER_NAME") and _catalog_has_filter(catalog, "OPER_NAME"):
        filters.append({"field": "OPER_NAME", "op": "in", "values": _unique(process_values)})
    if str(analysis_kind or "") == "equipment_for_previous_products":
        filters.append({"field": "PRODUCT_GRAIN", "op": "from_state"})
    return _dedupe_filters(filters)


def _attach_state_product_keys(plan: dict[str, Any], payload: dict[str, Any]) -> None:
    if plan.get("state_product_keys"):
        return
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    question = str(request.get("question") or "")
    needs_state_products = (
        plan.get("analysis_kind") == "equipment_for_previous_products"
        or plan.get("intent_type") == "followup_transform"
        or _mentions_any(question, ["이 제품", "그 제품", "해당 제품", "앞의 제품", "위 제품", "previous products"])
    )
    if not needs_state_products:
        return
    product_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    product_rows = _product_keys_from_state_summary(current_data, product_grain)
    if product_rows:
        plan["state_product_keys"] = product_rows
        return
    rows = _rows_from_current_data(current_data)
    product_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        product = {key: row.get(key) for key in product_grain if row.get(key) not in {None, ""}}
        if product and product not in product_rows:
            product_rows.append(product)
    if product_rows:
        plan["state_product_keys"] = product_rows


def _product_keys_from_state_summary(current_data: dict[str, Any], product_grain: list[Any]) -> list[dict[str, Any]]:
    values = current_data.get("product_key_values")
    if not isinstance(values, list):
        return []
    state_columns = current_data.get("product_key_columns") if isinstance(current_data.get("product_key_columns"), list) else []
    grain = [str(item) for item in product_grain if str(item or "").strip()] or [str(item) for item in state_columns]
    product_rows: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        if grain:
            product = {key: item.get(key) for key in grain if item.get(key) not in {None, ""}}
        else:
            product = {str(key): value for key, value in item.items() if value not in {None, ""}}
        if product and product not in product_rows:
            product_rows.append(product)
    return product_rows


def _repair_followup_analysis_kind(
    plan: dict[str, Any],
    raw_jobs: list[Any],
    catalog: dict[str, Any],
    notes: list[str],
) -> None:
    if plan.get("intent_type") != "followup_transform" or not plan.get("state_product_keys"):
        return
    families = []
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue
        dataset_key = str(raw_job.get("dataset_key") or "")
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        family = str(dataset_catalog.get("dataset_family") or "")
        if family:
            families.append(family)
    if any(family in {"equipment", "capacity"} for family in families):
        if str(plan.get("analysis_kind") or "") in {"equipment_by_model", "detail_rows", "none"}:
            plan["analysis_kind"] = "equipment_for_previous_products"
            _append_once(notes, "후속 질문 계획을 이전 state의 제품 key 기준으로 조정했습니다.")


def _repair_lot_count_plan(
    plan: dict[str, Any],
    raw_jobs: list[Any],
    catalog: dict[str, Any],
    question: str,
    notes: list[str],
) -> list[Any]:
    if not _is_lot_count_by_process_question(plan, raw_jobs, catalog, question):
        return raw_jobs

    lot_jobs = [deepcopy(job) for job in raw_jobs if isinstance(job, dict) and str(job.get("dataset_key") or "") == "lot_status"]
    if not lot_jobs:
        lot_jobs = [{"dataset_key": "lot_status", "source_alias": "lot_status", "filters": [], "params": {}}]
    primary_job = lot_jobs[0]
    primary_job["dataset_key"] = "lot_status"
    primary_job["source_alias"] = str(primary_job.get("source_alias") or "lot_status")
    primary_job.setdefault("params", {})
    filters = primary_job.get("filters") if isinstance(primary_job.get("filters"), list) else []
    primary_job["filters"] = deepcopy(filters)
    required_columns = primary_job.get("required_columns") if isinstance(primary_job.get("required_columns"), list) else []
    primary_job["required_columns"] = _unique([*required_columns, "OPER_SHORT_DESC", "LOT_ID", "LOT_STAT_CD"])

    plan["intent_type"] = "single_retrieval_analysis"
    plan["analysis_kind"] = "lot_count_by_process"
    plan["datasets"] = ["lot_status"]
    plan["product_grain"] = []
    plan["analysis_output_columns"] = ["OPER_SHORT_DESC", "LOT_COUNT"]
    plan["step_plan"] = [
        {
            "step_id": "count_lots_by_process",
            "operation": "lot_count_by_process",
            "source_alias": primary_job["source_alias"],
            "group_by_columns": ["OPER_SHORT_DESC"],
            "count_column": "LOT_ID",
            "output_columns": ["OPER_SHORT_DESC", "LOT_COUNT"],
        }
    ]
    _append_once(notes, "Lot 상태/수량 질문은 lot_status의 LOT_ID unique count 기준 공정별 집계로 정리했습니다.")
    return [primary_job]


def _is_lot_count_by_process_question(
    plan: dict[str, Any],
    raw_jobs: list[Any],
    catalog: dict[str, Any],
    question: str,
) -> bool:
    if plan.get("matched_analysis_recipe") and str(plan.get("analysis_kind") or "") != "lot_count_by_process":
        return False
    if str(plan.get("analysis_kind") or "") == "lot_count_by_process":
        return True
    datasets = {str(item) for item in plan.get("datasets", []) if str(item or "").strip()}
    has_lot_status = "lot_status" in datasets
    has_lot_status = has_lot_status or any(isinstance(job, dict) and str(job.get("dataset_key") or "") == "lot_status" for job in raw_jobs)
    if not has_lot_status:
        return False
    if not (
        _mentions_any(question, ["작업대기", "작업중", "Lot 수량", "LOT 수량", "Lot 개수", "lot count"])
        or _raw_jobs_include_filter(raw_jobs, "LOT_STAT_CD")
        or _plan_mentions_lot_count(plan)
    ):
        return False
    if _mentions_any(question, ["wafer", "Wafer", "die", "Die", "DIE"]):
        return False
    return True


def _raw_jobs_include_filter(raw_jobs: list[Any], field: str) -> bool:
    for job in raw_jobs:
        if not isinstance(job, dict):
            continue
        filters = job.get("filters") if isinstance(job.get("filters"), list) else []
        if any(isinstance(item, dict) and str(item.get("field") or "") == field for item in filters):
            return True
    return False


def _plan_mentions_lot_count(plan: dict[str, Any]) -> bool:
    values: list[Any] = [
        plan.get("metric"),
        plan.get("quantity_column"),
        plan.get("count_column"),
        *(plan.get("analysis_output_columns") if isinstance(plan.get("analysis_output_columns"), list) else []),
    ]
    for step in plan.get("step_plan", []) if isinstance(plan.get("step_plan"), list) else []:
        if isinstance(step, dict):
            values.extend([step.get("metric"), step.get("count_column"), step.get("aggregation")])
            if isinstance(step.get("output_columns"), list):
                values.extend(step["output_columns"])
    text = " ".join(str(item or "") for item in values)
    return any(token in text for token in ["LOT_COUNT", "nunique"])


def _repair_followup_equipment_plan(
    plan: dict[str, Any],
    raw_jobs: list[Any],
    catalog: dict[str, Any],
    question: str,
    notes: list[str],
) -> list[Any]:
    if plan.get("intent_type") != "followup_transform" or not plan.get("state_product_keys"):
        return raw_jobs
    if not _is_followup_equipment_question(question, raw_jobs, catalog, plan):
        return raw_jobs

    count_requested = _is_equipment_count_question(question, plan)
    analysis_kind = "equipment_count_for_previous_products" if count_requested else "equipment_for_previous_products"
    plan["analysis_kind"] = analysis_kind

    equipment_jobs = []
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue
        dataset_key = str(raw_job.get("dataset_key") or "")
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        if str(dataset_catalog.get("dataset_family") or "") == "equipment":
            equipment_jobs.append(deepcopy(raw_job))
    if not equipment_jobs:
        equipment_jobs = [{"dataset_key": "equipment_status", "source_alias": "equipment_for_previous_products", "filters": [], "params": {}}]

    primary_job = equipment_jobs[0]
    primary_job["dataset_key"] = "equipment_status"
    primary_job["source_alias"] = str(primary_job.get("source_alias") or "equipment_for_previous_products")
    primary_job["filters"] = [{"field": "PRODUCT_GRAIN", "op": "from_state"}]
    primary_job.setdefault("params", {})

    product_grain = [str(item) for item in plan.get("product_grain", []) if str(item or "").strip()]
    if count_requested:
        primary_job["purpose"] = "followup_equipment_count"
        primary_job["required_columns"] = ["EQPID", *product_grain]
        plan["analysis_output_columns"] = [*deepcopy(product_grain), "EQP_COUNT"]
        plan["step_plan"] = [
            {
                "step_id": "count_equipment_for_previous_products",
                "operation": "equipment_count_for_previous_products",
                "source_alias": primary_job["source_alias"],
                "group_by": deepcopy(product_grain),
                "count_column": "EQPID",
                "output_columns": [*deepcopy(product_grain), "EQP_COUNT"],
            }
        ]
    else:
        primary_job["purpose"] = "followup_equipment_detail_rows"
        primary_job["required_columns"] = ["EQPID", "EQP_MODEL", "PRESS_CNT", *product_grain, "LOT_ID", "RECIPE_ID"]
        plan["analysis_output_columns"] = ["EQPID", "EQP_MODEL", "PRESS_CNT", "LOT_ID", "RECIPE_ID"]
        plan["step_plan"] = [
            {
                "step_id": "filter_equipment_for_previous_products",
                "operation": "detail_rows_for_product_keys",
                "source_alias": primary_job["source_alias"],
                "columns": ["EQPID", "EQP_MODEL", "PRESS_CNT", *deepcopy(product_grain), "LOT_ID", "RECIPE_ID"],
                "output_ref": "final_result",
            }
        ]

    plan["datasets"] = ["equipment_status"]
    _append_once(notes, "후속 장비 질문은 이전 제품 key와 equipment_status만 사용하도록 조회 작업을 정리했습니다.")
    return [primary_job]


def _is_followup_equipment_question(
    question: str,
    raw_jobs: list[Any],
    catalog: dict[str, Any],
    plan: dict[str, Any],
) -> bool:
    if _mentions_any(question, ["장비", "설비", "EQP", "equipment", "Equipment"]):
        return True
    if str(plan.get("analysis_kind") or "") in {"equipment_for_previous_products", "equipment_count_for_previous_products", "equipment_by_model"}:
        return True
    for raw_job in raw_jobs:
        if not isinstance(raw_job, dict):
            continue
        dataset_key = str(raw_job.get("dataset_key") or "")
        dataset_catalog = catalog.get(dataset_key) if isinstance(catalog.get(dataset_key), dict) else {}
        if str(dataset_catalog.get("dataset_family") or "") == "equipment":
            return True
    return False


def _is_equipment_count_question(question: str, plan: dict[str, Any]) -> bool:
    if str(plan.get("analysis_kind") or "") == "equipment_count_for_previous_products":
        return True
    return _mentions_any(
        question,
        [
            "장비 대수",
            "설비 대수",
            "장비 수",
            "설비 수",
            "장비수",
            "설비수",
            "몇 대",
            "몇대",
            "대수",
            "count",
            "number of equipment",
            "equipment count",
        ],
    )


def _mark_previous_result_restore_need(
    plan: dict[str, Any],
    payload: dict[str, Any],
    question: str,
    notes: list[str],
) -> None:
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    if not _has_previous_mongo_data_ref(state, current_data):
        return

    explicit = plan.get("requires_full_previous_result_restore")
    if _truthy_value(explicit):
        plan["requires_full_previous_result_restore"] = True
        plan["previous_result_restore_mode"] = "full"
        plan["previous_result_restore_reason"] = "llm_requested_full_previous_rows"
        _append_once(notes, "후속 질문 계획에서 MongoDB의 이전 결과 전체 row 복원을 요청했습니다.")
        return

    if _previous_source_reuse_requested(question) and _has_previous_source_mongo_ref(state):
        _mark_previous_source_reuse(plan, state, question, notes)
        return

    if _state_product_keys_are_enough(plan, question):
        plan.setdefault("previous_result_restore_mode", "summary")
        return

    if _followup_needs_previous_rows(plan, question):
        plan["requires_full_previous_result_restore"] = True
        plan["previous_result_restore_mode"] = "full"
        plan["previous_result_restore_reason"] = "followup_analysis_needs_previous_rows"
        _append_once(notes, "후속 분석에 이전 결과 row가 필요하여 pandas 실행 전에 MongoDB에서 전체 row를 복원하도록 표시했습니다.")


def _has_mongo_data_ref(current_data: dict[str, Any]) -> bool:
    data_ref = current_data.get("data_ref")
    if isinstance(data_ref, dict) and str(data_ref.get("store") or "").lower() == "mongodb":
        return True
    data = current_data.get("data")
    if isinstance(data, dict):
        nested_ref = data.get("data_ref")
        return isinstance(nested_ref, dict) and str(nested_ref.get("store") or "").lower() == "mongodb"
    return False


def _has_previous_mongo_data_ref(state: dict[str, Any], current_data: dict[str, Any]) -> bool:
    if _has_mongo_data_ref(current_data):
        return True
    source_results = state.get("followup_source_results")
    if isinstance(source_results, list):
        for item in source_results:
            if isinstance(item, dict) and _is_mongo_ref(item.get("data_ref")):
                return True
    runtime_source_refs = state.get("runtime_source_refs") if isinstance(state.get("runtime_source_refs"), dict) else {}
    return any(_is_mongo_ref(data_ref) for data_ref in runtime_source_refs.values())


def _is_mongo_ref(value: Any) -> bool:
    return isinstance(value, dict) and str(value.get("store") or "").lower() == "mongodb" and bool(value.get("ref_id"))


def _has_previous_source_mongo_ref(state: dict[str, Any]) -> bool:
    source_results = state.get("followup_source_results")
    if isinstance(source_results, list):
        for item in source_results:
            if isinstance(item, dict) and _is_mongo_ref(item.get("data_ref")):
                return True
    runtime_source_refs = state.get("runtime_source_refs") if isinstance(state.get("runtime_source_refs"), dict) else {}
    return any(_is_mongo_ref(data_ref) for data_ref in runtime_source_refs.values())


def _previous_source_reuse_requested(question: str) -> bool:
    previous_terms = [
        "이때",
        "그때",
        "해당 때",
        "이 결과",
        "그 결과",
        "해당 결과",
        "이 데이터",
        "그 데이터",
        "해당 데이터",
        "방금",
        "직전",
        "앞에서",
        "위에서",
        "이전 결과",
        "previous result",
        "prior result",
        "same data",
    ]
    reshape_terms = [
        "상세",
        "세부",
        "나눠",
        "나누",
        "분해",
        "breakdown",
        "drilldown",
        "group",
        "groupby",
        "group by",
        "별로",
        "별",
        "device별",
        "디바이스별",
        "공정별",
        "제품별",
        "mode별",
    ]
    new_lookup_terms = ["장비", "설비", "할당", "대수", "lot", "hold", "보류", "작업대기", "작업중"]
    if _mentions_any(question, new_lookup_terms):
        return False
    return _mentions_any(question, previous_terms) and _mentions_any(question, reshape_terms)


def _mark_previous_source_reuse(
    plan: dict[str, Any],
    state: dict[str, Any],
    question: str,
    notes: list[str],
) -> None:
    aliases = _previous_source_aliases(state)
    dataset_keys = _previous_source_dataset_keys(state)
    group_by = _previous_source_group_by(plan, state, question)
    metric = _previous_source_metric(state, question)

    plan["intent_type"] = "followup_transform"
    plan["depends_on_state"] = True
    plan["reuse_previous_runtime_sources"] = True
    plan["requires_full_previous_result_restore"] = True
    plan["previous_result_restore_mode"] = "full"
    plan["previous_result_restore_reason"] = "followup_reuses_previous_source_rows"
    plan["retrieval_jobs"] = []
    if dataset_keys:
        plan["datasets"] = dataset_keys

    if group_by and metric:
        plan["analysis_kind"] = "aggregate_previous_source"
        plan["metric"] = metric
        plan["product_grain"] = group_by
        plan["step_plan"] = [
            {
                "step_id": "aggregate_previous_source",
                "operation": "aggregate_previous_source",
                "source_alias": aliases[0] if aliases else "",
                "source_aliases": aliases,
                "group_by": group_by,
                "metric": metric,
                "aggregation": "sum",
            }
        ]
    else:
        plan["analysis_kind"] = "detail_rows"
        plan["step_plan"] = [
            {
                "step_id": "previous_source_detail_rows",
                "operation": "detail_rows",
                "source_alias": aliases[0] if aliases else "",
                "source_aliases": aliases,
                "columns": _previous_source_columns(state),
            }
        ]

    _append_once(notes, "후속 질문이 이전 조회 원본의 재가공 요청으로 보여 새 조회 없이 MongoDB source ref를 전체 복원하도록 조정했습니다.")


def _previous_source_aliases(state: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    source_results = state.get("followup_source_results")
    if isinstance(source_results, list):
        for item in source_results:
            if isinstance(item, dict):
                alias = str(item.get("source_alias") or item.get("dataset_key") or "").strip()
                if alias:
                    aliases.append(alias)
    runtime_source_refs = state.get("runtime_source_refs") if isinstance(state.get("runtime_source_refs"), dict) else {}
    aliases.extend(str(alias) for alias in runtime_source_refs if str(alias or "").strip())
    return _unique(aliases)


def _previous_source_dataset_keys(state: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    source_results = state.get("followup_source_results")
    if isinstance(source_results, list):
        for item in source_results:
            if isinstance(item, dict) and item.get("dataset_key"):
                keys.append(str(item["dataset_key"]))
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    source_dataset_keys = current_data.get("source_dataset_keys")
    if isinstance(source_dataset_keys, list):
        keys.extend(str(item) for item in source_dataset_keys if str(item or "").strip())
    return _unique(keys)


def _previous_source_columns(state: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    source_results = state.get("followup_source_results")
    if isinstance(source_results, list):
        for item in source_results:
            if isinstance(item, dict) and isinstance(item.get("columns"), list):
                columns.extend(str(column) for column in item["columns"] if str(column or "").strip())
    return _unique(columns)


def _previous_source_group_by(plan: dict[str, Any], state: dict[str, Any], question: str) -> list[str]:
    current_data = state.get("current_data") if isinstance(state.get("current_data"), dict) else {}
    group_by: list[str] = []
    if isinstance(current_data.get("product_key_columns"), list):
        group_by.extend(str(column) for column in current_data["product_key_columns"] if str(column or "").strip())
    elif isinstance(plan.get("product_grain"), list):
        group_by.extend(str(column) for column in plan["product_grain"] if str(column or "").strip())
    lowered = question.lower()
    dimension_terms = {
        "DEVICE": ["device", "디바이스", "device별", "디바이스별"],
        "DEVICE_DESC": ["device_desc", "device desc", "디바이스명"],
        "OPER_NAME": ["공정", "oper", "oper_name", "공정별"],
        "MODE": ["mode별", "모드별"],
    }
    for column, terms in dimension_terms.items():
        if any(term.lower() in lowered for term in terms):
            group_by.append(column)
    return _unique(group_by)


def _previous_source_metric(state: dict[str, Any], question: str) -> str:
    if _mentions_any(question, ["생산", "production", "실적"]):
        return "PRODUCTION"
    if _mentions_any(question, ["재공", "wip"]):
        return "WIP"
    columns = _previous_source_columns(state)
    for metric in ["PRODUCTION", "WIP", "OUT_PLAN", "TARGET_QTY", "LOT_COUNT", "WF_QTY", "DIE_QTY"]:
        if metric in columns:
            return metric
    return ""


def _state_product_keys_are_enough(plan: dict[str, Any], question: str) -> bool:
    if str(plan.get("analysis_kind") or "") not in {"equipment_for_previous_products", "equipment_count_for_previous_products"}:
        return False
    if not plan.get("state_product_keys"):
        return False
    if _mentions_any(question, ["전체", "모든", "상세", "세부", "원본", "row", "rows", "records", "full"]):
        return False
    return True


def _followup_needs_previous_rows(plan: dict[str, Any], question: str) -> bool:
    if str(plan.get("intent_type") or "") != "followup_transform" and not bool(plan.get("depends_on_state")):
        return False
    jobs = plan.get("retrieval_jobs") if isinstance(plan.get("retrieval_jobs"), list) else []
    datasets = plan.get("datasets") if isinstance(plan.get("datasets"), list) else []
    if not jobs and not datasets:
        return True
    if str(plan.get("analysis_kind") or "") in {"detail_rows", "rank_top_n"}:
        return True
    previous_terms = [
        "이전",
        "이때",
        "그때",
        "앞",
        "위",
        "방금",
        "직전",
        "결과",
        "데이터",
        "테이블",
        "목록",
        "previous",
        "prior",
        "current data",
        "result",
    ]
    row_operation_terms = [
        "전체",
        "모든",
        "상세",
        "세부",
        "원본",
        "다시",
        "정렬",
        "상위",
        "하위",
        "필터",
        "추려",
        "골라",
        "집계",
        "합계",
        "평균",
        "비교",
        "제품별",
        "공정별",
        "row",
        "rows",
        "records",
        "full",
        "all",
    ]
    return _mentions_any(question, previous_terms) and _mentions_any(question, row_operation_terms)


def _truthy_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "full", "all", "rows", "restore_full"}


def _rows_from_current_data(current_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = current_data.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    data = current_data.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        return [row for row in data["rows"] if isinstance(row, dict)]
    return []


def _metadata_term_filters(
    question: str,
    metadata: dict[str, Any],
    dataset_key: str = "",
    dataset_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    result: list[dict[str, Any]] = []
    for section_name in ("product_terms", "status_terms"):
        terms = domain.get(section_name) if isinstance(domain.get(section_name), dict) else {}
        for term_key, term in terms.items():
            if not isinstance(term, dict):
                continue
            aliases = term.get("aliases") if isinstance(term.get("aliases"), list) else []
            match_values = [term_key, term.get("display_name"), *aliases]
            if not _mentions_any(question, match_values):
                continue
            condition = _condition_for_dataset(term, dataset_key, dataset_catalog or {})
            result.extend(_condition_to_filters(condition, metadata))
    return result


def _metadata_process_values(question: str, metadata: dict[str, Any]) -> list[str]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    groups = domain.get("process_groups") if isinstance(domain.get("process_groups"), dict) else {}
    exact_matches: list[str] = []
    for group in groups.values():
        if not isinstance(group, dict):
            continue
        values = group.get("processes") if isinstance(group.get("processes"), list) else []
        for value in values:
            text = str(value or "").strip()
            if text and _alias_in_text(question, text):
                exact_matches.append(text)
    if exact_matches:
        return _unique(exact_matches)
    result: list[str] = []
    for group_key, group in groups.items():
        if not isinstance(group, dict):
            continue
        aliases = group.get("aliases") if isinstance(group.get("aliases"), list) else []
        match_values = [group_key, group.get("display_name"), *aliases]
        if not _mentions_any(question, match_values):
            continue
        values = group.get("processes") if isinstance(group.get("processes"), list) else []
        result.extend(str(item) for item in values if str(item or "").strip())
    return _unique(result)


def _attach_result_scope_columns(
    plan: dict[str, Any],
    jobs: list[dict[str, Any]],
    metadata: dict[str, Any],
    question: str,
) -> None:
    scope_columns: list[dict[str, Any]] = [
        deepcopy(item)
        for item in plan.get("result_scope_columns", [])
        if isinstance(item, dict)
    ] if isinstance(plan.get("result_scope_columns"), list) else []
    product_scope_fields = _append_product_term_scope_columns(scope_columns, metadata, question)
    for job in jobs:
        if not isinstance(job, dict):
            continue
        filters = job.get("filters") if isinstance(job.get("filters"), list) else []
        for condition in filters:
            if not isinstance(condition, dict):
                continue
            field = str(condition.get("field") or "").strip()
            if not field or field in {"DATE", "PRODUCT_GRAIN"}:
                continue
            if field in product_scope_fields:
                continue
            values = _scope_condition_values(condition)
            if field == "OPER_NAME":
                group_key = _process_group_key_for_scope(question, metadata, values)
                if group_key:
                    _append_scope_column(scope_columns, "OPER_GROUP", group_key, field)
                    continue
                if len(values) > 1:
                    continue
            if values:
                _append_scope_column(scope_columns, field, _scope_display_value(values), field)
    if scope_columns:
        plan["result_scope_columns"] = scope_columns


def _append_product_term_scope_columns(scope_columns: list[dict[str, Any]], metadata: dict[str, Any], question: str) -> set[str]:
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    terms = domain.get("product_terms") if isinstance(domain.get("product_terms"), dict) else {}
    raw_fields: set[str] = set()
    for term_key, term in terms.items():
        if not isinstance(term, dict):
            continue
        condition = term.get("condition") if isinstance(term.get("condition"), dict) else {}
        if not condition:
            continue
        aliases = term.get("aliases") if isinstance(term.get("aliases"), list) else []
        match_values = [term_key, term.get("display_name"), *aliases]
        if not _mentions_any(question, match_values):
            continue
        label = _matched_term_label(question, str(term_key), term)
        output_column = str(term.get("result_scope_column") or "PRODUCT_GROUP").strip()
        source_field = next((str(field) for field in condition if str(field or "").strip()), output_column)
        _append_scope_column(scope_columns, output_column, label, source_field)
        raw_fields.update(str(field) for field in condition if str(field or "").strip())
    return raw_fields


def _matched_term_label(question: str, term_key: str, term: dict[str, Any]) -> str:
    aliases = term.get("aliases") if isinstance(term.get("aliases"), list) else []
    candidates = [*aliases, term.get("display_name"), term_key]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and _alias_in_text(question, text):
            return _clean_scope_label(text)
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return _clean_scope_label(text)
    return term_key


def _clean_scope_label(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in (" 제품", "제품"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)].strip()
    return text


def _scope_condition_values(condition: dict[str, Any]) -> list[str]:
    if "value" in condition:
        return [str(condition.get("value") or "").strip()]
    values = condition.get("values")
    if isinstance(values, list):
        return [str(value or "").strip() for value in values if str(value or "").strip()]
    op = str(condition.get("op") or "").strip().lower()
    if op in {"not_empty", "exists"}:
        return ["NOT_EMPTY"]
    return []


def _process_group_key_for_scope(question: str, metadata: dict[str, Any], values: list[str]) -> str:
    if not values:
        return ""
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    groups = domain.get("process_groups") if isinstance(domain.get("process_groups"), dict) else {}
    value_set = {str(value or "").strip().upper() for value in values if str(value or "").strip()}
    for group_key, group in groups.items():
        if not isinstance(group, dict):
            continue
        processes = group.get("processes") if isinstance(group.get("processes"), list) else []
        process_set = {str(item or "").strip().upper() for item in processes if str(item or "").strip()}
        if value_set and value_set == process_set:
            return str(group_key)
        aliases = group.get("aliases") if isinstance(group.get("aliases"), list) else []
        match_values = [group_key, group.get("display_name"), *aliases]
        if value_set and value_set.issubset(process_set) and _mentions_any(question, match_values):
            return str(group_key)
    return ""


def _scope_display_value(values: list[str]) -> str:
    clean = [str(value or "").strip() for value in values if str(value or "").strip()]
    if len(clean) <= 1:
        return clean[0] if clean else ""
    if len(clean) <= 6:
        return ", ".join(clean)
    return ", ".join(clean[:6]) + f" ...(+{len(clean) - 6})"


def _append_scope_column(scope_columns: list[dict[str, Any]], column: str, value: Any, source_field: str) -> None:
    column_text = str(column or "").strip()
    value_text = str(value or "").strip()
    if not column_text or not value_text:
        return
    item = {"column": column_text, "value": value_text, "source_field": str(source_field or column_text)}
    signature = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    existing = {json.dumps(existing_item, ensure_ascii=False, sort_keys=True, default=str) for existing_item in scope_columns}
    if signature not in existing:
        scope_columns.append(item)


def _condition_for_dataset(term: dict[str, Any], dataset_key: str, dataset_catalog: dict[str, Any]) -> dict[str, Any]:
    overrides = term.get("condition_by_dataset") if isinstance(term.get("condition_by_dataset"), dict) else {}
    if dataset_key and isinstance(overrides.get(dataset_key), dict):
        return overrides[dataset_key]
    family_overrides = term.get("condition_by_family") if isinstance(term.get("condition_by_family"), dict) else {}
    family = str(dataset_catalog.get("dataset_family") or "")
    if family and isinstance(family_overrides.get(family), dict):
        return family_overrides[family]
    return term.get("condition") if isinstance(term.get("condition"), dict) else {}


def _condition_to_filters(condition: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for field, spec in condition.items():
        field_name = str(field or "").strip()
        if not field_name or not _metadata_has_filter(metadata, field_name):
            continue
        if isinstance(spec, dict):
            if spec.get("empty") or spec.get("missing_or_empty"):
                result.append({"field": field_name, "op": "empty"})
                continue
            if spec.get("exists") and spec.get("not_in"):
                result.append({"field": field_name, "op": "not_empty"})
                continue
            elif spec.get("exists"):
                result.append({"field": field_name, "op": "not_empty"})
            if isinstance(spec.get("starts_with"), str):
                result.append({"field": field_name, "op": "starts_with", "value": spec.get("starts_with")})
            if isinstance(spec.get("last_char_in"), list):
                result.append({"field": field_name, "op": "last_char_in", "values": deepcopy(spec["last_char_in"])})
            if isinstance(spec.get("in"), list):
                result.append({"field": field_name, "op": "in", "values": deepcopy(spec["in"])})
            if isinstance(spec.get("not_in"), list):
                result.append({"field": field_name, "op": "not_in", "values": deepcopy(spec["not_in"])})
            if "value" in spec:
                result.append({"field": field_name, "op": "eq", "value": spec.get("value")})
        elif isinstance(spec, list):
            result.append({"field": field_name, "op": "in", "values": deepcopy(spec)})
        else:
            result.append({"field": field_name, "op": "eq", "value": spec})
    return result


def _metadata_has_filter(metadata: dict[str, Any], filter_key: str) -> bool:
    filters = metadata.get("main_flow_filters") if isinstance(metadata.get("main_flow_filters"), dict) else {}
    return str(filter_key or "") in filters


def _catalog_has_filter(catalog: dict[str, Any], filter_key: str) -> bool:
    mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    return str(filter_key or "") in mappings


def _supports_product_grain_filter(catalog: dict[str, Any], plan: dict[str, Any]) -> bool:
    mappings = catalog.get("filter_mappings") if isinstance(catalog.get("filter_mappings"), dict) else {}
    product_grain = plan.get("product_grain") if isinstance(plan.get("product_grain"), list) else []
    return any(str(column or "") in mappings for column in product_grain)


def _drop_conflicting_product_alias_filters(
    filters: list[dict[str, Any]],
    inferred_filters: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    inferred_values = _filter_values(inferred_filters)
    if not inferred_values:
        return filters
    domain = metadata.get("domain_items") if isinstance(metadata.get("domain_items"), dict) else {}
    product_fields = set(domain.get("product_key_columns") or [])
    product_term_values = _product_term_alias_values(domain)
    inferred_fields = {str(item.get("field") or "") for item in inferred_filters if isinstance(item, dict)}
    inferred_keys = {json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) for item in inferred_filters}
    result = []
    for item in filters:
        field = str(item.get("field") or "")
        item_key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if item_key in inferred_keys or field not in product_fields or field in inferred_fields:
            result.append(item)
            continue
        if _filter_values([item]) & inferred_values:
            continue
        if _filter_values([item]) & product_term_values:
            continue
        result.append(item)
    return result


def _product_term_alias_values(domain: dict[str, Any]) -> set[str]:
    terms = domain.get("product_terms") if isinstance(domain.get("product_terms"), dict) else {}
    values: set[str] = set()
    for key, term in terms.items():
        if not isinstance(term, dict):
            continue
        for value in [key, term.get("display_name"), *(term.get("aliases") if isinstance(term.get("aliases"), list) else [])]:
            text = str(value or "").strip().upper()
            if text:
                values.add(text)
    return values


def _filter_values(filters: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for item in filters:
        if not isinstance(item, dict):
            continue
        if "value" in item:
            result.add(str(item.get("value") or "").upper())
        values = item.get("values")
        if isinstance(values, list):
            result.update(str(value or "").upper() for value in values)
    return {value for value in result if value}


def _normalize_date_filter(item: dict[str, Any], dataset_key: str, catalog: dict[str, Any]) -> None:
    if item.get("value"):
        item["value"] = _date_param(dataset_key, str(item["value"]), catalog)
    values = item.get("values")
    if isinstance(values, list):
        item["values"] = [_date_param(dataset_key, str(value), catalog) for value in values]


def _dedupe_filters(filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in filters:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _blocked_filter_fields(plan: dict[str, Any]) -> list[str]:
    return _as_recipe_text_list(plan.get("blocked_filter_fields"))


def _remove_filter_fields(filters: list[Any], blocked_fields: list[str]) -> list[dict[str, Any]]:
    blocked = {str(field or "").strip() for field in blocked_fields if str(field or "").strip()}
    if not blocked:
        return [deepcopy(item) for item in filters if isinstance(item, dict)]
    return [
        deepcopy(item)
        for item in filters
        if isinstance(item, dict) and str(item.get("field") or "").strip() not in blocked
    ]


def _as_recipe_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    result = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _mentions_any(question: str, aliases: list[Any]) -> bool:
    return any(_alias_in_text(question, alias) for alias in aliases)


def _alias_in_text(question: str, alias: Any) -> bool:
    text = str(question or "")
    value = str(alias or "").strip()
    if not value:
        return False
    if re.fullmatch(r"[A-Za-z0-9/.-]{1,4}", value):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return value in text or value.upper() in text.upper()


def _extract_lot_id(question: str) -> str:
    match = re.search(r"\b[A-Z0-9]{4,}[A-Z0-9_-]*\b", str(question or "").upper())
    return match.group(0) if match else ""


def _request_date(payload: dict[str, Any]) -> str:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    date_value = str(request.get("date") or request.get("request_date") or "").strip()
    if not date_value:
        date_value = _runtime_reference_date()
    return date_value.replace("-", "")


def _runtime_reference_date() -> str:
    try:
        zoneinfo = import_module("zoneinfo")
        return datetime.now(zoneinfo.ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    except Exception:
        return datetime.now().strftime("%Y%m%d")


def _date_value_for_job(
    question: str,
    dataset_key: str,
    catalog: dict[str, Any],
    job: dict[str, Any],
    request_date: str,
) -> str:
    text = " ".join(
        [
            str(question or ""),
            str(job.get("source_alias") or ""),
            str(job.get("purpose") or ""),
            str(dataset_key or ""),
            str(catalog.get("display_name") or ""),
        ]
    )
    family = str(catalog.get("dataset_family") or "")
    scope = str(catalog.get("date_scope") or "")
    mentions_yesterday = _mentions_any(text, ["어제", "전일", "yesterday", "previous day"])
    mentions_today = _mentions_any(text, ["오늘", "현재", "금일", "today", "current"])
    if mentions_yesterday:
        if "어제" in str(job.get("purpose") or "") or "yesterday" in str(job.get("purpose") or "").lower():
            return _shift_date(request_date, -1)
        if family == "production" and _mentions_any(question, ["어제", "전일", "yesterday"]):
            return _shift_date(request_date, -1)
        if not mentions_today:
            return _shift_date(request_date, -1)
    if mentions_today or scope == "current_day":
        return request_date
    return ""


def _shift_date(date_value: str, days: int) -> str:
    clean = str(date_value or "").replace("-", "")
    try:
        return (datetime.strptime(clean, "%Y%m%d") + timedelta(days=days)).strftime("%Y%m%d")
    except ValueError:
        return clean


def _date_param(dataset_key: str, request_date: str, catalog: dict[str, Any] | None = None) -> str:
    clean = str(request_date or "").replace("-", "")
    date_format = str((catalog or {}).get("date_format") or "")
    if (dataset_key == "target" or date_format == "YYYY-MM-DD") and len(clean) == 8:
        return f"{clean[0:4]}-{clean[4:6]}-{clean[6:8]}"
    return clean


def _append_once(values: list[str], message: str) -> None:
    if message not in values:
        values.append(message)


def _normalize_intent_type_for_analysis(plan: dict[str, Any], normalized_jobs: list[dict[str, Any]]) -> None:
    current = str(plan.get("intent_type") or "").strip()
    if current in {"finish", "followup_transform", "detail_lookup"}:
        return
    analysis_kind = str(plan.get("analysis_kind") or "").strip()
    job_count = len([job for job in normalized_jobs if isinstance(job, dict)])
    if analysis_kind == "aggregate_join" and job_count > 1:
        plan["intent_type"] = "multi_source_analysis"
        return
    if analysis_kind in {"rank_top_n", "aggregate_wip_total", "lot_count_by_process", "lot_quantity_summary", "equipment_by_model"} and job_count <= 1:
        plan["intent_type"] = "single_retrieval_analysis"


def _route_for_intent(intent_type: Any, job_count: int) -> str:
    text = str(intent_type or "").strip()
    if text == "finish":
        return "finish"
    if text == "followup_transform":
        return "followup_transform"
    if job_count > 1 or text in {"multi_source_analysis", "multi_step_analysis"}:
        return "multi_retrieval"
    return "single_retrieval"


def _metadata_context(intent_plan: dict[str, Any]) -> dict[str, Any]:
    dataset_keys = []
    filter_keys = []
    for job in intent_plan.get("retrieval_jobs", []):
        dataset_key = job.get("dataset_key")
        if dataset_key and dataset_key not in dataset_keys:
            dataset_keys.append(dataset_key)
        for condition in job.get("filters", []):
            if isinstance(condition, dict) and condition.get("field") and condition["field"] not in filter_keys:
                filter_keys.append(condition["field"])
    return {
        "domain_refs": _domain_refs(intent_plan),
        "table_refs": [{"dataset_key": key} for key in dataset_keys],
        "filter_refs": [{"filter_key": key} for key in filter_keys],
    }


def _domain_refs(intent_plan: dict[str, Any]) -> list[dict[str, Any]]:
    refs = [{"key": "product_grain", "columns": intent_plan.get("product_grain", [])}]
    if intent_plan.get("matched_analysis_recipe"):
        refs.append({"section": "analysis_recipes", "key": intent_plan["matched_analysis_recipe"]})
    return refs


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        for key in ("llm_text", "text", "content", "response"):
            if data.get(key):
                return str(data[key])
    for attr in ("text", "content"):
        if getattr(value, attr, None):
            return str(getattr(value, attr))
    return str(value)


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    data = getattr(value, "data", None)
    return dict(data) if isinstance(data, dict) else {}


def _unique(values: Any) -> list[str]:
    result = []
    if not isinstance(values, list):
        values = [values] if values else []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


# 컴포넌트 설명: 03 Intent Plan Normalizer
# Langflow 표시 설명: LLM의 의도 분석 JSON을 정규화해 조회 작업, 필터, pandas 분석 계획으로 변환합니다.
class IntentPlanNormalizer(Component):

    display_name = "03 Intent Plan Normalizer"
    description = "LLM의 의도 분석 JSON을 정규화해 조회 작업, 필터, pandas 분석 계획으로 변환합니다."
    inputs = [
        DataInput(name="payload", display_name="Payload", required=True),
        MessageTextInput(name="llm_response", display_name="LLM Response", required=True),
    ]
    outputs = [Output(name="payload_out", display_name="Payload", method="build_payload")]

    # 함수 설명: Langflow output 포트가 호출하는 메서드입니다.
    # 처리 역할: LLM의 의도 분석 JSON을 정규화해 조회 작업, 필터, pandas 분석 계획으로 변환합니다.
    # 반환 값은 다음 노드가 받을 수 있도록 Data 또는 Message 형태로 감쌉니다.
    def build_payload(self) -> Data:
        result = normalize_intent_payload(getattr(self, "payload", None), getattr(self, "llm_response", ""))

        plan = result.get("intent_plan", {})
        self.status = {
            "analysis_kind": plan.get("analysis_kind"),
            "jobs": len(plan.get("retrieval_jobs", [])),
            "errors": len(plan.get("normalizer_errors", [])),
        }
        return Data(data=result)
