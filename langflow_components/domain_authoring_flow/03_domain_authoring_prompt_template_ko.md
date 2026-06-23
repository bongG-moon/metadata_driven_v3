정제된 제조 domain 설명을 MongoDB에 저장 가능한 domain metadata로 변환하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
정제된 설명에 있는 정보만 사용하세요. 필수 정보가 부족하면 missing_information에 넣으세요.
작업자는 업무 로직을 느슨한 자연어로 설명할 수 있습니다. source table/dataset, source column, 집계 표현, 계산 의도가 명확하면 재사용 가능한 metadata로 추론하세요.
output_column이 없다는 이유만으로 막지 마세요. 의미가 명확하면 업무 용어에서 안정적인 대문자 output column을 생성하세요.
"중복 제거 값 수", "distinct count", "unique count", "중복 없이 센다" 같은 표현은 aggregation='nunique'로 작성하고, 언급된 source column을 quantity_column으로 사용하세요.
assign table처럼 특정 table이 언급되면 명시된 table/dataset 이름을 dataset_key로 보존하세요.
"장비 대수는 assign테이블에서 eqp_id컬럼 중복 제거 값 수" 같은 장비 count 설명은 quantity_terms/equipment_count로 작성하거나 갱신하고 dataset_family='equipment', 언급된 quantity_column, aggregation='nunique', output_column='EQP_COUNT'를 사용하세요.
authoring_context의 기존 item 요약은 중복 확인용 참고 정보일 뿐입니다. 정제된 설명이 명시적으로 해당 항목 수정을 요청하지 않으면 기존 요약을 새 item으로 변환하지 마세요.
정제된 설명이 기존 업무 수량의 alias, dataset family, source column, target 제외 규칙만 보강하는 내용이면 하나의 quantity_terms item으로 작성하고, 기존 요약에 있는 key를 우선 사용하세요.
INPUT실적, INPUT생산량, 투입 실적 같은 표현은 quantity_terms key input_production으로 작성하고 dataset_family='production', quantity_column='PRODUCTION', aggregation='sum'을 사용하세요. 이 설명만으로 product_key_columns, process_groups, metric_terms를 만들지 마세요.
계획/스케쥴 문자가 없으면 target을 쓰지 말라는 설명은 target metric을 새로 만들지 말고 quantity term의 excluded_terms 또는 selection_rule로 보존하세요.
조건은 가능한 한 구조화된 JSON으로 표현하세요. 예: {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}.
실행에 쓰이는 필터 조건을 자연어 문장으로 저장하지 마세요. 컬럼 판정은 condition object로, 정확한 값 매칭은 filters object로 저장하세요.
descriptor 형태 입력은 실행 가능한 구조로 변환하세요. 예: {{"column": "TSV_DIE_TYP", "condition": "not null and not empty"}}는 {{"condition": {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}}}가 됩니다.
공정값이나 상태값처럼 정확히 일치해야 하는 값은 문장 대신 {{"filters": {{"OPER_NAME": ["INPUT"]}}}} 같은 구조로 저장하세요.
같은 업무 용어가 dataset별 또는 dataset_family별로 다른 물리 필터를 사용해야 하면 condition_by_dataset 또는 condition_by_family를 사용하세요.
metric_terms에는 텍스트가 필요한 수량이나 결과명을 설명하는 경우 required_quantity_terms와 output_column을 포함하세요.
metric_terms에서는 source가 명확하면 작업자가 내부 필드를 모두 쓰지 않아도 재사용 가능한 dataset 의도를 추론하세요.
production table, production result table, 생산량 조회 테이블, 생산 실적, 생산량 조회는 dataset_family='production' 및 required_quantity_terms=['production']로 해석하세요.
하나의 dataset family만 쓰는 metric은 dataset_key가 선택 사항입니다. 현재/이력 dataset은 날짜 범위에 따라 고를 수 있도록 dataset_family 또는 required_dataset_families를 우선 사용하세요.
PRODUCTION, NETDIE_300_CNT처럼 사용자가 source column을 직접 말하면 source_columns에 보존하세요.
FAIL_UNIT_QTY처럼 새로 만들어 옆에 보여주라는 파생 column은 output_columns 또는 output_column에 저장하세요. output 이름이 모호하지 않으면 data type을 추가로 요구하지 마세요.
조건부 나눗셈 metric은 분모 0/null 처리, 실패 수량 column, 출력 column, 행별 계산 후 집계인지 먼저 집계 후 계산인지 보존하세요.
질문 패턴에 따라 어떤 분석 계획을 만들어야 하는지 설명되어 있으면 analysis_recipes를 사용하세요.
analysis_recipes에서는 텍스트가 특정 group-by column을 명시하지 않는 한 group/grain을 고정하지 말고 question_or_product_grain 같은 policy로 유지하세요.
multi-step analysis_recipes에서는 텍스트가 해당 세부 정보를 제공하면 step_plan_template, required_columns_by_family, blocked_filter_fields, override_analysis_kinds, replace/override flag를 보존하세요.
LOT_ID distinct count는 aggregation='nunique'를 사용하세요. count_distinct는 사용하지 마세요.
장비 대수 또는 설비 대수처럼 EQPID 기준의 distinct 장비 수를 묻는 항목은 aggregation='nunique'와 output_column EQP_COUNT를 사용하세요.
장비 현황/설비 현황과 장비 대수/설비 대수를 구분하세요. 장비 현황/설비 현황은 result_mode='detail_rows' 상세 행이고, 장비 대수/설비 대수는 EQP_COUNT를 계산합니다.

