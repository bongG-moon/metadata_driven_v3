# Main Flow Filters Authoring Raw Text Examples

아래 예시는 질문에서 공통 필터 의미를 인식하도록 등록하는 최소 샘플입니다.
실제 dataset별 컬럼 연결은 table catalog의 filter_mappings와 standard_column_aliases를 함께 사용합니다.

<!-- bulk_main_flow_filters:start -->
```text
[날짜 필터]
DATE는 기준일 필터야.
사용자가 날짜, 일자, 기준일, 작업일, 오늘, 금일, 어제, 전일, date, work date라고 말하면 DATE 조건으로 해석해줘.
값은 기간이 명시되지 않으면 YYYYMMDD 형식의 단일 날짜로 정규화하고, operator는 eq로 사용해.
실제 컬럼 후보는 WORK_DT, WORK_DATE, DATE, BASE_DT야.

[공정명 필터]
OPER_NAME은 공정명 필터야.
사용자가 공정, 작업공정, operation, process, oper name, 차수라고 말하면 OPER_NAME 조건으로 해석해줘.
실제 컬럼 후보는 OPER_NAME, OPER_DESC, OPER_ID, OPER_SHORT_DESC야.
값이 여러 개면 in 조건으로 처리해.

[제품 MODE 필터]
MODE는 제품 mode 필터야.
사용자가 mode, product mode, 모드, 제품모드, 제품군이라고 말하면 MODE 조건으로 해석해줘.
실제 컬럼 후보는 MODE, PROD_TYP야.
POP 제품이라고 말하면 MODE가 LP로 시작하는 조건으로 해석할 수 있어.

[패키지 타입 필터]
PKG_TYPE1은 package type 1, PKG_TYPE2는 package type 2 필터야.
실제 컬럼 후보는 PKG_TYPE1/PKG1/PKG_TYP1, PKG_TYPE2/PKG2/PKG_TYP2/PKG_TYP_2야.
dataset마다 실제 컬럼명이 다르면 table catalog의 alias 정보를 사용해 표준 컬럼명으로 맞춰줘.

[장비 필터]
EQP_MODEL은 장비 모델 필터야.
사용자가 eqp model, equipment model, 장비 모델, 설비 모델이라고 말하면 EQP_MODEL 조건으로 해석해줘.
실제 컬럼 후보는 EQP_MODEL, EQP_MODEL_CD야.
```
<!-- bulk_main_flow_filters:end -->

## 단일 항목 예시

<!-- single_eqp_model:start -->
```text
장비 모델 조건은 EQP_MODEL로 사용해줘.
사용자가 eqp model, equipment model, 장비 모델, 설비 모델이라고 말하면 EQP_MODEL 조건으로 해석해줘.
실제 컬럼 후보는 EQP_MODEL, EQP_MODEL_CD야.
문자 값이 여러 개 들어오면 in 조건으로 적용해줘.
```
<!-- single_eqp_model:end -->
