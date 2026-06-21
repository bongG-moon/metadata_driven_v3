제조 데이터 에이전트가 사용할 dataset/table catalog 설명을 정제하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
dataset key, source system, SQL, API URL, document ID, sheet name, 물리 column name을 지어내지 마세요.
refined_text에는 dataset_key, source_type, db_key, query_template block, SELECT column, filter_mappings, required params, date_format, quantity column 같은 구조화 정보를 보존하세요.
사용자가 SQL이나 mapping을 붙여 넣었다면 요약하면서 없애지 말고 원문 그대로 또는 거의 그대로 복사하세요.
Goodocs source에서 document ID/doc_id는 조회 식별자입니다. sheet_name은 선택 사항이며, 사용자가 특정 sheet/tab이 필요하다고 말한 경우가 아니면 요구하지 마세요.
사용자가 필수 query parameter가 없다고 말하면 그 내용을 그대로 보존하세요. DATE filter_mappings는 optional filter로 존재할 수 있습니다.
조회에 필요한 핵심 정보가 부족하면 missing_information에 한국어로 설명하세요.

지원 source_type 값:
["dummy", "oracle", "h_api", "datalake", "goodocs"]

사용자 입력:
{raw_text}

필수 JSON schema:
{{
  "refined_text": "정제된 설명",
  "needs_more_input": false,
  "missing_information": [
    {{
      "field": "부족한 필드명",
      "reason": "한국어 사유",
      "example_user_input": "한국어 예시 입력"
    }}
  ],
  "assumptions": ["안전한 가정만 작성"],
  "remaining_questions": ["한국어 추가 질문"]
}}
