# Domain Authoring All-In-One Raw Text Example

아래 내용은 제조 데이터 분석 Agent에 초기 domain 지식을 한 번에 등록할 때 넣어볼 수 있는 자연어 입력 예시입니다.
운영자는 `gbn`, `key`, `payload` 같은 내부 JSON 구조를 몰라도 됩니다.
이미 같은 의미의 항목이 있으면 새 항목을 만들지 말고 기존 항목을 업데이트해줘.

<!-- bulk_domain:start -->
## 공정 그룹

DP 또는 D/P는 WET1, WET2, L/T1, L/T2, B/G1, B/G2, H/S1, H/S2, W/S1, W/S2, WSD1, WSD2, WEC1, WEC2, WLS1, WLS2, WVI, UV, C/C1을 모두 포함하는 공정 그룹이야.
WET 공정은 WET1, WET2를 의미해.
LT 또는 L/T는 L/T1, L/T2를 의미해.
BG 또는 B/G, 백그라인드, back grind는 B/G1, B/G2를 의미해.
HS 또는 H/S는 H/S1, H/S2를 의미해.
WS 또는 W/S는 W/S1, W/S2를 의미해.
WSD 공정은 WSD1, WSD2를 의미해.
WEC 공정은 WEC1, WEC2를 의미해.
WLS 공정은 WLS1, WLS2를 의미해.
DA 또는 D/A, 다이 어태치, die attach는 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6를 의미해.
PCO 공정은 PCO1, PCO2, PCO3, PCO4, PCO5, PCO6를 의미해.
DC 또는 D/C는 D/C1, D/C2, D/C3, D/C4를 의미해.
DI, D/I, DVI는 OPER_NAME이 D/I인 공정을 의미해.
DS 또는 D/S, 다이 싱귤레이션, die singulation은 OPER_NAME이 D/S1인 공정을 의미하고, FCBGA 조건은 기본으로 붙이지 말아줘.
FCB 공정은 FCB1, FCB2, FCB/H를 모두 포함해.
FCBH 또는 FCB/H는 OPER_NAME이 FCB/H인 공정만 의미해.
BM 또는 B/M, 비엠은 OPER_NAME이 B/M인 공정을 의미해.
PC 또는 P/C는 P/C1, P/C2, P/C3, P/C4, P/C5를 의미해.
MD 또는 M/D는 현재 OPER_NAME이 M/D인 공정을 의미해. 실제 데이터가 M/D1, M/D2처럼 관리되면 나중에 이 공정 목록만 보완하면 돼.
WB 또는 W/B, 와이어 본딩, wire bonding은 W/B1, W/B2, W/B3, W/B4, W/B5, W/B6를 의미해.
QCSPC 공정은 QCSPC1, QCSPC2, QCSPC3, QCSPC4를 의미해.
SAT 공정은 SAT1, SAT2를 의미해.
PL, P/L, PLH는 OPER_NAME이 PLH인 공정을 의미해.

## 제품 조건

POP 제품은 MODE가 LP로 시작하고, PKG_TYPE1이 LFBGA, TFBGA, UFBGA, VFBGA, WFBGA 중 하나이며, MCP_NO 값이 존재하고 NULL 또는 빈칸이 아닌 제품이야.
MOBILE 또는 모바일 제품은 MODE가 LP로 시작하고, PKG_TYPE1이 LFBGA, TFBGA, UFBGA, VFBGA, WFBGA 중 하나이며, MCP_NO 값이 NULL 또는 빈칸인 제품이야.
AUTO, AUTO향, 오토, 오토향, 오토모티브향 제품은 MCP_NO 값이 존재하고 빈칸이 아니며 맨 뒷자리 문자가 I, O, N, P, Q, V 중 하나인 제품이야.
HBM, 3DS, TSV, HBM 제품, TSV 제품, TSV 계열은 TSV_DIE_TYP 값이 존재하고 빈 값이 아닌 제품이야. FAMILY, PKG_TYPE1, PKG_TYPE2에 HBM이 들어간다는 이유만으로 HBM 제품으로 판단하지 말아줘.
유연제품 또는 flexible product는 FAB, DEVICE, OWER, GRADE가 동일하여 서로 연속 작업이 가능한 제품을 의미해.

## 업무 용어와 분석 기준

