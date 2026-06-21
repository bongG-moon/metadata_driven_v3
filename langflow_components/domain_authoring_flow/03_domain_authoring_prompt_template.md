You convert a refined manufacturing domain description into MongoDB-storable domain metadata.
Return one strict JSON object only. Do not wrap it in markdown.
Use only information present in the refined text. Put missing essentials in missing_information.
Prefer structured JSON conditions, for example {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}.
Use condition_by_dataset or condition_by_family when the same business term must use different physical filters by dataset.
For metric_terms, include required_quantity_terms and output_column when the text explains the needed measures or result name.
Use analysis_recipes when the text explains what kind of analysis plan should be built for a question pattern.
For analysis_recipes, keep group/grain as a policy such as question_or_product_grain instead of hardcoding one group-by column unless the text explicitly fixes it.
For multi-step analysis_recipes, preserve step_plan_template, required_columns_by_family, blocked_filter_fields, override_analysis_kinds, and replace/override flags when the text gives those details.
Use aggregation='nunique' for distinct LOT_ID counts. Do not use count_distinct.
Use aggregation='nunique' for equipment count questions such as 장비 대수 or 설비 대수 over EQPID, with output_column EQP_COUNT.
Distinguish equipment detail and count intents: 장비 현황 or 설비 현황 should be detail rows with result_mode='detail_rows', while 장비 대수 or 설비 대수 should calculate EQP_COUNT.

Authoring context:
{authoring_context}

Required JSON schema:
{{
  "items": [
    {{
      "section": "process_groups | product_terms | quantity_terms | metric_terms | status_terms | analysis_recipes | product_key_columns",
      "key": "stable_key",
      "payload": {{
        "display_name": "business display name",
        "aliases": ["business words"],
        "processes": ["optional for process_groups"],
        "condition": {{"optional": "structured condition"}},
        "condition_by_dataset": {{"dataset_key": {{"physical_column": "condition value or object"}}}},
        "condition_by_family": {{"dataset_family": {{"physical_column": "condition value or object"}}}},
        "dataset_key": "optional dataset key",
        "dataset_family": "optional dataset family",
        "quantity_column": "optional column",
        "aggregation": "sum | nunique | mean | max | min",
        "formula": "optional formula",
        "calculation_rule": "optional rule",
        "required_quantity_terms": ["optional quantity term keys needed by a metric"],
        "required_dataset_families": ["optional dataset families needed by an analysis recipe"],
        "metric_terms": ["optional metric term keys used by an analysis recipe"],
        "intent_type": "optional intended intent type",
        "default_analysis_kind": "optional supported analysis_kind",
        "grain_policy": "optional, e.g. question_or_product_grain | aggregate_total | explicit",
        "source_aliases_by_family": {{"dataset_family": "optional source alias"}},
        "required_columns_by_family": {{"dataset_family": ["optional required source columns"]}},
        "override_analysis_kinds": ["optional analysis kinds this recipe may replace"],
        "blocked_filter_fields": ["optional filters to remove from retrieval and use only as calculation conditions"],
        "step_plan_template": [{{"step_id": "optional multi-step plan template"}}],
        "replace_datasets": "optional boolean",
        "replace_retrieval_jobs": "optional boolean",
        "override_step_plan": "optional boolean",
        "top_n_policy": "optional, e.g. question_or_default",
        "result_mode": "optional, e.g. detail_rows",
        "output_columns": ["optional standard output columns"],
        "output_column": "optional standard output column"
      }},
      "columns": ["only for product_key_columns"],
      "confidence": "high | medium | low"
    }}
  ],
  "missing_information": [
    {{"field": "field name", "reason": "Korean reason", "example_user_input": "Korean example"}}
  ],
  "warnings": ["Korean warning"]
}}
