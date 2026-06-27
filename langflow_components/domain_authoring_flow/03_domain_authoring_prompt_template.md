You convert a refined manufacturing domain description into MongoDB-storable domain metadata.
Return one strict JSON object only. Do not wrap it in markdown.
Use only information present in the refined text. Put missing essentials in missing_information.
The authoring context contains existing domain metadata, table catalog metadata, and main flow filter metadata.
Use existing domain metadata only to choose an existing key or detect duplicate/update intent; do not create unrelated items just because they appear in the existing summary.
Every generated item must be directly grounded in the refined text. If a key, alias, process value, formula, or question pattern appears only in the existing summary but not in the refined text, do not create that item.
Use table catalog metadata to infer dataset_family, source columns, and table wording when the worker says things like production table, ASSIGN table, target/schedule table, WIP table, or names a known column.
Use main flow filter metadata to infer standard field names from physical columns or worker wording, but do not create main_flow_filter items in this domain flow.
For reusable domain rules, prefer dataset_family/source_columns over a concrete dataset_key unless the worker explicitly names one dataset.
Prefer structured JSON conditions, for example {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}.
Do not store executable filters as prose. Use condition objects for column predicates and filters objects for exact value matches.
For descriptor-style input, convert it to executable form: {{"column": "TSV_DIE_TYP", "condition": "not null and not empty"}} becomes {{"condition": {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}}}.
For exact process or status values, use filters such as {{"filters": {{"OPER_NAME": ["INPUT"]}}}} instead of a sentence.
For process_groups, put the actual OPER_NAME values in processes. If the worker says "OPER_NAME value is S/G", create processes=["S/G"], not processes=[] with a condition.
Do not use process_groups for grouping-axis rules such as "세부공정별" or "차수별로 보여줘"; use analysis_recipes for reusable analysis/grain rules.
For field-alias rules where the user asks to show a specific output column, such as DEVICE code, device suffix, or description, use analysis_recipes rather than product_key_columns. Use product_key_columns only when the worker explicitly defines product keys or join keys.
Use condition_by_dataset or condition_by_family when the same business term must use different physical filters by dataset.
For metric_terms, include required_quantity_terms and output_column when the text explains the needed measures or result name.
For metric_terms, if the text clearly names source columns/formula and a source family can be inferred from table catalog context, do not ask for dataset_key.
For quantity_terms, if the text says a metric is a unique count over a column in a table family, infer aggregation='nunique', quantity_column/source_columns, dataset_family, and let the output_column be generated from the business term when not explicitly given.
For metric_terms, infer reusable dataset intent from common business words when the source is clear:
production table, production result table, 생산량 조회 테이블, 생산 실적, 생산량 조회 means dataset_family='production' and required_quantity_terms=['production'].
If a metric only depends on one dataset family, dataset_key is optional; prefer dataset_family or required_dataset_families so current/history datasets can still be selected by date scope.
When the text names source columns such as PRODUCTION or NETDIE_300_CNT, preserve them in source_columns even if the worker did not write source_columns explicitly.
When the text says to create/show a derived column such as FAIL_UNIT_QTY, store it in output_columns or output_column. Do not ask for a data type unless the same output name is ambiguous.
For conditional division metrics, preserve zero/null denominator handling, fail/output columns, and whether the calculation is row-level before aggregation or aggregate-first.
Use analysis_recipes when the text explains what kind of analysis plan should be built for a question pattern.
For analysis_recipes, keep group/grain as a policy such as question_or_product_grain instead of hardcoding one group-by column unless the text explicitly fixes it.
For multi-step analysis_recipes, preserve step_plan_template, required_columns_by_family, blocked_filter_fields, override_analysis_kinds, and replace/override flags when the text gives those details.
If an analysis recipe describes a reusable interpretation rule that does not fit step_plan_template, preserve it in calculation_rule or pandas_generation_rule and save it. Do not block it just because there is no specialized internal field.
Use pandas_function_cases when the text describes a reusable helper-function case for pandas code generation, especially procedural matching or parsing logic that is too specific to reliably infer from ordinary intent fields.
For pandas_function_cases, save only the helper selection hints such as function_name, use_when, token/source/output columns, and short pandas_code_instructions. Do not save large helper implementations in MongoDB/domain authoring raw text; put actual helper/reference code in the 14 Pandas Prompt Builder / 15 Pandas Code Executor Specialized Functions inputs or an explicit external helper package.
Use aggregation='nunique' for distinct LOT_ID counts. Do not use count_distinct.
Use aggregation='nunique' for equipment count questions such as 장비 대수 or 설비 대수 over EQPID, with output_column EQP_COUNT.
Distinguish equipment detail and count intents: 장비 현황 or 설비 현황 should be detail rows with result_mode='detail_rows', while 장비 대수 or 설비 대수 should calculate EQP_COUNT.

Authoring context:
{authoring_context}

Required JSON schema:
{{
  "items": [
    {{
      "section": "process_groups | product_terms | quantity_terms | metric_terms | status_terms | analysis_recipes | pandas_function_cases | product_key_columns",
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
        "output_column": "optional standard output column",
        "function_name": "optional helper function name for pandas_function_cases",
        "use_when": "optional plain-language activation rule for pandas_function_cases",
        "input_text": "optional expression source for pandas_function_cases",
        "required_source_columns": ["optional source columns needed by pandas_function_cases"],
        "token_columns": ["optional token-match columns for pandas_function_cases"],
        "output_order": ["optional output order for pandas_function_cases"],
        "pandas_code_instructions": ["optional short usage hints for generated pandas code"]
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