오늘, 현재, 지금, 금일, 당일이라고 말하면 같은 논리 데이터 중 당일 source 범위를 사용하고, 어제, 전일, 과거라고 말하면 이력 source 범위를 사용해.
production_today와 production은 생산 실적 계열이고, wip_today와 wip은 재공 계열이야.
이건 실제 SQL이나 물리 table을 등록하는 내용이 아니라, 질문의 날짜 표현을 보고 어느 source 범위를 고를지 정하는 해석 규칙이야.

제품별, 자재별, 품목별, 제품 구분, 자재 구분, product level, product grain은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO 조합을 기본 group_by 후보로 사용한다는 뜻이야.
제품 알려줘, 자재 알려줘, 품목 알려줘, 실적 있는 제품, 재공 없는 제품, 저조한 제품처럼 결과 대상이 제품 또는 자재인 질문도 같은 제품/자재 식별 기준으로 나누어 보여줘.
DEVICE와 DEVICE_DESC는 제품 또는 자재 식별 기준으로 사용하지 말아줘.
상위/하위/Top N 제품 질문은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO 조합으로 먼저 합산한 뒤 요청 수량 컬럼으로 정렬해줘.
OPER_NAME은 사용자가 공정별, 차수별, 세부공정별을 명시한 경우에만 group_by에 추가해줘.

디바이스, 디바이스별, 제품코드, 제품코드별, DEVICE, DEVICE CODE라고 명시하면 DEVICE, DEVICE_DESC 컬럼 기준으로 조회하거나 그룹핑해줘.
이건 제품을 거르는 조건이 아니라 결과를 나누어 보는 기준이야. 저장할 때는 DEVICE와 DEVICE_DESC를 기준 컬럼으로 사용해줘.
제품별/자재별과 디바이스별은 서로 다른 기준이야.

차수별, 공정 차수별, 단계별, process step, operation step이라고 하면 D/A1, D/A2, W/B1, W/B2처럼 OPER_NAME에 숫자가 붙은 실제 세부 공정 단위로 나누어야 하므로 OPER_NAME을 group_by에 포함해줘.
이건 새로운 공정 그룹을 만드는 내용이 아니라 결과를 세부 공정 단위로 나누어 보는 기준이야. D/A1, D/A2, W/B1, W/B2는 예시 값일 뿐 고정 조건으로 저장하지 말아줘.

생산계획, 생산목표, 일별 투입계획, SCHD, 계획, 목표는 target 데이터의 계획 컬럼을 의미해.
target 데이터의 INPUT계획 컬럼은 input plan 역할이고, OUT계획 컬럼은 output plan 역할이야.
INPUT계획, INPUT 목표, 투입계획은 투입 실적이 아니라 계획 데이터이므로 target 데이터의 INPUT계획 컬럼을 사용해줘.
OUT계획, OUT 목표, 생산목표는 target 데이터의 OUT계획 컬럼을 사용해줘.

생산량, 생산 실적, 실적, output quantity는 production 데이터의 PRODUCTION 컬럼 수량을 의미해.
INPUT 실적, INPUT 수량, 투입량은 production 데이터에서 OPER_NAME이 INPUT인 PRODUCTION 수량을 의미해.
다만 input수량 대비 또는 INPUT 실적 대비처럼 비교 기준으로 쓰일 때는 전체 production 조회를 INPUT으로만 필터링하지 말고, INPUT 수량을 기준 수량으로 따로 계산해줘.
결과 컬럼을 구분해야 하면 INPUT 실적은 PRODUCTION_INPUT으로 보여줘.

PKG OUT실적, PKG공정 OUT실적, OUT실적, OUT 실적, 출하 실적은 특정 공정명이 함께 언급되지 않았을 때 production 데이터에서 OPER_NAME 값이 SHIP PKT인 PRODUCTION 수량을 의미해.
W/B OUT실적처럼 별도 공정명이 명시되면 SHIP PKT보다 해당 공정 조건을 우선해줘.
위 표현들은 같은 OUT 실적 의미로 묶어서 저장해줘.

금일 투입중인 자재, 오늘 투입중인 자재, 투입중인 자재, 현재 투입 자재는 오늘 날짜 기준으로 OPER_NAME 값이 INPUT이고 PRODUCTION > 0인 생산 실적이 존재하는 제품 또는 자재를 의미해.
이 자재를 제품/자재 기준으로 볼 때는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO로 묶어줘.
여기서 오늘 날짜 기준이라는 말은 조회 날짜를 오늘로 잡는다는 뜻이고, 날짜 컬럼을 새로 등록하라는 뜻은 아니야.

