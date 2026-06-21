제조 데이터 에이전트가 사용할 filter/parameter 설명을 정제하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
물리 column name, normalized format, value mapping, operator를 지어내지 마세요.
filter를 아직 조회/분석에 사용할 수 없다면 부족한 정보를 missing_information에 한국어로 설명하세요.

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
