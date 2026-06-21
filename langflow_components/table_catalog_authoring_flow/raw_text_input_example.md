# Table Catalog Authoring Single-Dataset Raw Text Examples

아래 예시는 `01 Table Catalog Text Refinement Prompt Template`의 `{raw_text}`에 넣는 단건 원문 예시입니다.
실제 작업자는 필요한 dataset 블록 하나만 골라 자연스럽게 입력하면 됩니다.
SQL이나 실제 컬럼명처럼 반드시 보존해야 하는 값은 정확히 적어주세요.

- 같은 데이터가 이미 MongoDB에 있으면 writer 기본값 `update_mode=merge` 기준으로 기존 문서와 병합 업데이트됩니다.
- `DATE`처럼 조회에 꼭 필요한 기준값이 있는 데이터는 어느 컬럼과 연결되는지 함께 적어주세요.
- 날짜 값 형식은 실제 데이터에 저장된 모양 그대로 적어주세요. 예: 20260609이면 YYYYMMDD, 2026-06-09이면 YYYY-MM-DD, 2026/06/09이면 YYYY/MM/DD, 2026.06.09이면 YYYY.MM.DD.
- 한 데이터에서 분석에 쓰는 수량 컬럼이 여러 개면 "두 컬럼 모두 분석 수량으로 사용한다"고 적어주세요.
- 컬럼 뜻, 비슷한 이름, 예시값을 알면 함께 적어주세요. 예: OUT계획은 산출 계획 수량이고 OUT_PLAN, 생산목표라고도 부르며 예시는 12000이야.
- filter_mappings는 왼쪽에 main flow filter 표준명(DATE, OPER_NAME, MODE 등)을 적고, 오른쪽에 해당 dataset의 실제 컬럼명을 적어주세요.
- SQL은 `query_template:` 아래에 원문 그대로 붙여 넣어주세요.
- Goodocs의 `doc_id`는 실제 목표2 문서 ID로 바꿔서 사용해야 합니다.
- 이 파일은 `raw_text_input_all_in_one_example.md`의 기본 dataset과 운영 중 선택 등록/수정 case를 나눈 예시입니다.

<!-- bulk_table_catalog:start -->
## Production Today

```text
당일용 생산 실적 데이터는 production_today로 등록해줘.
화면에 보일 이름은 Production Today이면 돼.
당일 생산 실적 질문에 사용하는 Oracle 데이터야.
production_today는 production 계열의 당일용 생산 실적 source야.
조회할 때 DATE 값은 WORK_DT 컬럼에 넣어서 조회하고, DATE는 조회 필수 기준일이야.
DATE는 YYYYMMDD 형식이야.
수량은 PRODUCTION 컬럼을 사용하고, 이 값은 생산량이야.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT WORK_DT, FACTORY, FAMILY, MODE, DEN, TECH, ORG, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, DEVICE, DEVICE_DESC, OPER_NUM, OPER_NAME, OPER_SEQ, PRODUCTION
FROM PRODUCTION_TODAY
WHERE 1=1
AND WORK_DT = {DATE}
AND PRODUCTION > 0

filter_mappings는 DATE -> WORK_DT, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2, LEAD -> LEAD, MCP_NO -> MCP_NO, TSV_DIE_TYP -> TSV_DIE_TYP, DEVICE_DESC -> DEVICE_DESC, OPER_NUM -> OPER_NUM, OPER_NAME -> OPER_NAME로 연결해줘.
```

## Production History

```text
이력 생산 실적 데이터는 production으로 등록해줘.
화면에 보일 이름은 Production History이면 돼.
production은 production 계열의 이력 생산 실적 source야.
조회할 때 DATE 값은 WORK_DT 컬럼에 넣어서 조회하고, DATE는 조회 필수 기준일이야.
수량은 PRODUCTION 컬럼을 사용하고, 이 값은 생산량이야.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT WORK_DT, FACTORY, FAMILY, MODE, DEN, TECH, ORG, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, DEVICE, DEVICE_DESC, OPER_NUM, OPER_NAME, OPER_SEQ, PRODUCTION
FROM PRODUCTION
WHERE 1=1
AND WORK_DT = {DATE}
AND PRODUCTION > 0

filter_mappings는 DATE -> WORK_DT, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2, LEAD -> LEAD, MCP_NO -> MCP_NO, TSV_DIE_TYP -> TSV_DIE_TYP, DEVICE_DESC -> DEVICE_DESC, OPER_NUM -> OPER_NUM, OPER_NAME -> OPER_NAME로 연결해줘.
```

