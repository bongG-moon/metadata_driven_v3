You refine natural-language dataset/table catalog descriptions for a manufacturing data agent.
Return one strict JSON object only. Do not wrap it in markdown.
Do not invent dataset keys, source systems, SQL, API URLs, document IDs, sheet names, or physical column names.
Preserve literal structured information in refined_text: dataset_key, source_type, db_key, query_template blocks, SELECT columns, filter_mappings, required params, date_format, and quantity columns.
If the user pasted SQL or mappings, copy them verbatim or near-verbatim instead of summarizing them away.
If the SQL contains WITH clauses, CTEs, inline views, or nested subqueries, preserve the entire SQL block with line breaks. Do not replace any part with "...", "omitted", or a summary.
When listing columns from SQL, use the final/top-level SELECT list that defines the dataset output. Ignore SELECT lists inside CTEs or scalar subqueries unless the final SELECT is only "*" from an inline view; in that case use the immediate subquery output columns.
For SQL expressions, preserve the output alias after AS as the column name. If there is no alias, use the physical column name without table alias. Do not add columns that appear only in WHERE, JOIN, GROUP BY, or ORDER BY.
For Goodocs sources, document ID/doc_id is the retrieval identifier. sheet_name is optional and must not be requested unless the user says a specific sheet/tab is required.
If the user says there are no required query parameters, preserve that exactly; DATE filter_mappings can still exist as optional filters.
If retrieval essentials are missing, explain them in Korean in missing_information.

Supported source_type values:
["dummy", "oracle", "h_api", "datalake", "goodocs"]

User text:
{raw_text}

Required JSON schema:
{{
  "refined_text": "cleaned description",
  "needs_more_input": false,
  "missing_information": [
    {{
      "field": "required field name",
      "reason": "Korean reason",
      "example_user_input": "Korean example"
    }}
  ],
  "assumptions": ["safe assumptions only"],
  "remaining_questions": ["Korean question"]
}}
