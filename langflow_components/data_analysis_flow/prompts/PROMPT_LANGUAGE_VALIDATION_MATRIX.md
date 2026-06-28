# Prompt Language Validation Matrix

이 문서는 데이터 조회 flow의 3개 LLM prompt를 영어에서 한글로 바꿀 때 확인해야 하는 대표 질문 10개와 기대 계약을 정리한다.

## 결론

- 한글 프롬프트로 바꿔도 자연어 지시문만 한글화하고 JSON key, enum 값, operation 이름, Python 변수명, pandas helper function 이름을 그대로 유지하면 구조적으로 큰 문제는 없다.
- 성능 저하가 생긴다면 원인은 보통 한글 자체가 아니라 `intent_type`, `retrieval_jobs`, `step_plan`, `result_df`, `answer_message` 같은 계약명이 번역되거나, 설명형 응답이 JSON/code 계약을 침범하는 경우다.
- 따라서 한글판은 사용자의 한국어 질문 해석에는 유리할 수 있지만, schema/operation/function 이름은 영어 그대로 두는 hybrid prompt가 가장 안전하다.
- 실제 모델 성능 비교는 아래 10개 질문을 같은 모델/temperature/date/metadata로 영문 prompt와 한글 prompt에 각각 실행해서 pass count와 실패 유형을 비교한다.

## 대표 검증 질문 10개

| No | 유형 | 질문 | 기대 계약 |
| --- | --- | --- | --- |
| 1 | 기존 multi-step | 오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘 | `multi_step_analysis`, `rank_wip_then_join_production`, `wip_today + production_today`, DA/WB scope 분리 |
| 2 | 기존 LOT detail | T1234567GEN1 LOT의 HOLD이력 알려줘 | `detail_lookup`, `detail_rows`, `hold_history`, `LOT_ID` param |
| 3 | 기존 Hold list | 현재 hold된 lot list 알려줘 | `detail_lookup`, `detail_rows`, `lot_status`, hold status filter |
| 4 | 기존 WIP total | 현재 DA공정 재공 수량 알려줘 | `single_retrieval_analysis`, `aggregate_wip_total`, `wip_today`, `OPER_NAME` filter |
| 5 | 기존 목표 대비 | 오늘 D/A1공정에서 목표값 대비해서 생산량이 저조한 제품을 알려줘 | `multi_source_analysis`, `low_output_vs_target`, `production_today + target` |
| 6 | 기존 장비 보유 | 오늘 HBM 장비 보유 현황을 EQP_MODEL별로 알려줘 | `single_retrieval_analysis`, `equipment_by_model`, HBM은 product_terms filter |
| 7 | 어제 개선 product token detail | 생산 데이터에서 64G L-269P1Q 제품 찾아줘 | `pandas_function_cases.component_token_product_lookup`, `match_product_tokens`, `detail_rows` |
| 8 | 오늘 개선 product token metric | 오늘 lpddr4 lc 64g 제품 생산량 알려줘 | MODE/DEN/PKG 임의 filter 금지, `component_token_product_lookup` 먼저 적용 후 production aggregate |
| 9 | product_terms 우선순위 | 오늘 HBM 제품 생산량 알려줘 | HBM은 `product_terms` 조건으로 처리, product token function case 사용 금지 |
| 10 | Hold/IN_TAT 공정 집계 | 현재 hold된 lot 중 IN_TAT 24시간 이상인 Lot을 공정별로 집계해서 보여줘 | `lot_status`, `LOT_HOLD_STAT_CD`/`IN_TAT` 조건, 공정별 `LOT_ID` 집계 |

## 로컬 계약 검증

라이브 LLM 없이 확인 가능한 항목:

- 한글 prompt 문서가 필수 schema key를 번역하지 않는지
- 한글 prompt 문서가 `component_token_product_lookup`, `match_product_tokens`, `apply_pandas_function_case`를 그대로 유지하는지
- 10개 검증 질문의 기대 계약이 문서에 남아 있는지
- 기존 deterministic regression과 pytest가 통과하는지

## 2026-06-27 로컬 확인 결과

- `python tools\validate_prompt_language_guides.py`: 통과
- 확인 범위: prompt file 4개 한글판, 대표 질문 10개, deterministic reference 계약 6/6, component-level product/function-case 계약 5/5
- `python -m pytest -q`: 305 passed
- `python tools\validate_regression.py`: 현재 reference_runtime 기준 20/23 passed. 실패 3건은 prompt language 문서가 아니라 오래된 reference_runtime multi-step recipe 불일치이며, 이번 10개 prompt-language matrix 검증 범위와는 분리한다.
- 실제 LLM A/B 성능 비교는 한글 prompt를 Langflow 캔버스에 연결한 뒤 같은 10개 질문을 동일 모델/temperature/date/metadata로 실행해 비교한다.

## 라이브 LLM 비교 권장 명령

현재 컴포넌트 코드는 기본 영문 prompt를 생성한다. 한글 prompt를 실제 flow에 연결한 뒤에는 같은 10개 질문을 아래 방식으로 실행한다.

```powershell
python tools\validate_component_llm_flow.py --case multi_step_rank_wip_with_production --case hold_history_detail --case hold_lot_list --case da_wip_quantity_uses_wip_dataset --case da1_low_output_vs_target --case hbm_equipment_by_model
```

product-token 신규 케이스는 Langflow에서 `14 Pandas Prompt Builder > Specialized Functions`에 helper code를 연결한 상태로 아래 질문을 별도 smoke로 확인한다.

```text
64G L-269P1Q 제품 찾아줘
오늘 lpddr4 lc 64g 제품 생산량 알려줘
오늘 HBM 제품 생산량 알려줘
```