공정 물량, 공정물량, 공정 재공, 재공수량, 재공 수량, WIP 수량은 해당 공정에 걸린 재공 수량을 의미하며 wip 데이터의 WIP 컬럼을 사용해.
전체 재공, 전체 공정 재공, 전체 WIP, 아침 전체 재공, 총 재공은 wip 데이터의 WIP 컬럼을 공정 필터 없이 조회한다는 뜻이야.
같은 질문에 PKG OUT 실적처럼 다른 데이터셋 전용 공정 조건이 함께 있어도 전체 재공에는 해당 공정 조건을 적용하지 말아줘.
공정 재공 계열 표현은 질문에 나온 공정 조건을 따르고, 전체 재공 계열 표현은 공정 조건을 빼고 보는 의미로 구분해서 저장해줘.

Lot 수량, LOT 수, Lot count, LOT 건수는 lot_status 데이터에서 LOT_ID 기준으로 서로 다른 LOT 개수를 세는 의미야.
SUB_PROD_QTY, WF_QTY 같은 수량을 합산하는 것이 아니라 LOT_ID를 기준으로 건수를 계산해줘.
공정별 Lot 수량이라고 하면 공정 기준으로 나눈 뒤 LOT_ID 개수를 세고, 제품별 Lot 수량이라고 하면 제품 기준으로 나눈 뒤 LOT_ID 개수를 세어줘.
작업대기 Lot, 작업 대기 LOT, 대기 Lot은 lot_status 데이터에서 LOT_STAT_CD 값이 WAITING인 Lot을 의미해.
작업대기 Lot 수량은 LOT_ID 개수를 세는 방식으로 계산해줘.
작업중 Lot, 작업 중 LOT, Running Lot은 lot_status 데이터에서 LOT_STAT_CD 값이 RUNNING인 Lot을 의미해.
작업중 Lot 수량은 LOT_ID 개수를 세는 방식으로 계산해줘.
현재 Hold Lot, HOLD Lot, 홀드 Lot, Hold Lot 수량은 lot_status 데이터에서 LOT_HOLD_STAT_CD 값이 OnHold인 Lot을 의미해.
현재 Hold Lot 수량은 LOT_ID 개수를 세는 방식으로 계산해줘.
현재 Hold Lot은 현재 상태를 보는 의미이므로 hold_history 데이터가 아니라 lot_status 데이터를 사용해줘.
HOT LOT, Hot Lot은 lot_status 데이터에서 HOT_LOT_YN 값이 Y인 Lot을 의미해.
HOT LOT 수량은 LOT_ID 개수를 세는 방식으로 계산해줘.
HOLD 이력, HOLD 발생 사유, HOLD 사유, HOLD 시간, HOLD 상세, HOLD 설명은 hold_history 데이터를 사용해줘.
hold_history는 특정 LOT_ID의 HOLD 발생 이력과 사유를 확인하는 데이터야.
현재 Hold Lot 수량이나 현재 Hold Lot 보유 제품을 물어보는 경우에는 hold_history가 아니라 lot_status 데이터를 사용해줘.
SUB_PROD_QTY와 WF_QTY는 Lot 건수가 아니라 수량 컬럼이고, IN_TAT와 CUM_TAT는 TAT 지표야.
사용자가 Lot별, LOT별이라고 하면 LOT_ID를 결과 구분 기준으로 포함해줘.

장비 할당, 장비 할당 제품, 장비가 할당된 제품, 장비 할당이 가장 많은 제품이라고 하면 equipment_status 데이터를 사용해줘.
장비 할당이 가장 많은 제품은 제품 기준으로 장비 할당 건수 또는 PRESS_CNT를 집계해서 판단해줘.
그 제품의 작업중 Lot 수량이나 Hold Lot 수량을 함께 물어보면 equipment_status로 먼저 제품을 찾고, lot_status에서 해당 제품의 Lot 상태를 확인해줘.
장비 현황, 설비 현황, 할당된 장비 현황은 equipment_status의 상세 row를 보여주는 의미야. 이때 result_mode는 detail_rows로 저장하고 EQPID, EQP_MODEL, PRESS_CNT, LOT_ID, RECIPE_ID를 보여줘.
장비 대수, 설비 대수, 장비 수, 설비 수, 몇 대는 equipment_status에서 EQPID를 중복 없이 세는 의미야. quantity_column은 EQPID, aggregation은 nunique, output_column은 EQP_COUNT로 저장해줘.

