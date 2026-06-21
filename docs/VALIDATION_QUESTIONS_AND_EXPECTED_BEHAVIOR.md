# Validation Questions And Expected Behavior

이 문서는 정답 숫자만 맞추는 용도가 아니다. 새 agent가 올바른 dataset, filter scope, group_by, metric 계산식, result schema, applied condition을 남기는지 검증하기 위한 기준이다.

## Required Regression Set

현재 `metadata/regression_questions.json`에는 23개 회귀 질문이 들어 있다. 아래 6개는 최초 smoke set이고, 그 뒤 항목들은 persistence/scope/metric/recipe 기반 순차 분석까지 넓힌 검증 set이다.

### 1. Multi-Step WIP Rank + Production Join

질문:

`오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘`

기대 동작:

- `intent_type`: `multi_step_analysis`
- 사용 dataset: `wip_today`, `production_today`
- step 순서: `rank_wip_by_process_group -> aggregate_production_for_ranked_products -> join_rank_and_production`
- DA/WB를 전역 top 3로 섞지 않고 `RANK_GROUP`별 top 3로 계산한다.
- product grain: `TECH`, `DEN`, `MODE`, `PKG_TYPE1`, `PKG_TYPE2`, `LEAD`, `MCP_NO`
- 최종 컬럼: `RANK_GROUP`, `WIP_RANK`, product grain, `WIP`, `PRODUCTION`

### 2. HOLD History

질문:

`T1234567GEN1 LOT의 HOLD이력 알려줘`

기대 동작:

- 사용 dataset: `hold_history`
- required param: `LOT_ID=T1234567GEN1`
- 결과 모드: detail rows
- 최종 컬럼: `LOT_ID`, `HOLD_TM`, `HOLD_CD`, `HOLD_DESC`, `HOLD_USER_ID`, `EVENT_CD`

### 3. Current Hold Lot List

질문:

`현재 hold된 lot list 알려줘`

기대 동작:

- 사용 dataset: `lot_status`
- filter: `LOT_HOLD_STAT_CD in HOLD/OnHold`
- detail list 요청이므로 자동 집계하지 않는다.
- 최종 컬럼: `LOT_ID`, `OPER_SHORT_DESC`, `LOT_STAT_CD`, `LOT_HOLD_STAT_CD`

### 4. DA WIP Top Product

질문:

`현재 da에서 재공이 가장 많은 제품 알려줘`

기대 동작:

- 사용 dataset: `wip_today`
- DA group은 `D/A1~D/A6`로 확장한다.
- product grain 기준으로 `WIP`를 합산하고 rank 1을 반환한다.
- 다음 후속 질문에서 이 product grain을 state.current_data로 재사용할 수 있어야 한다.

### 5. Follow-Up Equipment For This Product

질문:

`이 제품에 할당된 장비 현황 알려줘`

기대 동작:

- 이전 질문의 `state.current_data.product_key_values`를 우선 사용하고, 없을 때 preview rows에서 product grain을 읽는다.
- 사용 dataset: `equipment_status`
- `state_product_keys`가 비어 있으면 실패 또는 확인 요청을 해야 한다.
- 최종 컬럼: `EQPID`, `EQP_MODEL`, `PRESS_CNT`, product grain, `LOT_ID`, `RECIPE_ID`

### 6. LPDDR5 W/B Production And WIP

질문:

`현재 MODE값이 LPDDR5인 제품의 W/B공정에서 생산량과 재공 수량 알려줘`

기대 동작:

- 사용 dataset: `production_today`, `wip_today`
- filter: `MODE=LPDDR5`, `OPER_NAME in W/B1~W/B6`
- 두 source에 같은 business filter를 적용한다.
- product grain 기준으로 `PRODUCTION`, `WIP`를 각각 합산한 뒤 join한다.

### 7. DA WIP + Production + Target + Achievement Rate

질문:

`오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘`

기대 동작:

- 사용 dataset: `production_today`, `wip_today`, `target`
- DA group은 `D/A1~D/A6`로 확장한다.
- `PRODUCTION`, `WIP`, `OUT_PLAN`을 product grain 기준으로 aggregate-first 계산한다.
- `ACHIEVEMENT_RATE = sum(PRODUCTION) / sum(OUT_PLAN) * 100`

### 8. Low Output Against Target

질문:

`오늘 D/A1공정에서 목표값 대비해서 생산량이 저조한 제품을 알려줘`

기대 동작:

- 사용 dataset: `production_today`, `target`
- `D/A1`은 DA group 전체가 아니라 단일 공정으로 유지한다.
- 결과 컬럼에 `TARGET_QTY`, `ACHIEVEMENT_RATE`, `BALANCE`, `LOW_OUTPUT_FLAG`가 있어야 한다.
- 달성률은 row 평균이 아니라 product grain별 aggregate-first로 계산한다.

