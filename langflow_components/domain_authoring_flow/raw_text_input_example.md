# Domain Authoring Raw Text Examples

이 파일은 domain metadata 컬렉션을 비우고 자연어 입력으로 다시 쌓을 때 사용할 기준 예시입니다.

권장 방식:
- 한 번에 전부 넣기보다 아래 `single_*` 블록을 하나씩 Domain Authoring Flow에 입력합니다.
- 기존 항목을 새 기준으로 갈아엎을 때는 flow의 duplicate action을 `replace`로 둡니다.
- 여기 문장은 작업자가 실제로 말할 수 있는 자연어 수준을 기준으로 작성했습니다.
- `dataset_key`를 꼭 고정해야 하는 경우가 아니면 `production`, `wip`, `target`, `equipment`, `lot` 같은 dataset_family 중심으로 저장합니다.
- 물리 컬럼명이 dataset마다 다를 수 있는 항목은 main flow filter와 table catalog의 mapping을 통해 맞춥니다.

## 항목별 입력 기준

아래 블록들은 Domain Authoring Flow에 하나씩 넣기 위한 기준 입력입니다.

<!-- single_process_group_dp:start -->
```text
DP 또는 D/P 공정 그룹은 OPER_NAME 값 WET1, WET2, L/T1, L/T2, B/G1, B/G2, H/S1, H/S2, W/S1, W/S2, WSD1, WSD2, WEC1, WEC2, WLS1, WLS2, WVI, UV, C/C1을 포함해.
```
<!-- single_process_group_dp:end -->

<!-- single_process_group_wet:start -->
```text
WET 공정 그룹은 OPER_NAME 값 WET1, WET2를 포함해.
```
<!-- single_process_group_wet:end -->

<!-- single_process_group_lt:start -->
```text
LT 또는 L/T 공정 그룹은 OPER_NAME 값 L/T1, L/T2를 포함해.
```
<!-- single_process_group_lt:end -->

<!-- single_process_group_bg:start -->
```text
BG 또는 B/G 공정 그룹은 OPER_NAME 값 B/G1, B/G2를 포함해.
```
<!-- single_process_group_bg:end -->

<!-- single_process_group_hs:start -->
```text
HS 또는 H/S 공정 그룹은 OPER_NAME 값 H/S1, H/S2를 포함해.
```
<!-- single_process_group_hs:end -->

<!-- single_process_group_ws:start -->
```text
WS 또는 W/S 공정 그룹은 OPER_NAME 값 W/S1, W/S2를 포함해.
```
<!-- single_process_group_ws:end -->

<!-- single_process_group_wsd:start -->
```text
WSD 공정 그룹은 OPER_NAME 값 WSD1, WSD2를 포함해.
```
<!-- single_process_group_wsd:end -->

<!-- single_process_group_wec:start -->
```text
WEC 공정 그룹은 OPER_NAME 값 WEC1, WEC2를 포함해.
```
<!-- single_process_group_wec:end -->

<!-- single_process_group_wls:start -->
```text
WLS 공정 그룹은 OPER_NAME 값 WLS1, WLS2를 포함해.
```
<!-- single_process_group_wls:end -->

<!-- single_process_group_da:start -->
```text
D/A 또는 DA 공정 그룹은 OPER_NAME 값 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6를 포함해.
```
<!-- single_process_group_da:end -->

<!-- single_process_group_pco:start -->
```text
PCO 공정 그룹은 OPER_NAME 값 PCO1, PCO2, PCO3, PCO4, PCO5, PCO6를 포함해.
```
<!-- single_process_group_pco:end -->

<!-- single_process_group_dc:start -->
```text
D/C 공정 그룹은 OPER_NAME 값 D/C1, D/C2, D/C3, D/C4를 포함해.
```
<!-- single_process_group_dc:end -->

<!-- single_process_group_di:start -->
```text
D/I 또는 DI 또는 DVI 공정 그룹은 OPER_NAME 값 D/I를 의미해.
```
<!-- single_process_group_di:end -->

<!-- single_process_group_ds:start -->
```text
D/S 또는 DS 공정 그룹은 OPER_NAME 값 D/S1을 의미하고 PKG_TYPE1 조건은 없어.
```
<!-- single_process_group_ds:end -->

<!-- single_process_group_fcb:start -->
```text
FCB 공정 그룹은 OPER_NAME 값 FCB1, FCB2, FCB/H를 포함해.
```
<!-- single_process_group_fcb:end -->

<!-- single_process_group_fcbh:start -->
```text
FCB/H 또는 FCBH 공정 그룹은 OPER_NAME 값 FCB/H를 의미해.
```
<!-- single_process_group_fcbh:end -->

<!-- single_process_group_bm:start -->
```text
B/M 또는 BM 또는 비엠 공정 그룹은 OPER_NAME 값 B/M을 의미해.
```
<!-- single_process_group_bm:end -->

<!-- single_process_group_pc:start -->
```text
P/C 공정 그룹은 OPER_NAME 값 P/C1, P/C2, P/C3, P/C4, P/C5를 포함해.
```
<!-- single_process_group_pc:end -->