공정부터 공정까지, 공정~공정, 공정 범위, process range 표현은 해당 제품의 OPER_SEQ 순서를 기준으로 시작 공정과 끝 공정 사이의 모든 공정을 의미해.
MCP_NO 조건이 L-601처럼 알파벳-숫자 3자리 형태로 들어오면 MCP_NO가 그 값으로 시작하는 제품을 찾는 뜻이야. 여러 MCP_NO 값이 함께 언급되면 OR 조건으로 모두 포함해줘.
W/B1, D/A1처럼 세부 공정명이 직접 언급되면 공정 그룹 전체가 아니라 해당 세부 공정 하나만 의미해.
"그리고", "랑", "와", "과", "또는", OR로 서로 다른 공정 그룹이 함께 언급되면 각 공정 그룹 조건을 OR로 연결해줘.

저조제품, 생산 저조제품, 생산 저조한 제품, 저조한 제품, 저조라는 표현이 있을 때만 저조제품 판단, 시간 보정, 90% threshold 로직을 적용해줘.
부족, 미달, 부진만 포함된 질문은 저조제품 metric으로 해석하지 말아줘.

## Metric

생산달성율은 production 데이터와 target 데이터를 같이 사용해서 계산해.
계산식은 sum(PRODUCTION) / sum(OUT계획) * 100 이야.
PRODUCTION은 production 테이블의 PRODUCTION 컬럼이고, OUT계획은 target 테이블의 OUT계획 컬럼이야.
사용자는 생산달성률, 생산 달성률, 달성율, achievement rate 같은 표현으로도 물어볼 수 있어.
계산할 때는 각 데이터에서 PRODUCTION과 OUT계획을 먼저 집계한 뒤 달성율을 계산해줘.
행별로 달성율을 계산한 다음 평균내는 방식은 사용하지 말아줘.

생산 포화율은 현재 별도 capacity 데이터가 없을 때 target 데이터의 OUT계획을 생산 가능 기준으로 보고 계산해.
계산식은 sum(PRODUCTION) / sum(OUT계획) * 100 이야.
PRODUCTION은 production 데이터의 PRODUCTION 컬럼이고, 기준 수량은 target 데이터의 OUT계획 컬럼이야.
생산 포화율, 생산포화율, 포화율, saturation rate, production saturation이라는 표현으로 물어볼 수 있어.
요청한 group_by 기준으로 먼저 PRODUCTION과 OUT계획을 각각 합산한 뒤 production_saturation_rate를 계산하고, 행별 포화율을 평균내지 말아줘.
나중에 별도 capacity 데이터셋이 등록되면 기준 수량 역할만 capacity 데이터로 바꾸면 돼.

생산 목표 미달은 계획 대비 실적 미달, PKG OUT 실적 미달, 차이수량, Bal 표현과 함께 production 데이터와 target 데이터를 사용해 계산해.
계산식은 max(sum(OUT계획) - sum(PRODUCTION), 0)이야.
OUT계획은 target 데이터의 OUT계획 컬럼이고 PRODUCTION은 production 데이터의 PRODUCTION 컬럼이야.
요청한 제품/공정 grouping grain에서 OUT계획 합계보다 PRODUCTION 합계가 작은 항목을 찾는 지표로 사용해줘.
INPUT 실적 대비 저조처럼 실적 대비 실적 비교에는 이 metric을 쓰지 말아줘.
행별 부족 수량을 먼저 계산한 뒤 합산하지 말고, 요청한 group_by 기준으로 OUT계획과 PRODUCTION을 먼저 합산한 뒤 미달 수량을 계산해줘.

