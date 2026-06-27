# 02 Specialized Intent Prompt

아래 문장을 `02 Intent Prompt Builder > Specialized Prompt` 입력칸에 붙여넣는다.
이 파일은 제조/PKG/제품/Lot/장비 특화 의도 분석 규칙만 담는다. 02번 노드의 기본 prompt에는 공통 JSON/step/retrieval 계약만 둔다.

```text
도메인 특화 의도 분석 규칙:
- 등록된 product_terms, process_groups, status_terms, metric_terms, quantity_terms, analysis_recipes가 있으면 일반 추론보다 먼저 적용한다.
- 등록된 도메인 조건으로 처리 가능한 질문은 pandas_function_cases로 보내지 않는다.
- pandas_function_cases는 일반 필터로 안정적으로 표현하기 어려운 절차형 매칭이나 파싱이 필요할 때만 선택한다.

제품/공정 grain 규칙:
- 제품별/product-by 질문은 product_grain으로 group_by한다.
- 차수별/공정 차수별 질문은 OPER_NUM으로 group_by한다.
- 세부공정별/세부 공정별/process-step 질문은 OPER_NAME으로 group_by한다.
- metric term이 WAFER_OUT_QTY, FAIL_UNIT_QTY 같은 derived output_columns를 정의하면 row-level column을 먼저 계산하고 요청 grain에서 집계한다. detail_rows가 명시되지 않으면 row-level derived 값을 그대로 반환하지 않는다.

제품 token/function-case 규칙:
- 사용자가 "64G L-269P1Q 제품 찾아줘"처럼 제품 속성 token을 자유롭게 섞어서 제품을 찾으면 pandas_function_cases.component_token_product_lookup / match_product_tokens를 사용한다.
- lpddr4 lc 64g처럼 mode/density/package/lead/MCP-style 값이 여러 개 나열되고 product_terms로 정의된 제품군이 아니면 MODE/DEN/PKG_TYPE filter를 임의 생성하지 않는다.
- 이런 경우 pandas_function_case=component_token_product_lookup을 설정하고 aggregate/rank/detail step 전에 apply_pandas_function_case step을 추가한다.
- product-token function case에서는 retrieval_jobs가 helper에 필요한 제품 컬럼을 조회해야 하며, token match를 retrieval_jobs[].filters만으로 표현하지 않는다.
- 단, "64G L-269 ASSY 제품 찾아줘"처럼 제품 token과 찾기/조회 의도만 있고 생산/재공/Lot/Hold/장비/dataset 같은 source family 단서가 없으면 wip_today나 production_today를 임의로 선택하지 않는다. 이 경우 dataset 선택이 불명확하다고 reasoning_steps에 남기고 retrieval_jobs를 만들지 않는다.
- POP, MOBILE, HBM, AUTO향 같은 등록 product_terms는 ordinary metadata-backed filter condition이다. 이 제품군 조건은 pandas function case가 아니다.
- product_terms의 raw condition field는 filter로만 쓰고, 필요하면 PRODUCT_GROUP 같은 사용자-facing scope label을 result_scope_columns/output_columns에 남긴다.
- ranked 또는 aggregated entity가 DEVICE이면 DEVICE 기준으로 group/rank한다. MOBILE 같은 product filter가 있다고 product_grain으로 바꾸지 않는다.

공정/metric source scope 규칙:
- DA, WB, SG, DP, BG, LT, WET 같은 공정명 또는 공정 그룹 표현은 metadata.domain_items.process_groups를 먼저 확인한다.
- 공정 그룹 질문은 해당 그룹에 등록된 세부 OPER_NAME 또는 OPER_SHORT_DESC 조건으로 해석한다.
- 사용자가 "공정별", "세부공정별", "차수별"처럼 breakdown 축을 말하면 그 축을 group_by 또는 step_plan에 명시한다.
- 생산량은 production 계열 dataset, 재공은 wip 계열 dataset, Lot/Hold는 lot 또는 hold 계열 dataset, 장비는 equipment 계열 dataset을 우선 검토한다.
- 사용자가 특정 공정 scope의 생산량, 재공, 목표, Hold, Lot, 장비를 묻는 경우 해당 metric에 맞는 dataset family를 선택한다.
- 같은 질문 안에 여러 공정 scope가 있으면 각 공정 scope를 별도 retrieval_job 또는 별도 step으로 분리한다.
- DA 생산량과 WB 재공을 함께 묻는 경우 DA 조건을 production source에, WB 조건을 wip source에 각각 적용한다.
- 전 공정/전체 공정/all process를 묻는 source에는 공정 필터를 적용하지 않는다.
- 특정 공정 scope를 고른 뒤 전체 합계를 묻는 경우 group_by는 비워두고, 필요한 경우 result_scope_columns나 output_columns로 scope label만 남긴다.

생산/재공/목표/계획 규칙:
- 오늘/현재 질문은 history를 묻지 않는 한 metadata.date_scope가 current_day인 dataset을 우선 사용한다.
- 목표/계획 질문은 target/plan 계열 dataset family와 quantity/metric term을 사용하고, 각 dataset의 date_format을 보존한다.
- 생산량/실적/생산량과 WIP/재공을 함께 묻는 제품별 질문에서 target/목표/계획/달성률/top/rank가 없으면 production_today + wip_today로 aggregate_join을 사용하고 product_grain으로 group_by한다.
- LPDDR5 같은 제품 조건과 DA/WB production + WIP를 함께 묻는 경우 production_today와 wip_today에 각각 공정 그룹 filter를 적용하고 aggregate_join을 사용한다.
- 재공 + 생산량 + 목표값/계획 + 달성률 질문은 production_wip_target_rate를 우선 검토한다.
- 목표값 대비/계획 대비/INPUT계획대비 저조 생산 질문은 low_output_vs_target를 우선 검토한다.
- one-dataset WIP/current quantity total 질문은 aggregate_wip_total을 우선 검토한다.
- 단순 multi-source production + WIP join이고 더 구체적인 analysis_recipes가 없으면 aggregate_join을 사용한다.

Lot/Hold/상태 규칙:
- status_terms는 ordinary metadata-backed filter다. status_terms가 SHIFT 같은 column에 매핑되면 dataset catalog가 지원하는 경우 해당 field를 retrieval job filters와 required_columns에 추가한다.
- status_terms의 시간대 alias, 예를 들어 07:00~15:00, 는 공백이 섞여도 같은 shift/status label alias처럼 처리한다.
- 작업대기/작업중 Lot 수량 질문은 lot_status와 matching status_terms 값을 사용하고 LOT_COUNT는 LOT_ID.nunique()로 계산한다.
- DA/WB 같은 공정 group에서 lot count + wafer count + die quantity를 함께 묻는 질문은 lot_status와 공정 group filter를 사용하고 lot_quantity_summary를 우선 검토한다.
- Lot ID, Hold 상태/사유, 공정명, IN_TAT/HOLD_TM 조건을 자유롭게 섞어 Lot/Hold 목록을 찾는 질문은 등록된 lot_hold_complex_lookup function case가 있을 때 해당 helper를 선택한다.

장비/follow-up 규칙:
- follow-up 장비 현황/설비 현황 질문은 이전 product key를 사용하고 equipment_status를 우선 사용한다.
- follow-up 장비 현황/설비 현황은 equipment_for_previous_products를 사용하고 장비 detail rows를 반환한다.
- follow-up 장비 대수/설비 대수/몇 대 질문은 equipment_count_for_previous_products를 사용하고 EQP_COUNT는 EQPID.nunique()로 계산한다.
- follow-up 장비 대수 질문은 intent_type=followup_transform, dataset은 equipment_status로 제한한다. 할당 장비 count에 capacity를 사용하지 않는다.
- 장비 보유 현황/설비 보유 현황을 EQP_MODEL/model별로 묻는 질문은 equipment_status + equipment_by_model을 사용한다. EQP_COUNT는 EQPID.nunique(), PRESS_CNT는 sum(PRESS_CNT)로 계산한다.

rank/dependent lookup 특화 규칙:
- rank_wip_then_join_production은 반드시 multi_step_analysis로 계획한다.
- top/bottom/rank 뒤에 dependent lookup, count, detail, oldest/longest selection이 이어지면 metadata analysis_recipes를 우선 검토하고 rank step을 dependent step보다 먼저 둔다.
- DA/WB 같은 그룹별 rank 질문은 rank_groups를 사용하고, rank_group_output_column/output_columns에 OPER_GROUP 같은 사용자-facing label column을 둔다.
- rank_groups[].field는 raw metadata-backed field에만 사용하고, 사용자가 raw breakdown axis를 명시하지 않는 한 final output_columns에는 넣지 않는다.
- per-group product ranking은 user-facing group label + product_grain으로 group/rank한다.
- 같은 질문에서 여러 공정 scope의 같은 measure를 묻는 경우 DA_PRODUCTION, DA_WIP, WB_PRODUCTION, WB_WIP처럼 scope-prefixed metric column을 반환한다.

source scope 분리 예시:
- "어제 DP공정에서 생산량이 가장 많은 제품의 오늘 DA공정 재공"처럼 source별 scope가 다르면 첫 retrieval job은 DP/yesterday scope만, 두 번째 retrieval job은 DA/today scope만 갖는다.
- 전일/금일 같은 표현이 한 질문에 같이 있어도 source_scope에 따라 각 source의 date scope를 분리한다.
- today_input, yesterday_input, DA production, WB wip, input source, comparison source, all-process wip 같은 source-local hint는 retrieval_jobs[].source_scope에 남기고 해당 job의 params/filters에만 반영한다.
```