<!-- single_process_group_wb:start -->
```text
W/B 또는 WB 공정 그룹은 OPER_NAME 값 W/B1, W/B2, W/B3, W/B4, W/B5, W/B6를 포함해.
```
<!-- single_process_group_wb:end -->

<!-- single_process_group_qcspc:start -->
```text
QCSPC 공정 그룹은 OPER_NAME 값 QCSPC1, QCSPC2, QCSPC3, QCSPC4를 포함해.
```
<!-- single_process_group_qcspc:end -->

<!-- single_process_group_sat:start -->
```text
SAT 공정 그룹은 OPER_NAME 값 SAT1, SAT2를 포함해.
```
<!-- single_process_group_sat:end -->

<!-- single_process_group_plh:start -->
```text
P/L 또는 PLH 공정 그룹은 OPER_NAME 값 PLH를 의미해.
```
<!-- single_process_group_plh:end -->

<!-- single_process_group_sg:start -->
```text
S/G 또는 SG 또는 S/G공정 또는 SG공정은 OPER_NAME 값이 S/G인 공정을 의미해.
```
<!-- single_process_group_sg:end -->

<!-- single_process_group_sbm:start -->
```text
SBM 또는 SBM공정은 OPER_NAME 값이 SBM인 공정을 의미해.
```
<!-- single_process_group_sbm:end -->

<!-- single_process_step_suffix_rule:start -->
```text
공정 차수 표현 규칙을 등록해줘.
이 블록은 공정 그룹을 새로 등록하는 것이 아니라 차수 표현을 해석하는 analysis recipe 규칙으로 저장해줘.
아래 예시는 규칙 설명을 위한 예시일 뿐이므로 D/A1, W/B2 같은 예시 공정을 별도 process_groups item으로 만들지 마.
전용 내부 필드가 없으면 calculation_rule 또는 pandas_generation_rule에 자연어 규칙으로 보존해도 돼.
공정명 뒤에 N차처럼 차수 번호가 붙으면 해당 공정 그룹 전체가 아니라 그 숫자가 붙은 단일 세부 공정을 의미해.
1차는 공정명 뒤에 1이 붙은 OPER_NAME, 2차는 2가 붙은 OPER_NAME, 3차는 3이 붙은 OPER_NAME, 4차는 4가 붙은 OPER_NAME처럼 차수 번호 N을 공정명 뒤 숫자 N과 매칭해서 해석해.
예를 들어 D/A 1차, DA 1차, D/A1차, DA1차는 D/A1 공정을 의미해.
W/B 2차, WB 2차, W/B2차, WB2차는 W/B2 공정을 의미해.
공정 차수 표현은 broad 공정 그룹 필터가 아니라 해당 숫자가 붙은 단일 OPER_NAME 필터로 적용해.
사용자가 "차수별로 보여줘"처럼 특정 차수를 지정하지 않고 전체 차수별 분해를 요청하면 공정 그룹에 포함된 세부 OPER_NAME 기준으로 group by 해서 보여줘.
```
<!-- single_process_step_suffix_rule:end -->

<!-- single_shift_terms:start -->
```text
Shift와 조 조건을 등록해줘.
Shift A조, A조, 1조는 같은 의미이고 SHIFT 값이 1인 데이터를 뜻해.
07:00~15:00, 07:00 ~ 15:00, 07:00-15:00, 07시부터 15시까지, 7시부터 15시까지라고 말하면 A조 조건으로 해석해.
Shift B조, B조, 2조는 같은 의미이고 SHIFT 값이 2인 데이터를 뜻해.
15:00~23:00, 15:00 ~ 23:00, 15:00-23:00, 15시부터 23시까지라고 말하면 B조 조건으로 해석해.
Shift C조, C조, 3조는 같은 의미이고 SHIFT 값이 3인 데이터를 뜻해.
23:00~07:00, 23:00 ~ 07:00, 23:00-07:00, 23시부터 다음날 7시까지라고 말하면 C조 조건으로 해석해.
조별 실적, Shift별 실적, A조 실적처럼 물으면 해당 SHIFT 조건을 필터로 사용해.
```
<!-- single_shift_terms:end -->

<!-- single_product_synonym_rule:start -->
```text
제품, PRODUCT, DEVICE, 자재는 같은 의미를 가진 분석 대상 표현이야.
이건 특정 제품 조건이 아니라 사용자가 제품 단위 분석을 요청했다는 표현으로 해석하는 analysis recipe 규칙으로 저장해줘.
```
<!-- single_product_synonym_rule:end -->

<!-- single_product_pop:start -->
```text
POP 제품 조건을 등록해줘.
POP 제품은 MODE가 LP로 시작하고, PKG_TYPE1이 LFBGA, TFBGA, UFBGA, VFBGA, WFBGA 중 하나이며, MCP_NO 값이 존재하고 NULL 또는 빈칸이 아닌 제품이야.
```
<!-- single_product_pop:end -->

