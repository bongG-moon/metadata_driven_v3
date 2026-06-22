# Domain Authoring Raw Text Examples

아래 예시는 작업자가 자연어로 입력할 수 있는 최소 샘플입니다.
필요한 항목만 복사해서 등록하고, 같은 의미의 항목이 이미 있으면 기존 항목을 업데이트하도록 입력하면 됩니다.

<!-- bulk_domain:start -->
```text
[공정 그룹]
DA 또는 D/A는 D/A1, D/A2, D/A3, D/A4, D/A5, D/A6를 모두 포함하는 공정 그룹이야.
사용자가 "DA공정", "다이 어태치", "die attach"라고 말하면 같은 의미로 해석해줘.

[제품 조건]
HBM, 3DS, TSV 제품은 TSV_DIE_TYP 값이 존재하고 빈 값이 아닌 제품이야.
FAMILY나 PKG_TYPE1에 HBM이라는 글자가 있다는 이유만으로 HBM 제품으로 판단하지 말아줘.

[수량 용어]
재공, WIP, 공정 물량은 wip 계열 데이터의 WIP 컬럼 합계를 의미해.
생산량, 생산 실적, output quantity는 production 계열 데이터의 PRODUCTION 컬럼 합계를 의미해.

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
