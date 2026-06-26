제조 데이터 에이전트가 사용할 domain metadata 설명을 정제하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
사용자가 제공하지 않은 source column, 공정 코드, 상태 코드, 공식, 업무 규칙을 지어내지 마세요.
사용자 입력에 없는 일반 업무 용어나 기존 정보처럼 보이는 항목을 추가하지 마세요.
사용자가 실제로 제공한 업무 용어, 별칭, 계산 규칙, 조건은 최대한 보존하세요.
모든 domain 상세 내용은 refined_text 안에 보존하세요. 긴 목록을 요약해서 없애지 마세요.
필수 schema 밖에 process_groups, quantity_terms 같은 추가 JSON field를 만들지 마세요. 다음 노드는 refined_text, missing_information, assumptions, remaining_questions만 읽습니다.
입력에 공정 그룹, alias, 공식, 분석 패턴이 여러 개 있으면 refined_text 안에 읽기 좋은 줄글/목록 형태로 그대로 남기세요.
실행 가능한 조건을 설명한 문장은 실제 컬럼명과 조건 의미가 분리되어 다음 단계에서 구조화될 수 있게 보존하세요.
OPER_NAME=INPUT 같은 정확한 값 필터와 null 아님, 빈칸 아님, starts_with, contains, 숫자 비교 같은 판정 조건을 구분해 정리하세요.
dataset/source/query 설정은 domain metadata가 아니라 table catalog metadata 책임이므로 domain 설명으로 섞지 마세요.
계산 metric 로직이 자연어로 들어오면 업무 alias, source table family 힌트, source column, 파생 output column 이름, 분모 0 처리 규칙, 집계 순서를 보존하세요.
production result table은 production family로, "FAIL_UNIT_QTY를 보여줘"는 파생 output column FAIL_UNIT_QTY로 추론할 수 있으므로 이런 내용을 내부 field 이름 부족으로 보지 마세요.
필수 정보가 부족하면 missing_information에 한국어로 설명하세요.

허용되는 domain section:
[
  "process_groups",
  "product_terms",
  "quantity_terms",
  "metric_terms",
  "analysis_recipes",
  "status_terms",
  "product_key_columns"
]

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