<!-- single_product_mobile:start -->
```text
MOBILE 제품 조건을 등록해줘.
section은 product_terms이고 key는 MOBILE_PRODUCT야.
display_name은 MOBILE 제품이고 aliases는 MOBILE 제품, MOBILE이야.
MOBILE 제품은 MODE가 LP로 시작하고, PKG_TYPE1이 LFBGA, TFBGA, UFBGA, VFBGA, WFBGA 중 하나이며, MCP_NO 값이 NULL이거나 빈칸인 제품이야.
production, wip, lot, equipment, capacity 계열 모두 같은 조건을 condition_by_family로 저장해.
```
<!-- single_product_mobile:end -->

<!-- single_product_auto:start -->
```text
AUTO향 제품 조건을 등록해줘.
AUTO향, 오토모티브향, 오토향은 MCP_NO 값이 존재하고 MCP_NO 맨 뒷자리 문자가 I, O, N, P, Q, V 중 하나인 제품을 말해.
```
<!-- single_product_auto:end -->

<!-- single_product_hbm_3ds_tsv:start -->
```text
HBM, 3DS, TSV 제품 조건을 등록해줘.
HBM, 3DS, TSV 제품은 TSV_DIE_TYP 값이 존재하고 NULL 또는 빈칸이 아닌 제품으로 판단해.
```
<!-- single_product_hbm_3ds_tsv:end -->

<!-- single_product_stack_height:start -->
```text
적층 단수 제품 조건을 등록해줘.
2Hi 제품은 TSV_DIE_TYP 값이 2Hi인 제품이야.
4Hi 제품은 TSV_DIE_TYP 값이 4Hi인 제품이야.
8Hi 제품은 TSV_DIE_TYP 값이 8Hi인 제품이야.
2Hi, 4Hi, 8Hi 같은 적층 단수 구분은 TSV_DIE_TYP 컬럼 값으로 구분해.
```
<!-- single_product_stack_height:end -->

<!-- single_product_flexible:start -->
```text
유연제품 조건을 등록해줘.
유연제품, 유연생산 제품, 유연작업제품은 FAB, DEVICE, OWNER, GRADE가 동일한 제품을 말하며 해당 제품끼리는 연속 작업이 가능해.
이 항목은 product_terms로 저장하고, 비교 기준 컬럼은 FAB, DEVICE, OWNER, GRADE야.
```
<!-- single_product_flexible:end -->

<!-- single_pandas_function_case_component_token_product_lookup:start -->
```text
제품 찾기 질문에서 사용자가 "2048G H-HBM16E 제품 찾아줘"처럼 제품 속성 토큰을 자유롭게 입력하면,
일반 제품군 조건으로 해석하지 말고 pandas_function_cases의 component_token_product_lookup 케이스로 저장해줘.
이 케이스는 match_product_tokens helper를 사용해서 조회된 제품 데이터에서 일치하는 제품 row를 찾는 용도야.
helper의 실제 코드 예시는 MongoDB raw text에 넣지 말고 14 Pandas Prompt Builder / 15 Pandas Code Executor의 Specialized Functions 입력 또는 별도 helper package에서 관리해.
```
<!-- single_pandas_function_case_component_token_product_lookup:end -->

<!-- single_device_code_field_rule:start -->
```text
DEVICE 첨자 용어를 등록해줘.
DEVICE 첨자, Device 첨자, 첨자, DEVICE CODE, Device Code는 DEVICE 컬럼을 말해.
DEVICE_DESC는 제품 설명 컬럼이고 DEVICE CODE와는 구분해.
사용자가 DEVICE 첨자를 알려달라고 하면 결과 컬럼에 DEVICE를 포함해.
이건 제품 키 정의가 아니라 질문에 따라 출력 컬럼을 선택하는 analysis_recipes 규칙으로 저장해줘.
```
<!-- single_device_code_field_rule:end -->

<!-- single_process_grouping_rule:start -->
```text
세부 공정별 결과 표시 규칙을 등록해줘.
세부 공정, 상세 공정은 OPER_NAME 기준으로 결과를 나누어 보여달라는 뜻이야.
이 항목은 analysis_recipes로 저장해줘.
```
<!-- single_process_grouping_rule:end -->

<!-- single_process_sequence_grouping_rule:start -->
```text
공정 차수별 결과 표시 규칙을 등록해줘.
공정명과 함께 1차, 2차처럼 특정 차수를 말하면 해당 숫자가 붙은 단일 OPER_NAME으로 필터링해.

특정 차수를 지정하지 않고 차수별, 공정 차수별로 보여달라고 하면 공정 그룹에 포함된 세부 OPER_NAME 기준으로 결과를 나누어 보여줘.

OPER_NUM 또는 OPER_SEQ는 table catalog에 명확히 공정 차수 컬럼으로 정의되어 있고 사용자가 공정 번호 기준을 요구할 때만 사용해.

공정 그룹에 등록된 기준이 아닌 A공정~B공정 이런식으로 질문할 때는 A공정의 OPER_SEQ보다 크거나 같으면서 B공정의 OPER_SEQ보다 작거나 같은 공정들을 뜻하는거야.
이 항목은 analysis_recipes로 저장해줘.
```
<!-- single_process_sequence_grouping_rule:end -->