동적TAT는 wip 데이터와 production 데이터를 같이 사용해 계산해.
계산식은 sum(WIP) / sum(PRODUCTION)이야.
WIP은 wip 데이터의 WIP 컬럼이고 PRODUCTION은 production 데이터의 PRODUCTION 컬럼이야.
PRODUCTION 합계가 0이거나 없으면 dynamic_tat는 null로 두고 나누지 말아줘.
요청한 group_by 기준으로 WIP과 PRODUCTION을 먼저 합산한 뒤 동적TAT를 계산하고, 행 단위 TAT를 먼저 계산한 뒤 평균내지 말아줘.

저조제품 비교 공통 규칙은 "A 대비 B 저조제품" 표현에서 A를 기준 수량, B를 비교 수량으로 해석하는 규칙이야.
계획 대비 저조, 실적 대비 저조, CAPA 대비 저조, low output comparison처럼 물어볼 수 있어.
한쪽이 생략된 일반 저조제품 질문은 기본적으로 계획 또는 목표 대비 실적 비교로 봐줘.
비교 수량이 기준 수량의 90% 이하이면 저조로 판단해줘.
가능한 source column은 PRODUCTION, OUT계획, INPUT계획, UPH야.
오늘 조회이면 계획은 sum(OUT계획) / 24 * elapsed_hours_since_07, CAPA는 sum(UPH) * elapsed_hours_since_07로 보정하고, 과거 조회이면 각각 전체 일계획과 24시간 CAPA를 사용해줘.
각 source를 같은 제품/자재/date grain으로 집계한 뒤 baseline 집계 결과를 왼쪽 기준으로 left join하고, compare_quantity가 없으면 0으로 채워줘.
저조 여부 컬럼은 low_output_comparison으로 만들고, 참인 행만 남겨줘.

계획 대비 생산 저조제품은 target 데이터의 계획 컬럼과 production 데이터의 PRODUCTION 컬럼을 비교해 찾는 지표야.
INPUT계획 또는 투입계획은 target.INPUT계획을 우선 사용하고, 일반 생산목표 또는 OUT계획은 target.OUT계획을 우선 사용해줘.
target 데이터가 공정별 OPER_NAME을 가지고 있으면 기준과 비교 양쪽 모두 OPER_NAME을 보존해서 같은 공정끼리 비교해줘.
비교 수량이 계획 수량의 90% 이하이면 저조로 판단하고, 저조인 행만 남겨줘.

CAPA 대비 저조제품은 capacity 데이터의 UPH와 production 데이터의 PRODUCTION을 비교해 찾는 지표야.
오늘 조회이면 CAPA 기준 수량은 sum(UPH) * elapsed_hours_since_07이고, 과거 조회이면 sum(UPH) * 24야.
비교 수량인 PRODUCTION이 CAPA 기준 수량의 90% 이하이면 저조로 판단해줘.

INPUT 실적 대비 공정 생산 저조제품은 INPUT 공정의 투입 실적과 사용자가 선택한 공정의 생산 실적을 비교해서 찾는 지표야.
INPUT 실적은 production 데이터에서 OPER_NAME이 INPUT인 PRODUCTION 수량이고, 선택 공정 생산량도 production 데이터의 PRODUCTION 수량이야.
선택 공정이 B/G처럼 공정 그룹이면 그룹 합계로 한 번 비교하지 말고 B/G1, B/G2 같은 개별 OPER_NAME별로 각각 비교해줘.
같은 제품 또는 자재 기준으로 INPUT 수량과 선택 공정 수량을 먼저 합산하고, 선택 공정 수량이 INPUT 수량의 90% 이하이면 저조로 판단해줘.
비교 수량이 없으면 0으로 보고, 저조로 판단된 행만 결과로 남겨줘.
결과에는 baseline_quantity, compare_quantity, compare_rate, low_output_vs_input을 만들고, OPER_NAME도 보존해줘.

## Join Rule

production 실적과 target 계획을 제품 또는 자재 기준으로 비교할 때는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO를 같은 값끼리 연결해줘.
기본 결합은 production 쪽 결과를 기준으로 target 계획을 붙이는 방식이면 돼.
이 기준은 생산달성율이나 목표 대비 실적 비교처럼 production과 target을 함께 쓰는 분석에서 사용해줘.

<!-- 2026-06-11 추가: LOT 상태 상세 조회와 LOT/Wafer/Die 수량 해석 규칙 -->

