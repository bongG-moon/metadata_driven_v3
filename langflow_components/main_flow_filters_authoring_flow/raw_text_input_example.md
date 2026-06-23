# Main Flow Filters Authoring Raw Text Examples

아래 예시는 질문에서 공통 필터 후보를 인식하도록 등록하는 최소 샘플입니다.
dataset별 실제 컬럼 연결은 table catalog의 `filter_mappings`와 `standard_column_aliases`에서 관리합니다.

<!-- bulk_main_flow_filters:start -->
```text
[날짜 필터]
DATE는 기준일자 필터야.
사용자가 날짜, 일자, 기준일, 작업일, 오늘, 금일, 어제, 전일, date, work date라고 말하면 DATE 조건으로 해석해줘.
실제 컬럼 후보는 WORK_DATE, WORK_DT, DATE, BASE_DT야.

[공정 필터]
OPER_NAME은 공정명 필터야. 실제 컬럼 후보는 OPER_NAME, OPER_DESC, OPER_ID, OPER_SHORT_DESC야.
OPER_NUM은 공정 번호 필터야. 실제 컬럼 후보는 OPER_NUM, OPER, OPER_NO야.

[제품 필터]
TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, DEVICE_DESC, TSV_DIE_TYP는 제품/자재 조건을 표현하는 공통 필터야.
DEN의 실제 컬럼 후보는 DEN, DENSITY, DEN_TYP야.
MODE의 실제 컬럼 후보는 MODE, PROD_TYP야.
PKG_TYPE1의 실제 컬럼 후보는 PKG_TYPE1, PKG1, PKG_TYP1, PKG_TYP야.
PKG_TYPE2의 실제 컬럼 후보는 PKG_TYPE2, PKG2, PKG_TYP2, PKG_TYP_2야.
MCP_NO의 실제 컬럼 후보는 MCP_NO, MCP NO, MCP_SALES_NO, MCP_SALE_CD, MCPSALENO, PROD_GRP_ID야.
DEVICE_DESC의 실제 컬럼 후보는 DEVICE_DESC, DEVICE, DEVICE_CODE야.
TSV_DIE_TYP의 실제 컬럼 후보는 TSV_DIE_TYP, TSV_DIE_TYPE야.

[장비/LOT/Recipe 필터]
EQP_ID는 장비 ID 필터야. 실제 컬럼 후보는 EQP_ID, EQPID야.
EQP_MODEL은 장비 모델 필터야. 실제 컬럼 후보는 EQP_MODEL, EQP_MODEL_CD야.
LOT_ID는 lot ID 필터야. 실제 컬럼 후보는 LOT_ID야.
RECIPE_ID는 recipe ID 필터야. 실제 컬럼 후보는 RECIPE_ID야.
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
