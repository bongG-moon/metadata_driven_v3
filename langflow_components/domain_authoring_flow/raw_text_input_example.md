# Domain Authoring Raw Text Examples

아래 예시는 작업자가 자연어로 입력할 수 있는 최소 샘플입니다.
필요한 항목만 복사해서 등록하고, 같은 의미의 항목이 이미 있으면 기존 항목을 업데이트하도록 입력하면 됩니다.

<!-- bulk_domain:start -->
```text
[공정 그룹]
DP 또는 D/P는 WET1, WET2, L/T1, L/T2, B/G1, B/G2, H/S1, H/S2, W/S1, W/S2, WSD1, WSD2, WEC1, WEC2, WLS1, WLS2, WVI, UV, C/C1을 포함하는 공정 그룹이야.
WET는 WET1, WET2를 포함해.
LT 또는 L/T는 L/T1, L/T2를 포함해.
BG 또는 B/G는 B/G1, B/G2를 포함해.
HS 또는 H/S는 H/S1, H/S2를 포함해.
WS 또는 W/S는 W/S1, W/S2를 포함해.
WSD는 WSD1, WSD2를 포함해.
WEC는 WEC1, WEC2를 포함해.
WLS는 WLS1, WLS2를 포함해.
DA 또는 D/A는 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6를 포함해.
PCO는 PCO1, PCO2, PCO3, PCO4, PCO5, PCO6를 포함해.
D/C는 D/C1, D/C2, D/C3, D/C4를 포함해.
D/I 또는 DI 또는 DVI는 D/I를 의미해.
D/S 또는 DS는 D/S1을 의미하며, PKG_TYPE1이 FCBGA인 자재만 해당해.
FCB는 FCB1, FCB2, FCB/H를 포함해.
FCB/H 또는 FCBH는 FCB/H를 의미해.
B/M 또는 BM 또는 비엠은 B/M을 의미해.
P/C는 P/C1, P/C2, P/C3, P/C4, P/C5를 포함해.
W/B 또는 WB는 W/B1, W/B2, W/B3, W/B4, W/B5, W/B6를 포함해.
QCSPC는 QCSPC1, QCSPC2, QCSPC3, QCSPC4를 포함해.
SAT는 SAT1, SAT2를 포함해.
P/L 또는 PLH는 PLH를 의미해.

[제품 조건]
제품, PRODUCT, DEVICE, 자재는 같은 의미의 분석 대상 표현이야.
POP 제품은 MODE가 LP로 시작하고, PKG_TYPE1이 LFBGA, TFBGA, UFBGA, VFBGA, WFBGA 중 하나이며, MCP_SALES_NO 또는 MCP_NO 값이 존재하고 NULL 또는 빈칸이 아닌 제품이야.
MOBILE 제품은 MODE가 LP로 시작하고, PKG_TYPE1이 LFBGA, TFBGA, UFBGA, VFBGA, WFBGA 중 하나이며, MCP_SALES_NO 또는 MCP_NO 값이 NULL이거나 빈칸인 제품이야.
AUTO향, 오토모티브향, 오토향은 MCP_SALES_NO 또는 MCP_NO 값이 존재하고 맨 뒷자리 문자가 I, O, N, P, Q, V 중 하나인 경우야.
HBM 또는 3DS 제품은 TSV_DIE_TYP 값이 존재하고 NULL 또는 빈칸이 아닌 제품이야.
2Hi, 4Hi, 8Hi 같은 적층 구분은 TSV_DIE_TYP 컬럼 값으로 구분해.
유연제품, 유연생산 제품, 유연작업제품은 FAB, DEVICE, OWNER, GRADE가 동일한 제품을 말하며 해당 제품끼리는 연속 작업이 가능해.

[수량 용어]
재공, WIP, 공정 물량은 wip 계열 데이터의 WIP 컬럼 합계를 의미해.
생산량, 생산 실적, output quantity는 production 계열 데이터의 PRODUCTION 컬럼 합계를 의미해.
투입량은 PKG INPUT 공정의 생산 실적이며, OPER_DESC 값이 INPUT인 production 계열 데이터의 PRODUCTION 합계를 의미해.
스케쥴, 스케줄, 생산계획, SCHD, 투입계획, 일별 투입계획은 모두 생산계획 데이터 또는 target 계열 데이터를 의미해.

[Metric]
생산달성률은 production 데이터의 sum(PRODUCTION) / target 데이터의 sum(OUT계획) * 100 으로 계산해.
행별 달성률을 평균내지 말고, 먼저 각 수량을 집계한 뒤 계산해줘.

[Join Rule]
production, wip, target 데이터를 제품 기준으로 결합할 때는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO를 기본 제품 키로 사용해.
```
<!-- bulk_domain:end -->

## 단일 항목 예시

<!-- single_da_process:start -->
```text
DA 공정 그룹을 등록해줘.
DA 또는 D/A, 다이 어태치, die attach는 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6를 포함하는 공정 그룹이야.
```
<!-- single_da_process:end -->