<!-- single_wip_today:start -->
## WIP Today

```text
당일용 재공 데이터는 wip_today로 등록해줘.
화면에 보일 이름은 WIP Today이면 돼.
당일 재공 질문에 사용하는 Oracle 데이터야.
wip_today는 wip 계열의 당일용 재공 source야.
조회할 때 DATE 값은 WORK_DT 컬럼에 넣어서 조회하고, DATE는 조회 필수 기준일이야.
수량은 WIP 컬럼을 사용하고, 이 값은 재공 수량이야.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT WORK_DT, FACTORY, FAMILY, MODE, DEN, TECH, ORG, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, DEVICE, DEVICE_DESC, OPER_NUM, OPER_NAME, OPER_SEQ, WIP
FROM WIP_TODAY
WHERE 1=1
AND WORK_DT = {DATE}
AND WIP > 0

filter_mappings는 DATE -> WORK_DT, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2, LEAD -> LEAD, MCP_NO -> MCP_NO, TSV_DIE_TYP -> TSV_DIE_TYP, DEVICE_DESC -> DEVICE_DESC, OPER_NUM -> OPER_NUM, OPER_NAME -> OPER_NAME로 연결해줘.
```
<!-- single_wip_today:end -->

## WIP History

```text
이력 재공 데이터는 wip으로 등록해줘.
화면에 보일 이름은 WIP History이면 돼.
wip은 wip 계열의 이력 재공 source야.
조회할 때 DATE 값은 WORK_DT 컬럼에 넣어서 조회하고, DATE는 조회 필수 기준일이야.
수량은 WIP 컬럼을 사용하고, 이 값은 재공 수량이야.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT WORK_DT, FACTORY, FAMILY, MODE, DEN, TECH, ORG, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, TSV_DIE_TYP, DEVICE, DEVICE_DESC, OPER_NUM, OPER_NAME, OPER_SEQ, WIP
FROM WIP
WHERE 1=1
AND WORK_DT = {DATE}
AND WIP > 0

filter_mappings는 DATE -> WORK_DT, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2, LEAD -> LEAD, MCP_NO -> MCP_NO, TSV_DIE_TYP -> TSV_DIE_TYP, DEVICE_DESC -> DEVICE_DESC, OPER_NUM -> OPER_NUM, OPER_NAME -> OPER_NAME로 연결해줘.
```

## Target2 Goodocs Plan

