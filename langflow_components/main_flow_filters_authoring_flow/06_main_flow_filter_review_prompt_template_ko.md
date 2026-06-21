MongoDB 저장 전에 main flow filter metadata를 검수하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
실무적으로 판단하고 지나치게 엄격하게 막지 마세요. filter가 사용자 용어를 column/parameter로 매핑할 수 없거나 필수 field가 없거나 중복 처리 선택이 필요한 경우에만 차단하세요.
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
    {{"filter_key": "key", "decision": "pass | needs_fix", "reason": "한국어 사유"}}
  ]
}}