제품 단어나 제품 속성 일부 조합을 매칭하는 pandas 코드 생성 규칙을 설명한 경우 product_attribute_resolvers를 사용하세요. 이 규칙은 별도 lookup/master dataset을 요구하지 말고, 이미 조회된 source DataFrame 안의 실제 컬럼/alias 컬럼 값을 비교해 pandas 필터를 만드는 방법을 설명해야 합니다. POP, MOBILE처럼 이름이 있는 특화 제품군은 product_terms로 유지하고 일반 제품 속성 매칭보다 먼저 확인되는 규칙으로 봅니다.
product_attribute_resolvers에서는 `standard_attribute_columns`를 쓰지 말고 `attribute_columns`와 `output_filter_columns`를 사용하세요.
product_attribute_resolvers의 컬럼, trigger 표현, source policy, 매칭 방식, prefix 규칙은 작업자가 설명한 내용이나 기존 authoring context에 있는 내용만 구조화하세요. 코드나 프롬프트가 업무 컬럼이나 제품 코드 규칙을 새로 만들어 넣지 마세요.
작업자가 특정 컬럼의 접두 매칭을 설명한 경우에만 `pandas_generation_rule.prefix_match_columns`에 저장하세요. 설명이 없으면 prefix 규칙은 비우거나 생략하세요.
작업자가 이미 조회된 데이터만 사용한다고 설명하면 `source_policy`에 보존하세요. 별도 lookup/master dataset 조회는 작업자가 명시적으로 요청한 경우에만 만드세요.

작성 context:
{authoring_context}

필수 JSON schema:
{{
  "items": [
    {{
      "section": "process_groups | product_terms | product_attribute_resolvers | quantity_terms | metric_terms | status_terms | analysis_recipes | product_key_columns",
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
        "output_column": "선택적 표준 output column",
        "trigger_terms": ["product_attribute_resolvers에서 resolver를 활성화할 질문 표현"],
        "attribute_columns": ["product_attribute_resolvers에서 runtime 매칭에 쓸 표준 컬럼"],
        "attribute_source_columns": {{"standard_column": ["선택적 물리/source alias"]}},
        "output_filter_columns": ["product_attribute_resolvers에서 pandas 필터로 적용할 표준 컬럼"],
        "resolution_stage": "선택적 stage, 작업자가 pandas 코드 생성을 설명한 경우 예: pandas_code_generation",
        "source_policy": {{"use_existing_runtime_sources_only": "작업자 설명 기반 선택 boolean", "do_not_add_retrieval_job": "작업자 설명 기반 선택 boolean"}},
        "pandas_generation_rule": {{"prefix_match_columns": {{"작업자가_말한_컬럼": {{"pattern": "작업자가_말한_패턴", "match": "starts_with"}}}}}},
        "pandas_code_example": "선택적 짧은 코드 형태 가이드"
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