```text
목표2 계획 데이터는 target으로 등록해줘.
화면에 보일 이름은 Target2 Goodocs Plan이면 돼.
Goodocs 목표2 문서에서 일자와 제품 속성별 INPUT계획, OUT계획을 가져오는 데이터야.
이 데이터는 Goodocs source이고 별도 필수 조회 파라미터는 없어.
DATE 값 형식은 YYYY-MM-DD야. 필터 조건 걸 때 이 부분을 잘 고려해서 구현해줘야 해
위 DATE 값 형식은 target dataset의 table catalog metadata에 date_format=YYYY-MM-DD로 저장되어야 해.
기본 목표 수량은 OUT계획이고, 계획/목표 데이터로 사용해.
계획 수량은 INPUT계획과 OUT계획 두 컬럼을 모두 사용해. 두 컬럼 모두 분석 수량으로 쓰는 계획 수량 컬럼이야.
Goodocs 문서 ID는 GOODOCS_TARGET2_DOCUMENT_ID를 사용해. 특정 시트를 고정해서 읽어야 하는 환경이면 sheet_name은 목표2야.
목표2 문서에는 DATE, Mode, DEN, TECH, PKG1, PKG2, LEAD, ORG, MCP NO, INPUT계획, OUT계획 항목이 있어.
DATE는 계획 일자이고 예시값은 2026-06-09야.
Mode는 제품 mode이고 MODE라고도 불러.
PKG1은 package type 1이고 PKG_TYPE1이라고도 불러.
PKG2는 package type 2이고 PKG_TYPE2라고도 불러.
MCP NO는 MCP number이고 MCP_NO라고도 불러.
INPUT계획은 투입 계획 수량이고 INPUT_PLAN, 투입계획이라고도 불러.
OUT계획은 산출 계획 수량이고 TARGET, OUT_PLAN, 생산목표라고도 불러.
filter_mappings는 DATE -> DATE, MODE -> Mode, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, LEAD -> LEAD, MCP_NO -> MCP NO로 연결해줘.
standard_column_aliases는 MODE -> Mode, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, MCP_NO -> MCP NO, INPUT_PLAN -> INPUT계획, OUT_PLAN -> OUT계획 또는 TARGET으로 연결해줘.
```

## Legacy Target Oracle Plan

```text
구형 target 계획 데이터를 사용하는 환경에서만 이 블록을 골라 등록해줘.
현재 Target2 Goodocs Plan과 동시에 등록하지 말고, 구형 target을 쓰는 경우에도 dataset 이름은 target으로 등록해줘.
화면에 보일 이름은 Legacy Target Oracle Plan이면 돼.
구형 target은 Oracle에서 날짜, 제품 속성, OPER_NAME별 TARGET 계획 수량을 가져오는 데이터야.
이 데이터는 TARGET 컬럼과 OPER_NAME 컬럼으로 계획 종류를 구분하는 구조야.
조회할 때 DATE 값은 WORK_DT 컬럼에 넣어서 조회하고, DATE는 조회 필수 기준일이야.
기본 목표 수량은 TARGET이고, 계획/목표 데이터로 사용해.
source는 oracle이고 db_key는 PNT_RPT야.
TARGET_PLAN은 예시 table명이므로 실제 구형 target table명으로 바꿔서 사용해.

query_template:
SELECT WORK_DT, FACTORY, FAMILY, MODE, DEN, TECH, ORG, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, TARGET
FROM TARGET_PLAN
WHERE 1=1
AND WORK_DT = {DATE}
AND TARGET > 0

filter_mappings는 DATE -> WORK_DT, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG_TYPE1, PKG_TYPE2 -> PKG_TYPE2, LEAD -> LEAD, MCP_NO -> MCP_NO, OPER_NAME -> OPER_NAME로 연결해줘.
main flow filter 예시에 남긴 핵심 필터 기준으로만 연결하고 FACTORY, FAMILY, ORG는 필터로 매핑하지 말아줘.
TARGET은 PLAN, 목표, 생산목표라고도 불러.
OPER_NAME='INPUT'인 TARGET 수량은 INPUT계획으로 볼 수 있어.
OUT계획 또는 생산목표를 구분하는 OPER_NAME 값은 환경마다 다를 수 있으니, 실제 값을 모르면 table catalog에서 고정하지 말아줘.
```

## Equipment Status

```text
설비 보유 현황 데이터는 equipment_status로 등록해줘.
화면에 보일 이름은 Equipment Status이면 돼.
Oracle PNT_RPT의 EQP_TABLE에서 설비별 보유 현황을 가져오는 데이터야.
이 데이터는 필수 PARA가 없어
장비 대수는 EQPID를 중복 없이 세어 EQP_COUNT로 보여줘. PRESS_CNT도 주요 수량 컬럼으로 사용할 수 있어.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT BAY_ID, EQPID, EQP_MODEL, PRESS_CNT, MODE, DEN, TECH, PKG1, PKG2, LEAD, ORG, PKGSIZE, MCPSALENO, DEVICE, DEVICE_DESC, LOT_ID, EQP_OPERATYN, PI, RECIPE_ID
FROM EQP_TABLE
WHERE 1=1

filter_mappings는 EQP_ID -> EQPID, EQP_MODEL -> EQP_MODEL, MODE -> MODE, DEN -> DEN, TECH -> TECH, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, LEAD -> LEAD, MCP_NO -> MCPSALENO, DEVICE_DESC -> DEVICE_DESC, LOT_ID -> LOT_ID, RECIPE_ID -> RECIPE_ID로 연결해줘.
standard_column_aliases는 PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, MCP_NO -> MCPSALENO로 연결해줘.
```

