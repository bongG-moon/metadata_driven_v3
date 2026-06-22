정제된 제조 domain 설명을 MongoDB에 저장 가능한 domain metadata로 변환하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
정제된 설명에 있는 정보만 사용하세요. 필수 정보가 부족하면 missing_information에 넣으세요.
조건은 가능한 한 구조화된 JSON으로 표현하세요. 예: {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}.
실행에 쓰이는 필터 조건을 자연어 문장으로 저장하지 마세요. 컬럼 판정은 condition object로, 정확한 값 매칭은 filters object로 저장하세요.
descriptor 형태 입력은 실행 가능한 구조로 변환하세요. 예: {{"column": "TSV_DIE_TYP", "condition": "not null and not empty"}}는 {{"condition": {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}}}가 됩니다.
공정값이나 상태값처럼 정확히 일치해야 하는 값은 문장 대신 {{"filters": {{"OPER_NAME": ["INPUT"]}}}} 같은 구조로 저장하세요.
같은 업무 용어가 dataset별 또는 dataset_family별로 다른 물리 필터를 사용해야 하면 condition_by_dataset 또는 condition_by_family를 사용하세요.
metric_terms에는 텍스트가 필요한 수량이나 결과명을 설명하는 경우 required_quantity_terms와 output_column을 포함하세요.
질문 패턴에 따라 어떤 분석 계획을 만들어야 하는지 설명되어 있으면 analysis_recipes를 사용하세요.
analysis_recipes에서는 텍스트가 특정 group-by column을 명시하지 않는 한 group/grain을 고정하지 말고 question_or_product_grain 같은 policy로 유지하세요.
multi-step analysis_recipes에서는 텍스트가 해당 세부 정보를 제공하면 step_plan_template, required_columns_by_family, blocked_filter_fields, override_analysis_kinds, replace/override flag를 보존하세요.
LOT_ID distinct count는 aggregation='nunique'를 사용하세요. count_distinct는 사용하지 마세요.
장비 대수 또는 설비 대수처럼 EQPID 기준의 distinct 장비 수를 묻는 항목은 aggregation='nunique'와 output_column EQP_COUNT를 사용하세요.
장비 현황/설비 현황과 장비 대수/설비 대수를 구분하세요. 장비 현황/설비 현황은 result_mode='detail_rows' 상세 행이고, 장비 대수/설비 대수는 EQP_COUNT를 계산합니다.

작성 context:
{authoring_context}

필수 JSON schema:
{{
  "items": [
    {{
      "section": "process_groups | product_terms | quantity_terms | metric_terms | status_terms | analysis_recipes | product_key_columns",
      "key": "stable_key",
      "payload": {{
        "display_name": "업무 표시명",
        "aliases": ["업무 용어"],
        "processes": ["process_groups에서 선택적으로 사용"],
        "condition": {{"optional": "구조화된 조건"}},
        "condition_by_dataset": {{"dataset_key": {{"physical_column": "condition value or object"}}}},
        "condition_by_family": {{"dataset_family": {{"physical_column": "condition value or object"}}}},
        "dataset_key": "선택적 dataset key",
        "dataset_family": "선택적 dataset family",
        "quantity_column": "선택적 수량 컬럼",
        "aggregation": "sum | nunique | mean | max | min",
        "formula": "선택적 공식",
        "calculation_rule": "선택적 계산 규칙",
        "required_quantity_terms": ["metric에 필요한 quantity term key"],
        "required_dataset_families": ["analysis recipe에 필요한 dataset family"],
        "metric_terms": ["analysis recipe가 사용하는 metric term key"],
        "intent_type": "선택적 intent type",
        "default_analysis_kind": "선택적 supported analysis_kind",
        "grain_policy": "선택적 값, 예: question_or_product_grain | aggregate_total | explicit",
        "source_aliases_by_family": {{"dataset_family": "선택적 source alias"}},
        "required_columns_by_family": {{"dataset_family": ["선택적 필수 source column"]}},
        "override_analysis_kinds": ["이 recipe가 대체할 수 있는 analysis kind"],
        "blocked_filter_fields": ["조회 필터에서 제거하고 계산 조건으로만 쓸 filter"],
        "step_plan_template": [{{"step_id": "선택적 multi-step plan template"}}],
        "replace_datasets": "선택적 boolean",
        "replace_retrieval_jobs": "선택적 boolean",
        "override_step_plan": "선택적 boolean",
        "top_n_policy": "선택적 값, 예: question_or_default",
        "result_mode": "선택적 값, 예: detail_rows",
        "output_columns": ["선택적 표준 output column"],
        "output_column": "선택적 표준 output column"
      }},
      "columns": ["product_key_columns에서만 사용"],
      "confidence": "high | medium | low"
    }}
  ],
  "missing_information": [
    {{"field": "필드명", "reason": "한국어 사유", "example_user_input": "한국어 예시 입력"}}
  ],
  "warnings": ["한국어 경고"]
}}
