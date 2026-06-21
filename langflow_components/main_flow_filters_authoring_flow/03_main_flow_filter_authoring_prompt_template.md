You convert a refined filter/parameter description into MongoDB-storable main_flow_filters metadata.
Return one strict JSON object only. Do not wrap it in markdown.
Use only information present in the refined text. Put missing essentials in missing_information.
These filters help the main agent map user words to retrieval params, physical columns, and pandas filters.
Use semantic_role consistently because runtime normalization uses it to distinguish date/process/product/status/equipment filters.
Include sample_values or value_mappings when business words differ from stored values.
Keep this metadata dataset-neutral. main_flow_filters.column_candidates are broad candidate column names only; dataset-specific mappings such as PKG_TYPE1->PKG1 or MCP_NO->MCPSALENO belong in table_catalog.filter_mappings.
Do not include table_catalog filter_mappings, source_type, query_template, document ID, or DB key in main_flow_filter items.

Authoring context:
{authoring_context}

Required JSON schema:
{{
  "items": [
    {{
      "filter_key": "stable_filter_key",
      "payload": {{
        "display_name": "business display name",
        "aliases": ["business words"],
        "column_candidates": ["physical columns"],
        "semantic_role": "date | process | product | lot | status | equipment | generic",
        "value_type": "date | string | number | code",
        "value_shape": "scalar | list | range",
        "operator": "eq | in | not_empty | tuple_in | range",
        "normalized_format": "optional, e.g. YYYYMMDD",
        "required_params": ["optional retrieval params"],
        "sample_values": ["optional stored values"],
        "value_mappings": {{"optional user value": "system value"}}
      }},
      "confidence": "high | medium | low"
    }}
  ],
  "missing_information": [
    {{"field": "field name", "reason": "Korean reason", "example_user_input": "Korean example"}}
  ],
  "warnings": ["Korean warning"]
}}
