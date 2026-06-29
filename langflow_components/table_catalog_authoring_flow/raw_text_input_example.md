# Table Catalog Authoring Raw Text Examples

아래 예시는 데이터셋을 등록할 때 필요한 핵심 정보만 담은 샘플입니다.
SQL은 실제 등록할 쿼리문을 그대로 붙여 넣고, filter_mappings에는 표준 필터명과 실제 컬럼명을 연결합니다.

<!-- bulk_table_catalog:start -->
```text
[Oracle 생산 데이터셋]
production_today는 오늘 생산 실적 데이터셋이야.
source는 oracle, db_key는 PNT_RPT이고 DATE는 WORK_DATE 컬럼에 넣어 조회하는 필수 파라미터야.
주요 수량은 PRODUCTION 컬럼이고 date_format은 YYYYMMDD야.

query_template:
SELECT A.WORK_DATE, A.SHIFT, A.MODE, A.DEN, A.TECH, A.PKG_TYP1, A.PKG_TYP2, A.LEAD, A.MCP_NO, A.DEVICE, A.DEVICE_DESC, A.DIE_ATTACH_QTY, A.NETDIE_300_CNT, A.OPER, A.OPER_NAME, A.OPER_SEQ, A.PRODUCTION
FROM PRODUCTION_TODAY A
WHERE 1=1
AND A.WORK_DATE = {DATE}
AND A.PRODUCTION > 0

filter_mappings는 DATE -> WORK_DATE, MODE -> MODE, DEN -> DEN, TECH -> TECH, ORG -> ORG, PKG_TYPE1 -> PKG_TYP1, PKG_TYPE2 -> PKG_TYP2, LEAD -> LEAD, MCP_NO -> MCP_NO, DEVICE -> DEVICE, DEVICE_DESC -> DEVICE_DESC, DIE_ATTACH_QTY -> DIE_ATTACH_QTY, NETDIE_300_CNT -> NETDIE_300_CNT, OPER_NUM -> OPER, OPER_SEQ -> OPER_SEQ, OPER_NAME -> OPER_NAME로 연결해줘.
standard_column_aliases는 DATE -> WORK_DATE, PKG_TYPE1 -> PKG_TYP1, PKG_TYPE2 -> PKG_TYP2, DEVICE -> DEVICE, DEVICE_DESC -> DEVICE_DESC, DIE_ATTACH_QTY -> DIE_ATTACH_QTY, NETDIE_300_CNT -> NETDIE_300_CNT, OPER_NUM -> OPER, OPER_SEQ -> OPER_SEQ로 연결해줘.

[Oracle 재공 데이터셋]
wip_today는 오늘 재공 데이터셋이야.
source는 oracle, db_key는 PNT_RPT이고 DATE는 WORK_DATE 컬럼에 넣어 조회하는 필수 파라미터야.
주요 수량은 WIP 컬럼이고 date_format은 YYYYMMDD야.

query_template:
SELECT A.WORK_DATE, A.SHIFT, A.MODE, A.DENSITY, A.TECH, A.PKG1, A.PKG2, A.LEAD, A.MCP_NO, A.DEVICE, A.DEVICE_DESC, A.DIE_ATTACH_QTY, A.NETDIE_300_CNT, A.OPER, A.OPER_NAME, A.OPER_SEQ, ROUND(SUM(A.WIP),1) AS WIP
FROM WIP_TODAY A
WHERE 1=1
AND A.WORK_DATE = {DATE}
GROUP BY A.WORK_DATE, A.SHIFT, A.MODE, A.DENSITY, A.TECH, A.PKG1, A.PKG2, A.LEAD, A.MCP_NO, A.DEVICE, A.DEVICE_DESC, A.DIE_ATTACH_QTY, A.NETDIE_300_CNT, A.OPER, A.OPER_NAME, A.OPER_SEQ

filter_mappings는 DATE -> WORK_DATE, MODE -> MODE, DEN -> DENSITY, TECH -> TECH, ORG -> ORG, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, LEAD -> LEAD, MCP_NO -> MCP_NO, DEVICE -> DEVICE, DEVICE_DESC -> DEVICE_DESC, DIE_ATTACH_QTY -> DIE_ATTACH_QTY, NETDIE_300_CNT -> NETDIE_300_CNT, OPER_NUM -> OPER, OPER_SEQ -> OPER_SEQ, OPER_NAME -> OPER_NAME로 연결해줘.
standard_column_aliases는 DATE -> WORK_DATE, DEN -> DENSITY, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, DEVICE -> DEVICE, DEVICE_DESC -> DEVICE_DESC, DIE_ATTACH_QTY -> DIE_ATTACH_QTY, NETDIE_300_CNT -> NETDIE_300_CNT, OPER_NUM -> OPER, OPER_SEQ -> OPER_SEQ로 연결해줘.

[Goodocs 목표 데이터셋]
target은 목표 또는 계획 데이터셋이야.
source는 goodocs이고 DATE 형식은 YYYY-MM-DD야.
주요 수량은 INPUT 계획과 OUT 계획 컬럼이고, OUT 계획은 생산 목표로 사용해.
목표2 문서에는 DATE, Mode, DEN, TECH, PKG1, PKG2, LEAD, ORG, MCP NO, INPUT 계획, OUT 계획 컬럼이 있어.
filter_mappings는 DATE -> DATE, MODE -> Mode, DEN -> DEN, TECH -> TECH, ORG -> ORG, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, LEAD -> LEAD, MCP_NO -> MCP NO로 연결해줘.

[장비 현황 데이터셋]
equipment_status는 제품에 할당된 장비 현황 데이터셋이야.
source는 oracle이고 필수 조회 파라미터는 없어.
장비 대수는 EQPID를 중복 없이 세어 EQP_COUNT로 보여줘.
filter_mappings는 MODE -> MODE, DEN -> DEN, TECH -> TECH, ORG -> ORG, PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, LEAD -> LEAD, MCP_NO -> MCPSALENO, DEVICE -> DEVICE, DEVICE_DESC -> DEVICE_DESC, EQP_ID -> EQPID로 연결해줘.
standard_column_aliases는 PKG_TYPE1 -> PKG1, PKG_TYPE2 -> PKG2, MCP_NO -> MCPSALENO, DEVICE -> DEVICE, DEVICE_DESC -> DEVICE_DESC로 연결해줘.
```
<!-- bulk_table_catalog:end -->

