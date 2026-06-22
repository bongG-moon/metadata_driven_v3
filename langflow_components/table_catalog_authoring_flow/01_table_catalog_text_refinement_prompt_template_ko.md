제조 데이터 에이전트가 사용할 dataset/table catalog 설명을 정제하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
dataset key, source system, SQL, API URL, document ID, sheet name, 물리 column name을 지어내지 마세요.
refined_text에는 dataset_key, source_type, db_key, query_template block, SELECT column, filter_mappings, required params, date_format, quantity column 같은 구조화 정보를 보존하세요.
사용자가 SQL이나 mapping을 붙여 넣었다면 요약하면서 없애지 말고 원문 그대로 또는 거의 그대로 복사하세요.
query_template SQL은 실행용 원문이므로 불투명한 텍스트처럼 다루세요. comma, underscore, 식별자 내부 공백, alias, table name, column name, placeholder, comment를 추가/삭제/수정하지 마세요.
table/column spelling을 임의로 교정하지 마세요. 예를 들어 DATA_EXTINF_MAS를 DATA_EXT_INF_MAS로 바꾸거나 PKG_TYPE1, PKG_TYPE2를 PKG_TYPE1,, PKG_TYPE2처럼 바꾸면 안 됩니다.
SQL에 WITH 절, CTE, inline view, nested subquery가 있으면 전체 SQL block과 줄바꿈을 보존하세요. 어떤 부분도 "...", "생략", 요약 표현으로 바꾸지 마세요.
SQL에서 columns를 적을 때는 dataset output을 만드는 최종/top-level SELECT 목록을 기준으로 하세요. CTE 내부 SELECT나 scalar subquery 내부 SELECT는 제외하세요. 단, 최종 SELECT가 inline view에서 "*"만 선택하는 구조라면 해당 inline view의 출력 column을 사용하세요.
SQL expression은 AS 뒤의 출력 alias를 column name으로 보존하세요. alias가 없으면 table alias를 제거한 실제 물리 column name을 사용하세요. WHERE, JOIN, GROUP BY, ORDER BY에만 등장하는 column은 columns에 추가하지 마세요.
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
