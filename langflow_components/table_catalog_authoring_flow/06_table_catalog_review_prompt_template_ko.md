MongoDB 저장 전에 table catalog metadata를 검수하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
실무적으로 판단하고 지나치게 엄격하게 막지 마세요. dataset을 조회할 수 없거나 필수 field가 없거나 중복 처리 선택이 필요한 경우에만 차단하세요.
default_detail_columns는 선택 사항입니다. columns가 있으면 default_detail_columns가 없다는 이유만으로 저장을 막지 마세요.
source_type이 goodocs이면 doc_id가 필수입니다. sheet_name, db_key, query_template은 필수가 아니며 sheet_name은 특정 sheet/tab을 알고 있을 때만 선택 사항입니다.
required_params가 비어 있는데 DATE가 filter_mappings에 있으면 DATE를 누락된 필수 parameter가 아니라 optional filter로 판단하세요.
filter_mappings의 왼쪽은 표준 filter key이므로 최종 SELECT columns에 직접 존재할 필요가 없습니다.
payload.columns 또는 standard_column_aliases 안에 오른쪽 물리 mapping column이 하나 이상 있으면 정상으로 판단하세요. DEN, PKG_TYPE1, MCP_NO 같은 표준 key가 DENSITY, PKG1, MCPSALENO 같은 물리 column과 다르다는 이유만으로 저장을 막지 마세요.
query_template의 `--` line comment와 `/* ... */` block comment 안 텍스트는 컬럼명이 아닙니다. 주석 처리된 column이 payload.columns에 없다는 이유로 저장을 막지 마세요.
비개발 제조 업무 사용자가 이해할 수 있도록 보강 요청은 한국어로 설명하세요.

검수 input:
{review_input_json}

필수 JSON schema:
{{
  "ready_to_save": false,
  "summary": "한국어 요약",
  "supplement_requests": [
    {{"field": "field", "reason": "한국어 사유", "example_user_input": "한국어 예시 입력"}}
  ],
  "item_reviews": [
    {{"dataset_key": "key", "decision": "pass | needs_fix", "reason": "한국어 사유"}}
  ]
}}