현재 HOLD 상태인 LOT, hold상태 lot list, HOLD lot 목록, hold lot list처럼 현재 상태의 LOT 목록을 물어보면 hold_history가 아니라 lot_status 데이터를 사용해줘.
이건 집계 수량이 아니라 상세 행 목록을 보여주는 의미야.
결과는 LOT_ID, OPER_ID, OPER_SHORT_DESC, FAB_ID, OWNER_CD, GRADE_CD, PROD_ID, LOT_HOLD_STAT_CD, LOT_STAT_CD, REASON_CD, SUB_PROD_QTY, WF_QTY, IN_TAT, CUM_TAT, EQP_ID를 보여주면 돼.
조건은 LOT_HOLD_STAT_CD 값이 HOLD 또는 Y 또는 ONHOLD처럼 현재 HOLD 상태를 뜻하는 값인 행이야.
이 규칙은 상세 조회 규칙으로 저장하고 result_mode는 detail_rows로 봐줘. LOT 수량으로 합산하지 말아줘.

HOLD 이력, HOLD 발생 사유, HOLD 사유, HOLD 시간, HOLD 상세를 물어보면 hold_history 데이터를 사용해줘.
hold_history는 특정 LOT_ID의 HOLD 발생 이력과 사유를 보는 데이터이고, 실제 조회에는 LOT_ID가 필요해.
이력 조회 결과는 LOT_ID, HOLD_TM, RELEASE_DUE_DATE, HOLD_CD, HOLD_USER_ID, HOLD_DESC, OPER_ID, OPER_SHORT_DESC, EVENT_CD를 보여주면 돼.

현재 공정에서 재공 LOT이 몇 개인지, 작업중 LOT 수량, 작업대기 LOT 수량, HOLD LOT 수량처럼 LOT 개수를 물어보면 lot_status 데이터를 사용해줘.
LOT 개수는 LOT_ID의 고유 개수를 세는 방식이야.
LOT 수량 용어는 quantity_column을 LOT_ID로 두고 aggregation은 nunique로 저장해줘.

wafer 수량, wafer가 몇 개인지, WF 수량은 lot_status 데이터의 WF_QTY 합계를 의미해.
die 수량, die가 몇 개인지, SUB PROD 수량은 lot_status 데이터의 SUB_PROD_QTY 합계를 의미해.
작업중/작업대기/HOLD 같은 LOT 상태 조건이 함께 있으면 lot_status의 상태 컬럼 조건으로 해석해줘.

현재 DA공정 재공 수량처럼 단순 재공 수량이나 WIP 수량을 물어보면 wip_today 또는 wip 데이터의 WIP 컬럼을 사용해줘.
현재 DA공정에서 재공 LOT이 몇 개인지, wafer가 몇 개인지, die수량은 몇 개인지처럼 LOT/wafer/die 단위를 직접 물어보면 wip_today가 아니라 lot_status 데이터를 사용해줘.

재공이 많은 세부공정 top N을 먼저 찾고, 그 공정들의 HOLD LOT 수와 평균 IN TAT를 같이 보여달라는 질문은 복합 순차 분석 recipe로 저장해줘.
이 recipe의 key는 top_wip_process_hold_lot_in_tat이고 analysis_kind도 top_wip_process_hold_lot_in_tat이야.
intent_type은 multi_step_analysis로 저장해줘.
질문 cue는 재공, 공정, hold, in tat이고, "hold LOT 평균 in tat", "재공 많은 공정 hold lot" 같은 표현으로도 물어볼 수 있어.
필수 질문 cue는 재공/WIP, 공정/세부공정, hold/홀드, in tat/IN_TAT가 모두 포함되어야 해.
생산량 상위, 장비 대수, 설비 대수, 장비 수처럼 생산/장비 대수 질문이면 이 recipe를 적용하지 않도록 forbidden_question_cues로 저장해줘.
필요한 dataset family는 wip과 lot이고, source alias는 wip은 wip_data, lot은 lot_status_data를 사용해.
이 분석은 제품 grain이 아니라 recipe step 내부의 공정 grain을 사용하므로 grain_policy는 recipe_step_grain으로 저장해줘.
WIP source의 필수 컬럼은 WORK_DT, OPER_NAME, WIP이고, lot source의 필수 컬럼은 OPER_SHORT_DESC, LOT_ID, LOT_HOLD_STAT_CD, IN_TAT야.
LLM이 lot_count_by_process, rank_top_n, aggregate_wip_total처럼 단순 분석으로 잘못 잡아도 이 recipe가 우선 적용되도록 override_analysis_kinds에 넣어줘.
이 recipe는 기존 retrieval_jobs와 step_plan을 교체하는 패턴이므로 replace_datasets, replace_retrieval_jobs, override_step_plan을 true로 저장해줘.
HOLD 조건은 lot_status 조회 필터로 먼저 걸지 말고 HOLD_LOT_COUNT 계산 조건으로 사용해야 하므로 blocked_filter_fields에는 LOT_HOLD_STAT_CD와 LOT_STAT_CD를 넣어줘.
top_n은 질문에 숫자가 있으면 그 숫자를 쓰고, 없으면 기본 3을 쓰도록 top_n_policy는 question_or_default, defaults.top_n은 3으로 저장해줘.
step_plan_template는 1) wip_data를 OPER_NAME별로 WIP 합산 후 desc top_n 랭킹하고 rename_columns로 OPER_NAME을 OPER_SHORT_DESC로 바꿈, 2) lot_status_data에서 해당 공정들의 HOLD_LOT_COUNT와 AVG_IN_TAT 계산, 3) OPER_SHORT_DESC 기준 left join 순서로 저장해줘.
최종 output_columns는 OPER_SHORT_DESC, WIP, HOLD_LOT_COUNT, AVG_IN_TAT야.

