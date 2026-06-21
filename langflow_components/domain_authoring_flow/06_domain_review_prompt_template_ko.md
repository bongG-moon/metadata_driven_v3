MongoDB 저장 전에 domain metadata를 검수하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
실무적으로 판단하고 지나치게 엄격하게 막지 마세요. 필수 정보가 없거나 JSON을 사용할 수 없거나 중복 처리 선택이 필요한 경우에만 차단하세요.
duplicate_decision.requires_user_choice가 false이거나 duplicate_decision.action이 이미 merge, replace, skip, create_new 중 하나이면 duplicate_decision.message를 요구하지 마세요.
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
    {{"section": "section", "key": "key", "decision": "pass | needs_fix", "reason": "한국어 사유"}}
  ]
}}