## Equipment Recipe UPH

```text
설비/레시피별 UPH 데이터는 capacity로 등록해줘.
화면에 보일 이름은 Equipment Recipe UPH이면 돼.
Oracle GMS_DB의 UPH 테이블에서 설비와 레시피별 평균 UPH를 가져오는 데이터야.
이 데이터는 필수 파라미터 없이 조회해.
UPH 값은 AVG_UPH_VAL컬럼에 나와있어.
source는 oracle이고 db_key는 GMS_DB야.

query_template:
SELECT FAC_ID, EQP_OPER_GRP_CD, EQP_OPER_DET_GRP_CD, EQP_MODEL_CD, OPER_ID, OPER_DESC, PRESS_CNT, PROD_TYP, TECH_NM, DEN_TYP, PKG_TYP, PKG_TYP2, LEAD_CNT, MCP_SALE_CD, RECIPE_ID, AVG_UPH_VAL, BASE_DT
FROM UPH
WHERE 1=1

filter_mappings는 DATE -> BASE_DT, EQP_MODEL -> EQP_MODEL_CD, OPER_NAME -> OPER_DESC, MODE -> PROD_TYP, TECH -> TECH_NM, DEN -> DEN_TYP, PKG_TYPE1 -> PKG_TYP, PKG_TYPE2 -> PKG_TYP2, LEAD -> LEAD_CNT, MCP_NO -> MCP_SALE_CD, RECIPE_ID -> RECIPE_ID로 연결해줘.
standard_column_aliases는 EQP_MODEL -> EQP_MODEL_CD, OPER_NAME -> OPER_DESC, MODE -> PROD_TYP, TECH -> TECH_NM, DEN -> DEN_TYP, PKG_TYPE1 -> PKG_TYP, PKG_TYPE2 -> PKG_TYP2, LEAD -> LEAD_CNT, MCP_NO -> MCP_SALE_CD로 연결해줘.

```

## LOT Status