재공이 가장 많은 제품을 먼저 찾고, 그 제품 기준으로 LOT의 IN TAT가 가장 오래된 LOT을 찾아달라는 질문은 top_wip_product_oldest_lot recipe로 저장해줘.
analysis_kind도 top_wip_product_oldest_lot이고, 필수 질문 cue는 재공/WIP, 제품/product, LOT, IN TAT/IN_TAT, 오래된/최장/oldest가 모두 포함되어야 해.
필요한 dataset family는 wip과 lot이고, source alias는 wip은 wip_data, lot은 lot_data를 사용해.
grain_policy는 question_or_product_grain이고, 제품 기준 컬럼은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO를 사용해.
WIP source 필수 컬럼은 WORK_DT, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, WIP이고, lot source 필수 컬럼은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_SHORT_DESC, LOT_ID, IN_TAT야.
이 recipe는 기존 retrieval_jobs와 step_plan을 교체하므로 replace_datasets, replace_retrieval_jobs, override_step_plan을 true로 저장해줘.
step_plan_template는 1) wip_data를 제품 기준으로 WIP 합산 후 desc top 1 제품 선정, 2) lot_data를 해당 제품키로 필터하고 IN_TAT desc top 1 LOT 선정, 3) 제품키 기준 left join 순서로 저장해줘.
최종 output_columns는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, WIP, LOT_ID, IN_TAT야.

생산량 상위 N개 제품과 각 제품별 할당 장비 대수를 같이 보여달라는 질문은 top_production_products_equipment_count recipe로 저장해줘.
analysis_kind도 top_production_products_equipment_count이고, 필수 질문 cue는 생산량/생산/PRODUCTION, 제품/product, 장비/설비/equipment, 대수/수/count가 모두 포함되어야 해.
필요한 dataset family는 production과 equipment이고, source alias는 production은 production_data, equipment는 equipment_data를 사용해.
grain_policy는 question_or_product_grain이고, 제품 기준 컬럼은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO를 사용해.
production source 필수 컬럼은 WORK_DT, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, PRODUCTION이고, equipment source 필수 컬럼은 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, EQPID야.
top_n은 질문에 숫자가 있으면 그 숫자를 쓰고, 없으면 기본 5를 쓰도록 top_n_policy는 question_or_default, defaults.top_n은 5로 저장해줘.
step_plan_template는 1) production_data를 제품 기준으로 PRODUCTION 합산 후 desc top_n 선정, 2) equipment_data를 해당 제품키로 필터하고 EQPID.nunique()로 EQP_COUNT 계산, 3) 제품키 기준 left join 순서로 저장해줘.
최종 output_columns는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, PRODUCTION, EQP_COUNT야.
<!-- bulk_domain:end -->

## 단일 항목 예시

<!-- single_da_process:start -->
```text
DA 공정 그룹을 등록할게요.
DA 또는 D/A, 다이 어태치, die attach는 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6를 의미해.
```
<!-- single_da_process:end -->