### 9. Low Output Against Input Plan

질문:

`오늘 INPUT계획대비 D/A공정에서 생산량이 저조한 제품을 알려줘`

기대 동작:

- `INPUT계획`은 `target.INPUT_PLAN`으로 해석한다.
- 비교 actual은 `production_today`의 DA 공정 생산량이다.
- `target`과 `production_today`의 날짜/조건 scope가 분리되어야 한다.

### 10. Waiting Lot Count By Process

질문:

`현재 작업대기 Lot 수량을 공정별로 알려줘`

기대 동작:

- 사용 dataset: `lot_status`
- filter: `LOT_STAT_CD=WAITING`
- Lot 수량은 `LOT_ID.nunique()`로 계산한다.
- `SUB_PROD_QTY`, `WF_QTY` 합계를 lot count로 쓰면 실패다.

### 11. DA Lot/Wafer/Die Summary

질문:

`현재 DA공정에서 재공 lot이 몇개인지, wafer가 몇개인지, die수량은 몇개인지 알려줘`

기대 동작:

- 사용 dataset: `lot_status`
- DA group은 `D/A1~D/A6`로 확장한다.
- `LOT_COUNT = LOT_ID.nunique()`
- `WF_QTY`와 `DIE_QTY`는 수량 합산으로 계산한다.

### 12. WIP Quantity Must Use WIP Dataset

질문:

`현재 DA공정 재공 수량 알려줘`

기대 동작:

- 사용 dataset: `wip_today`
- `lot_status`로 라우팅하지 않는다.
- DA 공정 filter만 적용하고 `WIP`를 합산한다.

### 13. Scope Reset After Follow-Up State

질문 흐름:

1. `현재 da에서 재공이 가장 많은 제품 알려줘`
2. `전체 재공 수량 알려줘`

기대 동작:

- 두 번째 질문은 이전 DA filter를 상속하지 않는다.
- `wip_today` 전체 scope로 `WIP`를 합산한다.
- `applied_scope.filters_by_source`에 `OPER_NAME` filter가 없어야 한다.

### 14. Total Production/WIP/Target

질문:

`오늘 생산량/재공/목표 값을 보여줘`

기대 동작:

- 사용 dataset: `production_today`, `wip_today`, `target`
- 특정 공정 조건이 없으므로 전체 합계로 응답한다.

### 15. Date-Split Production Vs Plan Gap

질문:

`어제 생산량과 오늘 생산계획의 차이수량을 제품별로 알려줘`

기대 동작:

- `production`은 어제 날짜로 조회한다.
- `target`은 오늘 계획으로 조회한다.
- source별 날짜 scope가 섞이지 않아야 한다.
- 결과 컬럼에 `PRODUCTION`, `OUT_PLAN`, `BALANCE`가 있어야 한다.

### 16. HBM Equipment By Model

질문:

`오늘 HBM 장비 보유 현황을 EQP_MODEL별로 알려줘`

기대 동작:

- 사용 dataset: `equipment_status`
- HBM 조건은 metadata의 product rule 또는 catalog filter로 표현한다.
- 결과 컬럼에 `EQP_MODEL`, `EQP_COUNT`, `PRESS_CNT`가 있어야 한다.

## Additional Domain Questions

아래 질문은 metadata seed와 LLM planner 확장을 검증할 때 사용한다.

- 오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 제품별/공정별로 보여줘.
- 어제 AUTO향 제품 PKG OUT 실적과 오늘 아침 전체 재공을 제품별로 정리해줘.
- 오늘 INPUT계획대비 D/A공정에서 생산량이 저조한 제품을 알려줘.
- 오늘 D/A1공정에서 목표값 대비해서 생산량이 저조한 제품을 알려줘.
- 현재 작업대기 Lot 수량을 공정별로 알려줘.
- 현재 DA공정에서 재공 lot이 몇개인지, wafer가 몇개인지, die수량은 몇개인지 알려줘.
- 오늘 HBM 장비 보유 현황을 EQP_MODEL별로 알려줘. 이어서 해당 HBM 제품들의 레시피별 UPH도 보여줘.

## Release Gate

권장 순서:

1. `python -m compileall -q reference_runtime langflow_components tools`
2. `python -m pytest tests -q`
3. `python tools\validate_regression.py`
4. `python tools\upload_json_to_mongodb.py --dry-run`
5. 실제 LLM 연결 후 intent JSON, normalized plan, retrieval jobs, pandas code JSON, final payload를 케이스별로 캡처한다.

LLM smoke test는 숫자보다 구조를 먼저 본다. planner가 multi-step을 단순 multi-retrieval로 뭉개거나, pandas fallback이 실패를 숨기면 실패로 판단한다.