```text
LOT status 조회 데이터는 lot_status로 등록해줘.
화면에 보일 이름은 LOT Status이면 돼.
현재 재공에서 작업중 Lot 수량, 작업대기 Lot 수량, Hold Lot 수량, Lot별 TAT를 확인하는 Oracle 데이터야.
이 데이터는 필수 조회 조건이 없어.
Lot 건수는 LOT_ID를 count해서 보고, 수량/지표로는 SUB_PROD_QTY, WF_QTY, IN_TAT, CUM_TAT를 사용해.
IN_TAT는 현재 공정 유입 이후 TAT이고 CUM_TAT는 누적 TAT야.
LOT_HOLD_STAT_CD는 Hold 여부(OnHold, NotOnHold), LOT_STAT_CD는 Lot 상태, OPER_SHORT_DESC와 OPER_ID는 공정 정보야.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT ERM_ID, OPER_ID, OPER_SHORT_DESC, FAB_ID, OWNER_CD, GRADE_CD, PROD_ID, LOT_ID, SUB_LOT_ID, SUB_PROD_QTY, WF_QTY, IN_TAT, CUM_TAT, EQP_ID, FLOW_ID, OPER_IN_TM, CRT_TM, FAC_IN_TM, LOT_HOLD_STAT_CD, REASON_CD, FAMILY_CD, PROD_TYP, DEN_TYP, TECH_NM, ORGANIZ_CD, PKG_TYP, PKG_TYP_2, PKG_TYP_3, LEAD_CNT, PROD_GRP_ID, THK_CD, LOT_STAT_CD, LOT_GRP_CD, PKG_SIZE_VAL, PKG_DEN_TYP, HOT_LOT_YN, HOT_LEVEL_TYP, PKG_COMPOSIT_TYP, DURABLE_ID, DURABLE_TYP, SUB_QTY, TSV_DIE_TYP, EVENT_DESC, PLANNING_DESC, MOVE_IN_TM, PAD_ABNORM_YN, SWR_REQ_NO, OPER_GRP_VAL_1, INSP_TGT_YN
FROM LOT_STATUS_TABLE
WHERE 1=1

filter_mappings는 OPER_NAME -> OPER_SHORT_DESC 또는 OPER_ID, MODE -> PROD_TYP, DEN -> DEN_TYP, TECH -> TECH_NM, PKG_TYPE1 -> PKG_TYP, PKG_TYPE2 -> PKG_TYP_2, LEAD -> LEAD_CNT, MCP_NO -> PROD_GRP_ID, TSV_DIE_TYP -> TSV_DIE_TYP, EQP_ID -> EQP_ID, LOT_ID -> LOT_ID로 연결해줘.
lot_status 데이터에서 제품 기준 MCP_NO에 해당하는 실제 컬럼은 PROD_GRP_ID야.
standard_column_aliases는 OPER_NAME -> OPER_SHORT_DESC, MODE -> PROD_TYP, DEN -> DEN_TYP, TECH -> TECH_NM, PKG_TYPE1 -> PKG_TYP, PKG_TYPE2 -> PKG_TYP_2, LEAD -> LEAD_CNT, MCP_NO -> PROD_GRP_ID로 연결해줘.
```

<!-- single_hold_history:start -->
## HOLD History

```text
HOLD 이력 조회 데이터는 hold_history로 등록해줘.
화면에 보일 이름은 HOLD History이면 돼.
HOLD된 LOT의 HOLD 발생 사유, HOLD 발생 시각, 해제 예정일, HOLD 설명을 확인하는 Oracle 데이터야.
LOT_ID가 조회 필수 조건이야.
HOLD 건수는 LOT_ID를 count해서 보고, OLD_SUB_PROD_QTY는 HOLD 당시 sub product 수량이야.
HOLD_TM은 HOLD 발생 시각이고 RELEASE_DUE_DATE는 해제 예정일이야.
HOLD_CD와 HOLD_DESC는 HOLD 사유를 설명하는 컬럼이야.
source는 oracle이고 db_key는 PNT_RPT야.

query_template:
SELECT FAB_ID, DEN_TYP, PROD_ID, GRADE_CD, OWNER_CD, OPER_ID, OPER_SHORT_DESC, LOT_ID, OLD_SUB_PROD_QTY, HOLD_TM, RELEASE_DUE_DATE, HOLD_CD, HOLD_USER_ID, HOLD_DESC, FAMILY_CD, TECH_NM, GEN_TYP, ORGANIZ_CD, PKG_TYP_2, PKG_SIZE_VAL, PROD_GRP_ID, THK_CD, MCP_SALE_CD, HOLD_GRADE_CD, FLOW_ID, FAC_ID, EVENT_CD
FROM HOLD_HISTORY_TABLE
WHERE 1=1
AND LOT_ID = {LOT_ID}

required_param_mappings는 LOT_ID -> LOT_ID로 연결해줘.
filter_mappings는 LOT_ID -> LOT_ID, OPER_NAME -> OPER_SHORT_DESC 또는 OPER_ID, DEN -> DEN_TYP, TECH -> TECH_NM, PKG_TYPE2 -> PKG_TYP_2, MCP_NO -> MCP_SALE_CD로 연결해줘.
standard_column_aliases는 DEN -> DEN_TYP, TECH -> TECH_NM, PKG_TYPE2 -> PKG_TYP_2, MCP_NO -> MCP_SALE_CD로 연결해줘.
```
<!-- single_hold_history:end -->
<!-- bulk_table_catalog:end -->
