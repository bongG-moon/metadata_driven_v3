정제된 filter/parameter 설명을 MongoDB에 저장 가능한 main_flow_filters metadata로 변환하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
정제된 설명에 있는 정보만 사용하세요. 필수 정보가 부족하면 missing_information에 넣으세요.
이 filter들은 main agent가 사용자 표현을 조회 parameter, 물리 column, pandas filter로 매핑하는 데 사용됩니다.
runtime normalization이 date/process/product/status/equipment filter를 구분할 때 semantic_role을 사용하므로 일관되게 작성하세요.
사용자 업무 표현과 저장 값이 다르면 sample_values 또는 value_mappings를 포함하세요.
정제 설명에 known_values, value_aliases, columns, process_name, between 같은 이전 명칭이 있으면 현재 schema의 sample_values, value_mappings, column_candidates, process/generic semantic_role, range로 변환하세요.
filter_key는 table_catalog.filter_mappings가 참조할 수 있는 안정적인 표준 key여야 합니다. 이미 표준 key가 있으면 dataset별 물리 key를 새로 만들지 마세요.
이 metadata는 dataset-neutral하게 유지하세요. main_flow_filters.column_candidates는 넓은 후보 column name만 담습니다. PKG_TYPE1->PKG1 또는 MCP_NO->MCPSALENO 같은 dataset-specific mapping은 table_catalog.filter_mappings에 넣어야 합니다.
main_flow_filter item 안에는 table_catalog filter_mappings, source_type, query_template, document ID, DB key를 넣지 마세요.

작성 context:
{authoring_context}

필수 JSON schema:
{{
  "items": [
    {{
      "filter_key": "stable_filter_key",
      "payload": {{
        "display_name": "업무 표시명",
        "aliases": ["업무 용어"],
        "column_candidates": ["physical columns"],
        "semantic_role": "date | process | product | lot | status | equipment | generic",
        "value_type": "date | string | number | code",
        "value_shape": "scalar | list | range",
        "operator": "eq | in | not_empty | tuple_in | range",
        "normalized_format": "선택적 값, 예: YYYYMMDD",
        "required_params": ["선택적 retrieval params"],
        "sample_values": ["선택적 저장 값"],
        "value_mappings": {{"optional user value": "system value"}}
      }},
      "confidence": "high | medium | low"
    }}
  ],
  "missing_information": [
    {{"field": "필드명", "reason": "한국어 사유", "example_user_input": "한국어 예시 입력"}}
  ],
  "warnings": ["한국어 경고"]
}}
