정제된 제조 domain 설명을 MongoDB에 저장 가능한 domain metadata로 변환하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
정제된 설명에 있는 정보만 사용하세요. 필수 정보가 부족하면 missing_information에 넣으세요.
authoring context에는 기존 domain metadata, table catalog metadata, main flow filter metadata가 함께 들어 있습니다.
기존 domain metadata는 기존 key 선택 또는 중복/update 의도 판단에만 사용하세요. 기존 요약에 보인다는 이유만으로 입력에 없는 항목을 새로 만들지 마세요.
생성하는 모든 item은 정제된 설명에 직접 근거가 있어야 합니다. key, alias, process 값, 공식, 질문 패턴이 기존 요약에만 있고 정제된 설명에 없으면 생성하지 마세요.
table catalog metadata는 작업자가 production table, ASSIGN table, target/schedule table, WIP table처럼 말하거나 컬럼명을 언급했을 때 dataset_family와 source column을 추론하는 데 사용하세요.
main flow filter metadata는 물리 컬럼이나 업무 표현을 표준 field로 해석할 때만 사용하고, 이 domain flow에서 main_flow_filter item을 만들지 마세요.
재사용 가능한 domain rule은 작업자가 특정 dataset_key를 명시하지 않았다면 dataset_key보다 dataset_family/source_columns를 선호하세요.
조건은 가능한 한 구조화된 JSON으로 표현하세요. 예: {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}.
실행에 쓰이는 필터 조건을 자연어 문장으로 저장하지 마세요. 컬럼 판정은 condition object로, 정확한 값 매칭은 filters object로 저장하세요.
descriptor 형태 입력은 실행 가능한 구조로 변환하세요. 예: {{"column": "TSV_DIE_TYP", "condition": "not null and not empty"}}는 {{"condition": {{"TSV_DIE_TYP": {{"exists": true, "not_in": [null, ""]}}}}}}가 됩니다.
공정값이나 상태값처럼 정확히 일치해야 하는 값은 문장 대신 {{"filters": {{"OPER_NAME": ["INPUT"]}}}} 같은 구조로 저장하세요.
process_groups에서는 실제 OPER_NAME 값을 processes에 넣으세요. 작업자가 "OPER_NAME 값이 S/G"라고 말하면 condition에만 넣지 말고 processes=["S/G"]로 저장하세요.
세부공정별, 차수별로 보여줘 같은 grouping axis 규칙은 process_groups가 아니라 analysis_recipes로 저장하세요.
DEVICE 첨자, 코드, 설명처럼 특정 출력 컬럼을 보여달라는 필드 별칭 규칙은 product_key_columns가 아니라 analysis_recipes로 저장하세요. 사용자가 제품 키/조인 키 자체를 정의한다고 명시한 경우에만 product_key_columns를 사용하세요.
같은 업무 용어가 dataset별 또는 dataset_family별로 다른 물리 필터를 사용해야 하면 condition_by_dataset 또는 condition_by_family를 사용하세요.
metric_terms에는 텍스트가 필요한 수량이나 결과명을 설명하는 경우 required_quantity_terms와 output_column을 포함하세요.
metric_terms에서 source column/formula가 명확하고 table catalog 문맥으로 source family를 추론할 수 있으면 dataset_key를 요구하지 마세요.
quantity_terms에서 특정 table family의 특정 column unique count라고 설명되면 aggregation='nunique', quantity_column/source_columns, dataset_family를 추론하고 output_column은 명시되지 않았으면 업무 용어로 생성해도 됩니다.
metric_terms에서는 source가 명확하면 작업자가 내부 필드를 모두 쓰지 않아도 재사용 가능한 dataset 의도를 추론하세요.
production table, production result table, 생산량 조회 테이블, 생산 실적, 생산량 조회는 dataset_family='production' 및 required_quantity_terms=['production']로 해석하세요.
하나의 dataset family만 쓰는 metric은 dataset_key가 선택 사항입니다. 현재/이력 dataset은 날짜 범위에 따라 고를 수 있도록 dataset_family 또는 required_dataset_families를 우선 사용하세요.
PRODUCTION, NETDIE_300_CNT처럼 사용자가 source column을 직접 말하면 source_columns에 보존하세요.
FAIL_UNIT_QTY처럼 새로 만들어 옆에 보여주라는 파생 column은 output_columns 또는 output_column에 저장하세요. output 이름이 모호하지 않으면 data type을 추가로 요구하지 마세요.
조건부 나눗셈 metric은 분모 0/null 처리, 실패 수량 column, 출력 column, 행별 계산 후 집계인지 먼저 집계 후 계산인지 보존하세요.
질문 패턴에 따라 어떤 분석 계획을 만들어야 하는지 설명되어 있으면 analysis_recipes를 사용하세요.
analysis_recipes에서는 텍스트가 특정 group-by column을 명시하지 않는 한 group/grain을 고정하지 말고 question_or_product_grain 같은 policy로 유지하세요.
multi-step analysis_recipes에서는 텍스트가 해당 세부 정보를 제공하면 step_plan_template, required_columns_by_family, blocked_filter_fields, override_analysis_kinds, replace/override flag를 보존하세요.
analysis recipe가 재사용 가능한 해석 규칙을 설명하지만 step_plan_template으로 정확히 표현하기 어렵다면 calculation_rule 또는 pandas_generation_rule에 보존하고 저장하세요. 전용 내부 field가 없다는 이유만으로 저장을 막지 마세요.
일반 intent 필드만으로 pandas가 안정적으로 추론하기 어려운 절차형 매칭/파싱 함수 케이스는 pandas_function_cases로 저장하세요.
pandas_function_cases에는 function_name, use_when, token/source/output 컬럼, 짧은 pandas_code_instructions 같은 helper 선택 힌트만 저장하세요. 큰 helper 구현 코드는 MongoDB/domain authoring raw text에 저장하지 말고 14 Pandas Prompt Builder의 Specialized Functions 입력 또는 명시적인 외부 helper package에 둡니다.
LOT_ID distinct count는 aggregation='nunique'를 사용하세요. count_distinct는 사용하지 마세요.
장비 대수 또는 설비 대수처럼 EQPID 기준의 distinct 장비 수를 묻는 항목은 aggregation='nunique'와 output_column EQP_COUNT를 사용하세요.
장비 현황/설비 현황과 장비 대수/설비 대수를 구분하세요. 장비 현황/설비 현황은 result_mode='detail_rows' 상세 행이고, 장비 대수/설비 대수는 EQP_COUNT를 계산합니다.

작성 context:
{authoring_context}

필수 JSON schema:
{{
  "items": [
    {{
      "section": "process_groups | product_terms | quantity_terms | metric_terms | status_terms | analysis_recipes | pandas_function_cases | product_key_columns",
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
        "function_name": "pandas_function_cases용 선택적 helper function name",
        "use_when": "pandas_function_cases용 선택적 적용 조건",
        "input_text": "pandas_function_cases용 선택적 입력 표현 출처",
        "required_source_columns": ["pandas_function_cases에 필요한 source column"],
        "token_columns": ["pandas_function_cases에서 token match에 사용할 column"],
        "output_order": ["pandas_function_cases 결과 표시 순서"],
        "pandas_code_instructions": ["생성될 pandas 코드에 줄 수 있는 선택적 짧은 사용 힌트"]
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