<!-- single_quantity_terms:start -->
```text
수량 용어를 등록해줘.
재공, 재공수량, WIP, 공정 물량은 wip 계열 데이터의 WIP 컬럼 합계를 의미해.

현재 재공, 지금 재공, 금일 현재 재공은 wip_today 계열 데이터를 사용해.

생산량, 생산실적, 실적은 production 계열 데이터의 PRODUCTION 컬럼 합계를 의미해.
OUTPUT, OUT, Out Put, output 실적, out 실적은 production 계열 데이터의 PRODUCTION 컬럼 합계를 의미해.

특정 공정의 OUTPUT, 실적을 물으면 production 계열 데이터에서 해당 OPER_NAME 조건을 적용하고 PRODUCTION을 집계해.

투입량, INPUT, input, INPUT실적, INPUT생산량, 투입 실적은 PKG INPUT 공정의 생산 실적을 의미하고, production 계열 데이터에서 OPER_NAME 값이 'INPUT'인 행의 PRODUCTION 합계로 계산해.


계획, 스케쥴, 스케줄, SCHD, 투입계획, 일별 투입계획, 생산계획은 target 계열 데이터를 의미해.
계획이나 스케쥴 문자가 질문에 포함되지 않으면 target 계열 데이터는 사용하지 않아.

장비 대수, 설비 대수, 장비 수, 설비 수, 몇 대는 equipment 계열 데이터에서 EQP_ID 또는 EQPID의 중복 제거 개수로 계산해.
```
<!-- single_quantity_terms:end -->

<!-- single_boh_wip_temporal_rule:start -->
```text
BOH 재공과 아침 재공 기준일 규칙을 등록해줘.
아침 재공, BOH 재공, BOH, 07시 기준 재공, 7시 기준 재공은 하루 시작 시점의 재공을 뜻해.
재공 이력 테이블의 DATE는 해당 일자의 EOH, 즉 끝나는 시점 재공이야.
그래서 특정 일자의 BOH 재공은 그 전일 DATE의 wip 이력 데이터를 조회해야 해.
예를 들어 6/20 아침 재공, 6/20 BOH 재공, 6/20 07시 기준 재공은 wip 이력 데이터에 DATE=6/19를 넣어 조회한 결과가 6/20 BOH 값이야.
오늘 또는 금일 아침 재공, 오늘 BOH, 금일 07시 기준 재공은 wip_today를 사용하지 않고 wip 이력 데이터에 어제 DATE를 넣어 조회해.
반대로 현재 재공, 지금 재공, 금일 현재 재공은 wip_today 계열 데이터를 사용해.
특정 일자의 EOH 재공, 마감 재공, 종료 재공을 물으면 wip 이력 데이터에 해당 일자 DATE를 그대로 넣어 조회해.
분석 계획에서는 사용자가 요청한 기준일과 실제 조회 DATE를 구분해. 결과에는 BOH 기준일을 표시하고, retrieval job의 DATE 파라미터에는 기준일의 전일을 넣어.
```
<!-- single_boh_wip_temporal_rule:end -->

<!-- single_metric_terms:start -->
```text
계산 로직을 등록해줘.
Wafer기준 실적, Wafer기반 실적, Wafer Out 수량은 production 계열 데이터에서 PRODUCTION / NETDIE_300_CNT로 계산해.
NETDIE_300_CNT 값이 0보다 큰 경우에만 WAFER_OUT_QTY를 계산하고, NETDIE_300_CNT가 0 또는 NULL이라 나눌 수 없는 경우에는 해당 PRODUCTION 값을 FAIL_UNIT_QTY 컬럼으로 옆에 보여줘.
Wafer기준 실적은 먼저 row 단위로 WAFER_OUT_QTY와 FAIL_UNIT_QTY를 만든 뒤, 사용자가 요청한 grain 또는 전체 기준으로 합산해.
생산달성률은 production 계열 데이터의 sum(PRODUCTION) / target 계열 데이터의 sum(OUT_PLAN) * 100으로 계산해.
달성률을 평균내지 말고, 먼저 각 수량을 집계한 뒤 비율을 계산해.
```
<!-- single_metric_terms:end -->

<!-- single_join_rule:start -->
```text
제품 기준 join rule을 등록해줘.
production, wip, target, equipment 데이터를 제품 기준으로 결합할 때는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO를 기본 제품 키로 사용해.
dataset마다 PKG1, PKG2, PKG_TYP1, PKG_TYP2, DENSITY처럼 물리 컬럼명이 달라도 table catalog의 mapping을 통해 PKG_TYPE1, PKG_TYPE2, DEN 같은 표준 컬럼으로 맞춘 뒤 pandas에서 조인해.
사용자가 제품별이라고 하면 제품 키 기준으로 group by 해.
사용자가 DEVICE별이라고 하면 DEVICE 기준으로 group by 해.
사용자가 전체, 총, 합계를 물으면 별도 group by 없이 합계를 보여줘.

사용자가 원본, RAW DATA, 세부 데이터, 전체 데이터를 물으면 그룹화하지 않고 detail rows를 보여줘.
```
<!-- single_join_rule:end -->

