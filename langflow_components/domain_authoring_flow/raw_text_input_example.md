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
D/S 또는 DS는 D/S1을 의미해.
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

[제품 속성 매칭 규칙]
제품 속성 일부 조합으로 제품을 찾는 pandas 코드 생성 규칙을 등록해줘.
이 규칙은 사용자가 제품, PRODUCT, 자재, DEVICE 같은 표현으로 일부 제품 속성 조합을 말할 때 적용해줘.
POP, MOBILE, HBM, AUTO향처럼 이름이 등록된 제품 조건은 먼저 product_terms에서 확인하고, 그 외에 작업자가 "512M A-134 제품", "LPDDR5 1G 제품", "TSV 2048G 제품"처럼 일부 속성만 말하면 별도 product master나 lookup dataset을 조회하지 말고 이미 조회된 runtime source DataFrame 안에서 값을 찾아서 필터링해줘.
속성 순서는 뒤죽박죽일 수 있고 일부 속성만 입력될 수 있어.
매칭에 사용할 표준 컬럼은 TECH, DEN, MODE, ORG, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO야.
DEVICE_DESC는 일반 제품 속성 매칭 규칙에는 사용하지 말고, 사용자가 DEVICE_DESC를 명시해서 물어본 경우에만 별도 명시적 필터로 처리해.
실제 source 컬럼이 DENSITY, DEN_TYP, PKG1, PKG_TYP1, PKG2, PKG_TYP2, MCP_SALE_CD, MCP_SALES_NO, MCPSALENO처럼 다르더라도 metadata mapping으로 표준 컬럼명에 맞춰진 뒤 pandas에서는 표준 컬럼명을 사용해.
이미 조회된 source DataFrame에서 위 속성 컬럼별 distinct 값을 valid_values로 만들고, 사용자 질문을 공백, 쉼표, 슬래시 기준으로 토큰화한 뒤 각 토큰을 대문자 문자열로 바꿔 valid_values와 비교해.
일치하는 토큰이 있으면 해당 컬럼/값 조합을 matched_filters에 저장하고, matched_filters를 pandas boolean filter로 적용해.
MCP_NO는 완전일치뿐 아니라 접두 매칭도 허용해. 예를 들어 사용자 토큰이 A-587처럼 알파벳-숫자 3자리 형태로 시작하는 제품 코드 접두어이면, MCP_NO가 A-587AA, A-587K1, A-587 같은 값으로 시작하는 row를 모두 매칭해.
MCP_NO 접두 매칭은 MCP_NO 컬럼에만 적용하고, 다른 속성 컬럼에는 완전일치를 기본으로 사용해.
매칭된 속성 컬럼은 필터로만 사용해. 사용자가 해당 속성별 집계를 요청하지 않았다면 group_by에 넣지 마.
모르는 토큰은 경고만 남기고 무리하게 필터를 만들지 말아줘. 한 토큰이 여러 컬럼에 동시에 매칭되어 애매하면 임의로 강한 필터를 만들지 말고 불확실한 상태로 남겨줘.
pandas 처리 예시는 아래와 같아.
tokens = 사용자 질문을 공백/쉼표/슬래시 기준으로 나누고 대문자 문자열로 변환
attribute_columns = ["TECH", "DEN", "MODE", "ORG", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
valid_values = {column: set(source_df[column].dropna().astype(str).str.upper().unique()) for column in attribute_columns if column in source_df.columns}
matched_filters = {}
MCP_NO 접두어 패턴 예시는 알파벳 1자리, 하이픈, 숫자 3자리로 시작하는 r"^[A-Z]-\d{3}" 형태야.
for token in tokens:
    matched = False
    if "MCP_NO" in valid_values and token에서 r"^[A-Z]-\d{3}" 형태의 접두어를 찾을 수 있으면:
        mcp_prefix = 해당 접두어
        if any(value.startswith(mcp_prefix) for value in valid_values["MCP_NO"]):
            matched_filters["MCP_NO"] = {"op": "starts_with", "value": mcp_prefix}
            matched = True
    if not matched:
        for column, values in valid_values.items():
            if token in values:
                matched_filters[column] = {"op": "eq", "value": token}
                break
for column, rule in matched_filters.items():
    series = source_df[column].astype(str).str.upper()
    if rule["op"] == "starts_with":
        source_df = source_df[series.str.startswith(rule["value"])].copy()
    else:
        source_df = source_df[series.eq(rule["value"])].copy()

[수량 용어]
재공, WIP, 공정 물량은 wip 계열 데이터의 WIP 컬럼 합계를 의미해.
생산량, 생산 실적, output quantity는 production 계열 데이터의 PRODUCTION 컬럼 합계를 의미해.
투입량은 PKG INPUT 공정의 생산 실적이며, OPER_DESC 값이 INPUT인 production 계열 데이터의 PRODUCTION 합계를 의미해.
스케쥴, 스케줄, 생산계획, SCHD, 투입계획, 일별 투입계획은 모두 생산계획 데이터 또는 target 계열 데이터를 의미해.

[Metric]
생산달성률은 production 데이터의 sum(PRODUCTION) / target 데이터의 sum(OUT계획) * 100 으로 계산해.
행별 달성률을 평균내지 말고, 먼저 각 수량을 집계한 뒤 계산해줘.
동적TAT 또는 dynamic TAT는 sum(WIP) / sum(PRODUCTION)으로 계산하며, 먼저 WIP와 PRODUCTION을 집계한 뒤 계산해줘.

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

<!-- single_product_attribute_resolver:start -->
```text
제품 속성 일부 조합으로 제품을 찾는 pandas 코드 생성 규칙을 등록해줘.
이 규칙은 사용자가 제품, PRODUCT, 자재, DEVICE 같은 표현으로 일부 제품 속성 조합을 말할 때 적용해줘.

POP, MOBILE, HBM, AUTO향처럼 이름이 등록된 제품 조건은 먼저 product_terms에서 확인해.
그 외에 사용자가 "512M A-134 제품", "LPDDR5 1G 제품", "TSV 2048G 제품"처럼 일부 속성만 말하면 별도 product master나 lookup dataset을 조회하지 말고 이미 조회된 source DataFrame 안에서 값을 찾아서 필터링해줘.
속성 순서는 고정되어 있지 않고, 일부 속성만 입력될 수 있어.

매칭 대상 표준 컬럼은 TECH, DEN, MODE, ORG, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO야.
DEVICE_DESC는 일반 제품 속성 매칭 규칙에는 사용하지 말고, 사용자가 DEVICE_DESC를 명시해서 물어본 경우에만 별도 명시적 필터로 처리해.
source마다 실제 컬럼명이 DENSITY, PKG1, PKG2, MCP_SALE_CD, MCPSALENO처럼 달라도 pandas 코드에서는 metadata mapping 이후의 표준 컬럼명을 사용해.
이미 조회된 source DataFrame에서 컬럼별 distinct 값을 valid_values로 만든 다음, 질문 토큰이 어느 컬럼의 유효값에 포함되는지 찾는 방식으로 동작해야 해.
MCP_NO는 완전일치뿐 아니라 접두 매칭도 허용해. 예를 들어 A-587이라고 물으면 MCP_NO가 A-587AA, A-587K1, A-587처럼 A-587로 시작하는 값들을 모두 매칭해. 이 접두 매칭은 MCP_NO 컬럼에만 적용해.

pandas 처리 방식은 아래 예시를 참고해.
question tokens = 사용자 질문을 공백, 쉼표, 슬래시 기준으로 나누고 대문자 문자열로 변환
attribute_columns = ["TECH", "DEN", "MODE", "ORG", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
valid_values = {column: set(source_df[column].dropna().astype(str).str.upper().unique()) for column in attribute_columns if column in source_df.columns}
matched_filters = {}
MCP_NO 접두어 패턴 예시는 알파벳 1자리, 하이픈, 숫자 3자리로 시작하는 r"^[A-Z]-\d{3}" 형태야.
for token in question tokens:
    matched = False
    if token에서 r"^[A-Z]-\d{3}" 형태의 MCP_NO 접두어를 찾을 수 있고 "MCP_NO" in valid_values:
        if any(value.startswith(mcp_prefix) for value in valid_values["MCP_NO"]):
            matched_filters["MCP_NO"] = {"op": "starts_with", "value": mcp_prefix}
            matched = True
    if not matched:
        for column, values in valid_values.items():
            if token in values:
                matched_filters[column] = {"op": "eq", "value": token}
                break
for column, rule in matched_filters.items():
    series = source_df[column].astype(str).str.upper()
    if rule["op"] == "starts_with":
        source_df = source_df[series.str.startswith(rule["value"])].copy()
    else:
        source_df = source_df[series.eq(rule["value"])].copy()

매칭된 속성 컬럼은 필터로만 사용하고, 사용자가 속성별 집계를 요청하지 않았다면 group_by에는 넣지 마.
모르는 토큰이나 애매한 토큰은 임의로 강한 필터를 만들지 말고 경고 또는 보류로 처리해.
```
<!-- single_product_attribute_resolver:end -->