## 단일 항목 예시

<!-- single_hold_history:start -->
```text
hold_history는 HOLD 이력 조회 데이터셋이야.
source는 oracle, db_key는 PNT_RPT이고 LOT_ID를 필수 파라미터로 받아 조회해.
HOLD 발생 시간은 HOLD_TM, HOLD 사유는 HOLD_CD와 HOLD_DESC를 사용해.

query_template:
SELECT LOT_ID, HOLD_TM, RELEASE_DUE_DATE, HOLD_CD, HOLD_USER_ID, HOLD_DESC, OPER_ID, OPER_SHORT_DESC, EVENT_CD
FROM HOLD_HISTORY_TABLE
WHERE 1=1
AND LOT_ID = {LOT_ID}

required_param_mappings는 LOT_ID -> LOT_ID로 연결해줘.
filter_mappings는 LOT_ID -> LOT_ID, OPER_NAME -> OPER_SHORT_DESC, DEN -> DEN_TYP, TECH -> TECH_NM, MCP_NO -> MCP_SALE_CD로 연결해줘.
standard_column_aliases는 OPER_NAME -> OPER_SHORT_DESC, DEN -> DEN_TYP, TECH -> TECH_NM, MCP_NO -> MCP_SALE_CD로 연결해줘.
```
<!-- single_hold_history:end -->