<!-- single_recipe_sbm_without_sg:start -->
```text
SBM공정 WIP 있는 제품 중 S/G공정 WIP 없는 제품을 찾는 분석 패턴을 등록해줘.
이 블록은 analysis_recipes만 등록하고, SBM이나 S/G 공정 그룹은 새로 만들지 마.
SBM공정 WIP 있는 제품 중 S/G공정 WIP 없는 제품을 물으면 wip 계열 데이터를 두 source로 나누어 조회해. 첫 번째 source는 OPER_NAME=SBM, 두 번째 source는 OPER_NAME=S/G 조건을 적용해. 제품 키 기준으로 SBM을 left join 기준으로 두고 S/G WIP가 없거나 0인 제품만 남겨.
```
<!-- single_recipe_sbm_without_sg:end -->

<!-- single_recipe_sg_wip_100k:start -->
```text
S/G공정에서 재공이 100K 이상인 제품을 찾는 분석 패턴을 등록해줘.
이 블록은 analysis_recipes만 등록하고, S/G 공정 그룹이나 WIP 수량 용어는 새로 만들지 마.
S/G공정에서 재공이 100K 이상인 제품을 물으면 OPER_NAME=S/G 조건과 WIP >= 100000 조건을 같이 적용하고 제품 기준으로 결과를 보여줘.
```
<!-- single_recipe_sg_wip_100k:end -->

<!-- single_recipe_yesterday_no_input_today_input:start -->
```text
전일 투입 안 된 제품 중 금일 투입된 제품을 찾는 분석 패턴을 등록해줘.
이 블록은 analysis_recipes만 등록해줘.
전일 투입 안 된 제품 중 금일 투입된 제품을 물으면 전일 production 계열 INPUT source와 금일 production_today 계열 INPUT source를 따로 조회해. 전일 INPUT_QTY가 없거나 0이고 금일 INPUT_QTY가 0보다 큰 제품만 보여줘.
```
<!-- single_recipe_yesterday_no_input_today_input:end -->

<!-- single_recipe_input_lt_out:start -->
```text
특정일 INPUT된 자재의 L/T OUT을 찾는 분석 패턴을 등록해줘.
INPUT된 자재 L/T OUT, INPUT된 자재의 L/T OUT, INPUT 자재 L/T OUT은 같은 분석 패턴을 뜻해.
이 블록은 analysis_recipes만 등록하고, INPUT이나 L/T 공정 그룹은 새로 만들지 마.
특정일 INPUT된 자재의 L/T OUT을 물으면 같은 날짜의 INPUT 제품 키를 먼저 찾고, 그 제품 키를 기준으로 L/T1, L/T2 공정의 OUTPUT 실적을 조회해.
```
<!-- single_recipe_input_lt_out:end -->

<!-- single_recipe_input_vs_process:start -->
```text
INPUT 공정 실적 대비 특정 공정 실적을 제품별로 비교하는 분석 패턴을 등록해줘.
이 블록은 analysis_recipes만 등록하고, INPUT이나 비교 공정의 process_groups/quantity_terms는 새로 만들지 마.
INPUT 공정 실적 대비 특정 공정 실적을 제품별로 물으면 INPUT source와 비교 공정 source를 분리해서 조회하고, INPUT source에 비교 공정 필터를 섞지 않아.
```
<!-- single_recipe_input_vs_process:end -->

<!-- single_recipe_da_wb_production_wip:start -->
```text
DA공정 생산량/재공과 WB공정 생산량/재공을 각각 보여주는 분석 패턴을 등록해줘.
section은 analysis_recipes이고 key는 da_wb_process_analysis야.
표시 이름은 DA/WB 공정별 생산량/재공 분석이야.
유의어는 DA공정 생산량/재공, WB공정 생산량/재공, DA WB 생산량 재공이야.
required_question_cues는 DA, WB, 생산량, 재공이야. DA와 WB를 둘 다 명시한 질문에서만 이 recipe를 사용해.
forbidden_question_cues는 제품별, 제품, 상위, top, TOP, rank야.
이 블록은 analysis_recipes만 등록하고, DA/WB 공정 그룹이나 production/wip 수량 용어는 새로 만들지 마.
DA공정 생산량/재공과 WB공정 생산량/재공을 각각 보여달라고 하면 DA production, DA wip, WB production, WB wip를 각각 독립 source 또는 독립 step으로 집계하고, 최종 결과는 OPER_GROUP별로 PRODUCTION과 WIP를 모두 포함해.
```
<!-- single_recipe_da_wb_production_wip:end -->

