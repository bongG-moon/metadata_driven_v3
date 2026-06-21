# Main Flow Filters Authoring Raw Text Example

아래 내용은 제조 데이터 분석 Agent가 질문에서 공통 필터를 알아듣도록 등록하는 예시야.
이미 같은 의미의 필터가 있으면 새로 만들지 말고 기존 항목을 업데이트해줘.
작업자는 실제 질문에서 쓰는 말, 실제 컬럼 후보(column_candidates), 값 처리 방식을 중심으로 설명하면 돼.
dataset별 실제 컬럼 연결, 예를 들어 equipment_status의 MCP_NO -> MCPSALENO 같은 정보는 table_catalog의 filter_mappings와 standard_column_aliases에 넣어줘.

<!-- bulk_main_flow_filters:start -->
```text
날짜 조건은 DATE라는 기준 필터로 사용해줘.
사용자가 날짜, 일자, 기준일, 작업일, 조회일, 오늘, 현재, 지금, 금일, 당일, 어제, 전일, date, work date라고 말하면 날짜 조건으로 봐.
실제 데이터에서는 WORK_DT, WORK_DATE, DATE, BASE_DT, HOLD_TM 컬럼 중 해당 dataset에 있는 컬럼과 연결될 수 있어.
이 DATE는 소스 조회 필수 기준일 1개를 받는 용도야.
기간 조회가 명시되지 않으면 범위 조건으로 바꾸지 말고 YYYYMMDD 형식의 단일 날짜로 정규화해줘.
저장할 때는 semantic_role date, value_type date, value_shape scalar, operator eq, normalized_format YYYYMMDD로 남겨줘.
required_params에는 DATE를 넣어줘.


공정명 조건은 OPER_NAME으로 사용해줘.
사용자가 공정, 작업공정, operation, process, oper, oper name, 공정명, 차수라고 말하면 공정 조건으로 봐.
실제 컬럼 후보(column_candidates)는 OPER_NAME, OPER_DESC, OPER_ID, OPER_SHORT_DESC야.
저장할 때는 semantic_role process_name으로 남겨줘.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.
실제 공정 값으로 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6, W/B1, W/B2, W/B3, D/S1, INPUT이 자주 쓰여.
DA, D/A, 다이 어태치, die attach라고 말하면 D/A1~D/A6로 펼쳐줘.
WB, W/B, 와이어 본딩, wire bonding이라고 말하면 W/B1~W/B3로 펼쳐줘.
DS, D/S, 다이 싱귤레이션이라고 말하면 D/S1로 보고, 투입 또는 input이라고 말하면 INPUT으로 봐.

제품 TECH 조건은 TECH로 사용해줘.
사용자가 tech, technology, 테크, 기술, 공정기술이라고 말하면 TECH 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 TECH 또는 TECH_NM이야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.

제품 밀도나 용량 조건은 DEN으로 사용해줘.
사용자가 den, density, 밀도, 용량이라고 말하면 DEN 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 DEN 또는 DEN_TYP이야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.

제품 MODE 조건은 MODE로 사용해줘.
사용자가 mode, product mode, 모드, 제품모드, 제품군이라고 말하면 MODE 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 MODE 또는 PROD_TYP이야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.
POP 제품이라고 말하면 MODE가 LP로 시작하는 조건으로 해석할 수 있어.

패키지 타입 1 조건은 PKG_TYPE1로 사용해줘.
사용자가 pkg type1, package type1, 패키지 타입1, 패키지 대분류라고 말하면 PKG_TYPE1 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 PKG_TYPE1, PKG1, PKG_TYP이야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.

패키지 타입 2 조건은 PKG_TYPE2로 사용해줘.
사용자가 pkg type2, package type2, 패키지 타입2, 패키지 구분이라고 말하면 PKG_TYPE2 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 PKG_TYPE2, PKG2, PKG_TYP_2, PKG_TYP2야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.

LEAD 조건은 LEAD로 사용해줘.
사용자가 lead, 리드, lead count, lead type이라고 말하면 LEAD 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 LEAD 또는 LEAD_CNT야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.

MCP 번호 조건은 MCP_NO로 사용해줘.
사용자가 MCP, MCP NO, mcp 번호, mcp_no라고 말하면 MCP_NO 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 MCP_NO, MCP NO, MCP_SALE_CD, MCPSALENO야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.
빈값, blank, empty라고 말하면 EMPTY로 치환된 값과 동일하게 취급할 수 있어.

제품명이나 device description 텍스트 검색은 DEVICE_DESC로 사용해줘.
사용자가 device, device desc, device description, 디바이스, 제품명, 제품 설명이라고 말하면 DEVICE_DESC 컬럼에서 찾아줘.
실제 컬럼 후보(column_candidates)는 DEVICE_DESC야.
여러 검색어가 들어오면 contains 방식으로 DEVICE_DESC에 OR 부분 문자열 검색을 적용해줘.
저장할 때는 value_type string, value_shape list, operator contains로 남겨줘.
기본 제품 집계 grain은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO 조합이고 DEVICE_DESC는 상세 설명 컬럼으로 보면 돼.

TSV, HBM, 3DS 계열 판정 조건은 TSV_DIE_TYP로 사용해줘.
사용자가 TSV, HBM, 3DS, TSV die type, tsv_die_typ이라고 말하면 TSV_DIE_TYP 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 TSV_DIE_TYP야.
HBM/3DS/TSV 제품 판단 시에는 TSV_DIE_TYP 값이 존재하고 빈 값이 아닌 조건을 사용할 수 있어.

공정 번호 조건은 OPER_NUM으로 사용해줘.
사용자가 oper num, operation number, 공정 번호, 공정번호라고 말하면 OPER_NUM 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 OPER_NUM이야.
숫자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.

장비 ID 조건은 EQP_ID로 사용해줘.
사용자가 eqp, eqp id, equipment, equipment id, tool, 설비, 장비라고 말하면 장비 ID 조건으로 봐.
실제 컬럼 후보(column_candidates)는 EQP_ID, EQUIPMENT_ID, EQPID야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.


장비 모델 조건은 EQP_MODEL로 사용해줘.
사용자가 eqp model, equipment model, model, 장비 모델, 설비 모델이라고 말하면 장비 모델 조건으로 봐.
실제 컬럼 후보(column_candidates)는 EQP_MODEL, EQP_MODEL_CD야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.


lot ID 조건은 LOT_ID로 사용해줘.
사용자가 lot, lot id, 로트, 로트ID라고 말하면 LOT_ID 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 LOT_ID야.
LOT_ID는 LOT-00001-1처럼 하이픈과 숫자가 함께 포함될 수 있어.
LOT_ID를 추출할 때 마지막 숫자까지 포함한 전체 문자열을 하나의 값으로 보존해줘.
예: LOT-00001-1은 LOT-00001-가 아니라 LOT-00001-1 전체가 LOT_ID야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.

recipe 조건은 RECIPE_ID로 사용해줘.
사용자가 recipe, recipe id, 레시피, 레시피 ID라고 말하면 RECIPE_ID 컬럼 조건으로 봐.
실제 컬럼 후보(column_candidates)는 RECIPE_ID야.
장비 보유 현황과 UPH 데이터의 레시피 기준 조회에 사용해.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.
```
<!-- bulk_main_flow_filters:end -->

## 단일 항목 예시

<!-- single_eqp_model:start -->
```text
장비 모델 조건은 EQP_MODEL로 사용해줘.
사용자가 eqp model, equipment model, model, 장비 모델, 설비 모델이라고 말하면 장비 모델 조건으로 봐.
실제 컬럼 후보(column_candidates)는 EQP_MODEL, EQP_MODEL_CD야.
문자 값 여러 개를 받을 수 있고 in 조건으로 적용해줘.
```
<!-- single_eqp_model:end -->