<!-- single_recipe_product_production_wip_join:start -->
```text
제품별 생산량과 재공을 같이 보여주는 분석 recipe를 등록해줘.
section은 analysis_recipes이고 key는 product_production_wip_join야.
표시 이름은 제품별 생산량 재공 결합이고, 유의어는 제품별 생산량 재공, 제품별 생산량과 재공, 재공과 생산량, 생산량과 재공, production wip product join이야.
default_analysis_kind는 aggregate_join이고 intent_type은 multi_source_analysis야.
question_cues는 생산량, 재공, 제품별, 공정별, 세부 공정별이야.
사용자가 "오늘 DA공정에서 재공과 생산량을 제품별로 알려줘" 또는 "어제 512G G-777 제품의 생산량과 재공을 세부 공정별로 알려줘"처럼 production 계열 수량과 wip 계열 수량을 같이 묻고 같은 제품/공정 기준으로 붙여야 하면 이 recipe를 사용해.
required_dataset_families는 production, wip야.
source_aliases_by_family는 production=production_data, wip=wip_data로 저장해.
grain_policy는 question_or_product_grain이고, replace_datasets, replace_retrieval_jobs, override_step_plan은 true로 저장해.
override_analysis_kinds는 rank_top_n, aggregate_wip_total, aggregate_join, generic_aggregate_recipe야.
required_columns_by_family는 production에 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, PRODUCTION을 넣고, wip에 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, WIP를 넣어.
step_plan_template은 generic step만 사용해.
첫 번째 step은 step_id=aggregate_production_by_requested_grain, operation=aggregate_by_group, source_family=production, group_by는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, metric=PRODUCTION, aggregation=sum, output_columns는 group_by 컬럼과 PRODUCTION이야.
두 번째 step은 step_id=aggregate_wip_by_requested_grain, operation=aggregate_by_group, source_family=wip, group_by는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, metric=WIP, aggregation=sum, output_columns는 group_by 컬럼과 WIP야.
세 번째 step은 step_id=join_production_and_wip, operation=left_join, left_step_id=aggregate_production_by_requested_grain, right_step_id=aggregate_wip_by_requested_grain, join_keys는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME이고, output_columns는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, PRODUCTION, WIP야.
```
<!-- single_recipe_product_production_wip_join:end -->

<!-- single_recipe_rank_wip_then_join_production:start -->
```text
재공 상위 제품을 먼저 찾고 해당 제품의 생산량을 붙이는 분석 패턴을 등록해줘.
section은 analysis_recipes이고 key는 rank_wip_then_join_production야.
표시 이름은 재공 상위 제품 생산량 결합이고, 유의어는 재공 상위 제품 생산량, 재공 top 제품 실적, WIP top production이야.
default_analysis_kind는 rank_wip_then_join_production이고 intent_type은 multi_step_analysis야.
question_cues는 재공, 상위, top, 생산량, 실적이야.
사용자가 "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘"처럼 공정 그룹별 WIP rank 이후 production을 이어서 물으면 이 recipe를 사용해.
required_dataset_families는 wip, production이고 source_aliases_by_family는 wip=wip_data, production=production_data야.
grain_policy는 question_or_product_grain이고 top_n_policy는 question_or_default이며 defaults.top_n은 3이야.
replace_datasets, replace_retrieval_jobs, override_step_plan은 true로 저장해.
override_analysis_kinds는 rank_top_n, aggregate_join, generic_aggregate_recipe야.
required_columns_by_family는 wip에 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, WIP를 넣고, production에 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, OPER_NAME, PRODUCTION을 넣어.
step_plan_template은 generic step을 사용해.
공정 그룹별로 각각 rank해야 하는 질문을 위해 rank_group_output_column은 OPER_GROUP이고 rank_groups는 DA=OPER_NAME in D/A1,D/A2,D/A3,D/A4,D/A5,D/A6 그리고 WB=OPER_NAME in W/B1,W/B2,W/B3,W/B4,W/B5,W/B6로 저장해.
첫 번째 step은 step_id=rank_wip_products_per_process, operation=rank_top_n, source_family=wip, rank_group_output_column=OPER_GROUP, rank_groups는 위 DA/WB 정의를 사용하고, group_by는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, metric=WIP, top_n=$top_n, rank_order=desc, output_columns는 OPER_GROUP, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, WIP야.
두 번째 step은 step_id=aggregate_production_for_ranked_products, operation=aggregate_by_group, source_family=production, filter_from_step=rank_wip_products_per_process, rank_group_output_column=OPER_GROUP, rank_groups는 위 DA/WB 정의를 사용하고, join_keys는 OPER_GROUP, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, group_by는 OPER_GROUP, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, metric=PRODUCTION, aggregation=sum, output_columns는 OPER_GROUP, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, PRODUCTION이야.
세 번째 step은 step_id=join_ranked_wip_and_production, operation=left_join, left_step_id=rank_wip_products_per_process, right_step_id=aggregate_production_for_ranked_products, join_keys는 OPER_GROUP, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO이고, output_columns는 OPER_GROUP, TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, WIP, PRODUCTION이야.
```
<!-- single_recipe_rank_wip_then_join_production:end -->

<!-- single_recipe_lot_quantity_summary:start -->
```text
LOT 수량 요약 분석 패턴을 등록해줘.
section은 analysis_recipes이고 key는 lot_quantity_summary야.
표시 이름은 LOT 수량 요약이고, 유의어는 lot 수량, lot은 몇개, wafer 몇개, die 수량이야.
default_analysis_kind는 lot_quantity_summary이고 intent_type은 single_retrieval_analysis야.
question_cues는 lot, LOT, wafer, die, 수량, 몇개야.
사용자가 "DA공정에서 재공 lot은 몇개고 wafer와 die 수량은 몇개야?"처럼 공정 scope와 Lot/Wafer/Die 수량을 함께 물으면 lot_status 계열 데이터를 사용해.
required_dataset_families는 lot이고 source_aliases_by_family는 lot=lot_data야.
grain_policy는 aggregate_total이고 replace_datasets, replace_retrieval_jobs, override_step_plan은 true로 저장해.
override_analysis_kinds는 aggregate_join, aggregate, aggregate_wip_total이야.
required_columns_by_family는 lot에 LOT_ID, OPER_NAME, LOT_STAT_CD, WF_QTY, SUB_PROD_QTY, IN_TAT, CUM_TAT를 넣어.
step_plan_template은 하나의 generic aggregate_by_group step으로 저장해.
step_id는 summarize_lot_quantities, operation은 aggregate_by_group, source_family는 lot이야.
공정별이라고 물으면 group_by는 표준 컬럼 OPER_NAME을 사용하고, 전체 수량이면 group_by는 비워둬.
metrics는 LOT_ID nunique 결과 LOT_COUNT, WF_QTY sum 결과 WF_QTY, SUB_PROD_QTY sum 결과 DIE_QTY야.
output_columns는 LOT_COUNT, WF_QTY, DIE_QTY이고 공정별이면 OPER_NAME을 앞에 포함해.
```
<!-- single_recipe_lot_quantity_summary:end -->

<!-- single_recipe_top_wip_process_hold_lot_in_tat:start -->
```text
재공 상위 공정의 Hold LOT와 IN_TAT를 같이 보는 분석 패턴을 등록해줘.
section은 analysis_recipes이고 key는 top_wip_process_hold_lot_in_tat야.
표시 이름은 재공 상위 공정 HOLD LOT 평균 In TAT이고, 유의어는 hold LOT, in tat, 재공이 많은 세부공정이야.
default_analysis_kind는 top_wip_process_hold_lot_in_tat이고 intent_type은 multi_step_analysis야.
question_cues는 재공, 상위, top, hold, HOLD, IN_TAT, tat, TAT야.
사용자가 "현재 재공이 많은 세부공정 top 3을 찾고 해당 공정의 hold LOT 수와 평균 IN_TAT도 보여줘"처럼 재공 상위 공정과 Hold/IN_TAT 정보를 같이 물으면 이 recipe를 사용해.
required_question_cues는 hold/HOLD와 tat/TAT야.
required_dataset_families는 wip, lot이고 source_aliases_by_family는 wip=wip_data, lot=lot_status_data야.
grain_policy는 recipe_step_grain이고 top_n_policy는 question_or_default이며 defaults.top_n은 3이야.
replace_datasets, replace_retrieval_jobs, override_step_plan은 true로 저장해.
override_analysis_kinds는 lot_count_by_process, aggregate, aggregate_wip_total이야.
blocked_filter_fields는 LOT_HOLD_STAT_CD야. HOLD 조건은 조회 필터가 아니라 lot metrics step의 filters로 처리해.
output_columns는 OPER_SHORT_DESC, WIP, HOLD_LOT_COUNT, AVG_IN_TAT야.
required_columns_by_family는 wip에 OPER_NAME, WIP를 넣고, lot에 OPER_SHORT_DESC, LOT_ID, LOT_HOLD_STAT_CD, IN_TAT를 넣어.
step_plan_template은 generic step만 사용해.
첫 번째 step은 step_id=rank_top_wip_process, operation=rank_top_n, source_family=wip, group_by=OPER_NAME, metric=WIP, top_n=$top_n, rank_order=desc, output_columns=OPER_NAME,WIP야.
두 번째 step은 step_id=lot_metrics_by_process, operation=aggregate_by_group, source_family=lot, filter_from_step=rank_top_wip_process, join_keys는 left=OPER_SHORT_DESC right=OPER_NAME, group_by=OPER_SHORT_DESC야.
두 번째 step filters는 LOT_HOLD_STAT_CD in HOLD, ONHOLD야.
두 번째 step metrics는 LOT_ID nunique 결과 HOLD_LOT_COUNT, IN_TAT mean 결과 AVG_IN_TAT야.
세 번째 step은 step_id=join_wip_and_lot_metrics, operation=left_join, left_step_id=rank_top_wip_process, right_step_id=lot_metrics_by_process, join_keys는 left=OPER_NAME right=OPER_SHORT_DESC, output_columns는 OPER_SHORT_DESC, WIP, HOLD_LOT_COUNT, AVG_IN_TAT야.
```
<!-- single_recipe_top_wip_process_hold_lot_in_tat:end -->

<!-- single_recipe_top_wip_product_oldest_lot:start -->
```text
재공이 가장 많은 제품의 IN_TAT가 가장 오래된 LOT를 찾는 분석 패턴을 등록해줘.
section은 analysis_recipes이고 key는 top_wip_product_oldest_lot야.
표시 이름은 재공 최다 제품 기준 최장 In TAT LOT이고, 유의어는 재공이 가장 많은 제품, IN TAT가 가장 오래된 LOT야.
default_analysis_kind는 top_wip_product_oldest_lot이고 intent_type은 multi_step_analysis야.
question_cues는 재공, 가장 많은, IN_TAT, 오래된, LOT야.
사용자가 "재공이 가장 많은 제품을 찾고 그 제품의 IN_TAT가 가장 오래된 LOT를 보여줘"처럼 제품 rank 이후 LOT detail을 이어서 물으면 이 recipe를 사용해.
required_dataset_families는 wip, lot이고 source_aliases_by_family는 wip=wip_data, lot=lot_data야.
grain_policy는 question_or_product_grain이고 replace_datasets, replace_retrieval_jobs, override_step_plan은 true로 저장해.
output_columns는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, WIP, LOT_ID, IN_TAT야.
required_columns_by_family는 wip에 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, WIP를 넣고, lot에 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, LOT_ID, IN_TAT를 넣어.
step_plan_template은 generic step만 사용해.
첫 번째 step은 step_id=rank_top_wip_product, operation=rank_top_n, source_family=wip, group_by=TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO, metric=WIP, top_n=1, rank_order=desc야.
두 번째 step은 step_id=find_oldest_lot_for_top_product, operation=rank_top_n, source_family=lot, filter_from_step=rank_top_wip_product, join_keys=TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO, group_by=TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO,LOT_ID, metric=IN_TAT, top_n=1, rank_order=desc, output_columns=TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO,LOT_ID,IN_TAT야.
세 번째 step은 step_id=join_top_product_and_oldest_lot, operation=left_join, left_step_id=rank_top_wip_product, right_step_id=find_oldest_lot_for_top_product, join_keys=TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO, output_columns=TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO,WIP,LOT_ID,IN_TAT야.
```
<!-- single_recipe_top_wip_product_oldest_lot:end -->

<!-- single_recipe_followup_equipment_for_previous_products:start -->
```text
이전 결과 제품 기준 장비 조회 분석 패턴을 등록해줘.
section은 analysis_recipes이고 key는 equipment_for_previous_products야.
표시 이름은 이전 제품 기준 장비 조회이고, 유의어는 이전 제품 장비, 해당 제품 장비, 설비 현황, 장비 현황이야.
default_analysis_kind는 equipment_for_previous_products이고 intent_type은 followup_transform이야.
question_cues는 이 제품, 그 제품, 해당 제품, 장비, 설비, 현황이야.
사용자가 이전 답변에서 나온 제품들에 대해 "이 제품들의 장비 현황 보여줘"처럼 후속 질문을 하면 previous result의 제품 키를 사용해 equipment_status 계열 데이터를 조회해.
required_dataset_families는 equipment이고 source_aliases_by_family는 equipment=equipment_data야.
grain_policy는 question_or_product_grain이고 result_mode는 detail_rows야.
replace_datasets, replace_retrieval_jobs, override_step_plan은 true로 저장해.
required_columns_by_family는 equipment에 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, EQPID, EQP_MODEL, PRESS_CNT, LOT_ID, RECIPE_ID를 넣어.
step_plan_template은 step_id=filter_equipment_for_previous_products, operation=detail_rows, source_family=equipment, columns=TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO,EQPID,EQP_MODEL,PRESS_CNT,LOT_ID,RECIPE_ID로 저장해.
이 recipe는 이전 결과의 제품 key를 사용하는 것이 핵심이며, 코드 fallback이 아니라 metadata recipe와 PRODUCT_GRAIN from_state 필터를 통해 동작해야 해.
```
<!-- single_recipe_followup_equipment_for_previous_products:end -->

<!-- single_recipe_followup_equipment_count_for_previous_products:start -->
```text
이전 결과 제품 기준 장비 대수 집계 분석 패턴을 등록해줘.
section은 analysis_recipes이고 key는 equipment_count_for_previous_products야.
표시 이름은 이전 제품 기준 장비 대수이고, 유의어는 이전 제품 장비 대수, 해당 제품 설비 수, 장비 몇 대, 설비 몇 대야.
default_analysis_kind는 equipment_count_for_previous_products이고 intent_type은 followup_transform이야.
question_cues는 이 제품, 그 제품, 해당 제품, 장비 대수, 설비 대수, 몇 대, 몇대야.
사용자가 이전 답변에서 나온 제품들에 대해 "이 제품들의 장비는 몇 대야?"처럼 후속 질문을 하면 previous result의 제품 키를 사용해 equipment_status 계열 데이터를 조회해.
required_dataset_families는 equipment이고 source_aliases_by_family는 equipment=equipment_data야.
grain_policy는 question_or_product_grain이고 replace_datasets, replace_retrieval_jobs, override_step_plan은 true로 저장해.
required_columns_by_family는 equipment에 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, EQPID를 넣어.
output_columns는 TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO, EQP_COUNT야.
step_plan_template은 하나의 generic unique_count_by_group step으로 저장해.
step_id는 count_equipment_for_previous_products, operation은 unique_count_by_group, source_family는 equipment, group_by는 TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO, count_column은 EQPID, output_columns는 TECH,DEN,MODE,PKG_TYPE1,PKG_TYPE2,LEAD,MCP_NO,EQP_COUNT야.
이 recipe는 이전 결과의 제품 key를 사용하는 것이 핵심이며, 코드 fallback이 아니라 metadata recipe와 PRODUCT_GRAIN from_state 필터를 통해 동작해야 해.
```
<!-- single_recipe_followup_equipment_count_for_previous_products:end -->
