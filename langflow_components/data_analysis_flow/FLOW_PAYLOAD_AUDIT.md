# Data Analysis Flow Payload Audit

작성 목적: `data_analysis_flow`의 payload가 노드 사이를 지나가며 커지는 지점을 단계별로 줄이기 위한 기준 문서다. 이 문서는 먼저 현재 계약을 관찰하고, 이후 작은 단위로 정리하면서 갱신한다.

## 원칙

- prompt builder 노드는 LLM 입력 문자열을 만들기 위한 context만 구성한다. downstream 실행 노드는 prompt builder의 payload가 아니라 canonical payload를 직접 받는다.
- canonical 위치를 하나 정한다. 조회 계획은 `intent_plan.retrieval_jobs`를 기준으로 하고, top-level `retrieval_jobs` mirror는 만들지 않는다.
- row data는 `runtime_sources` 또는 저장된 `data_ref` 중 하나를 기준으로 이동한다. 같은 row가 `source_results.preview_rows`, `runtime_sources`, `analysis.rows`, `data.rows`, `state.current_data.rows`에 동시에 오래 남지 않게 한다.
- 의미 판단 보완은 우선 prompt/metadata에 둔다. Python fallback은 schema 안정화, 어댑터, 실제 실행 안전성에 필요한 범위로 제한한다.
- 각 축소는 대표 질문과 pytest subset을 통과한 뒤 다음 구간으로 넘어간다.

## 현재 주요 흐름

| 구간 | 노드 | 주요 입력 | 새로 만들거나 크게 바꾸는 key | 다음 구간에서 주로 쓰는 key |
| --- | --- | --- | --- | --- |
| request | `00_analysis_request_loader.py` | question, previous state | `request`, compact `state`, `info/warnings/errors` | `request`, `state` |
| metadata | `01_metadata_context_loader.py` | payload | `metadata`, initial `metadata_context` | `metadata`, `metadata_context` |
| intent prompt | `02_intent_prompt_builder.py` | payload, specialized prompt | prompt text, prompt payload | prompt text only |
| intent normalize | `03_intent_plan_normalizer.py` | payload, LLM JSON | `intent_plan`, refreshed `metadata_context`, `info/warnings` | `intent_plan`, `metadata_context` |
| previous restore | `04`~`06` | payload, restore payload | restored `runtime_sources` / previous state related keys | `runtime_sources`, `source_results`, `state` |
| retrieval | `07`~`11` | payload | branch-level `retrieval_payload.source_results` | `source_results` |
| retrieval merge | `12_source_retrieval_merger.py` | branch retrieval payloads | wrapped `retrieval_payload` with `source_results`, `intent_plan`, `state` | `source_results` |
| pandas adapter | `13_retrieval_payload_adapter.py` | main payload, retrieval payload | `runtime_sources`, compact `source_results` | `runtime_sources`, `source_results` |
| pandas prompt | `14_pandas_prompt_builder.py` | payload, specialized functions | prompt text, `pandas_function_case_runtime` in prompt payload | prompt text only; executor gets original payload |
| pandas execute | `15_pandas_code_executor.py` | payload, pandas LLM JSON | `analysis`, `warnings` from analysis errors | `analysis` |
| repair | `16A`~`16B`, second `15` | payload | `pandas_repair`, repaired `analysis` | `analysis`, `pandas_repair` |
| store | `17_mongodb_data_store.py` | payload | stores large rows, may compact `runtime_sources` and add refs | `mongo_data_store`, compact refs |
| answer prompt | `18_answer_prompt_builder.py` | payload | prompt text, compact answer context | prompt text only |
| answer response | `19_answer_response_builder.py` | payload, answer LLM output | `data`, `applied_scope`, `answer_message`, next `state`, removes `runtime_sources` | `data`, `applied_scope`, `answer_message`, `state` |
| display/api | `20`, `21` | payload | user markdown message, API response | final outputs |

## 중복/비대화 후보

| 후보 | 현재 위치 | 관찰 | 정리 방향 |
| --- | --- | --- | --- |
| 조회 계획 | `intent_plan.retrieval_jobs` | 03은 조회 계획을 `intent_plan` 안에만 세팅한다. downstream은 `intent_plan`을 직접 본다. | top-level mirror를 만들지 않고 검증/리포트 도구도 `intent_plan.retrieval_jobs`를 읽는다. |
| dataset 목록 | `intent_plan.datasets`, retrieval job list, `applied_scope.datasets`, API `intent.datasets` | 같은 dataset 정보가 여러 단계에서 재구성된다. | 최종 표시용은 `applied_scope`, 실행용은 `intent_plan.retrieval_jobs`에서 파생하는 방향 검토. |
| source rows | `runtime_sources`, `source_results.preview_rows`, `analysis.rows`, `data.rows`, `state.current_data.rows` | 단계가 진행될수록 같은 row가 preview와 full result로 중복될 수 있다. | 13 이후 실행 중에는 `runtime_sources`, 19 이후 응답/상태에는 `data`와 ref만 남기는 방향 유지. 중간 preview row 보존 필요성 점검. |
| source metadata | `source_results`, `applied_scope.filters_by_source`, `metadata_context.filter_refs` | 필터/파라미터 표시용 정보가 여러 형태로 파생된다. | 원본은 `source_results.applied_filters/applied_params`, 표시용은 19에서 파생. 저장 시 중복 줄이기. |
| pandas code/debug | `analysis.analysis_code`, `analysis.pandas_code_json`, API developer view | debug에는 유용하지만 최종 사용자 payload에는 무겁다. | API/debug 전용으로 유지하고 session state에는 넣지 않는지 확인. |
| errors/warnings/info | top-level `errors/warnings/info`, `analysis.errors`, API analysis errors | 19에서 top-level errors에 analysis errors를 다시 합친다. | canonical severity 위치를 정하고 final response에서 중복 표시 여부 점검. |
| metadata_context | 01 초기 context, 03 normalized context, 19 applied_scope.metadata_refs | 의미가 다른 context가 같은 key로 교체된다. | 01은 load info, 03은 used refs로 분리하거나 03 canonical만 남기는지 검토. |
| function-case trace | `analysis.function_case_trace`, answer context, API developer view | 최근 추가된 trace는 결과 설명에 필요하지만 크기가 커질 수 있다. | 최대 100 rows 제한은 있음. final state 저장 대상인지 확인. |

## 먼저 줄일 후보

1. `12 -> 13` 경계: `12`가 `retrieval_payload` wrapper 안에 `intent_plan/state`를 다시 넣는다. `13`은 main payload도 별도로 받으므로, wrapper에는 `source_results`만 남길 수 있는지 검토한다.
2. `03` 출력: top-level `retrieval_jobs` mirror는 제거했고, 조회 계획은 `intent_plan.retrieval_jobs`를 canonical로 사용한다.
3. `18 -> 19` 경계: 18은 prompt-only 노드다. 현재 연결 가이드처럼 19가 17 payload를 직접 받는 구조를 유지하고, 18의 prompt payload가 downstream으로 새지 않게 테스트한다.
4. `19` 이후: `analysis.rows`와 `data.rows`가 둘 다 API까지 간다. API에서 둘 다 필요한지, `analysis.rows`는 debug/analysis view에만 두고 state에는 `data`만 남기는지 확인한다.
5. `17` 저장 전후: `runtime_sources` compact/ref 처리와 `source_results` ref 적용이 동시에 일어난다. 저장 이후 payload에 full row가 남는지 대표 질문으로 확인한다.

## fallback/복잡도 점검 후보

- `03_intent_plan_normalizer.py`: recipe 보정, quantity term 보정, product-token 보정, follow-up 보정이 한 파일에 많이 모여 있다. 먼저 payload 축소와 무관한 의미 fallback은 문서화만 하고, 삭제는 뒤로 미룬다.
- `15_pandas_code_executor.py`: `_fallback_result_df` 계열은 테스트 안정성에 기여하지만 의미 보정을 많이 한다. 먼저 어떤 질문에서 fallback이 실제 사용되는지 로그/테스트로 확인한다.
- `16A/16B`: repair payload는 실패 시에만 필요하다. 성공 payload에 repair context가 남아 이동하지 않는지 확인한다.

## 대표 회귀 질문

1. `현재 DA공정 재공 수량 알려줘`
2. `오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘`
3. `오늘 lpddr4 lc 64g 제품 생산량 알려줘`
4. `생산 데이터에서 64G L-269P1Q 제품 찾아줘`
5. `64G L-269 ASSY 제품 찾아줘`
6. `오늘 HBM 제품 생산량 알려줘`
7. `T1234567GEN1 LOT의 HOLD이력 알려줘`
8. `현재 hold된 lot list 알려줘`

## 검증 명령

```powershell
python -m pytest -q
python -m pytest tests/test_langflow_llm_node_flow.py -q
python -m pytest tests/test_prompt_language_guides.py -q
```

## 다음 작업

- sub-agent audit 결과를 기준으로 `03_intent_plan_normalizer.py`와 `15_pandas_code_executor.py`의 의미 보정/fallback은 바로 삭제하지 않고, metadata/recipe/prompt로 옮길 수 있는 단위부터 별도 작업으로 다룬다.
- 첫 번째 실제 축소 대상은 `12 Source Retrieval Merger`의 wrapper payload로 검토한다.
- 축소 전후 대표 질문 payload key diff를 남기는 작은 smoke helper를 만들지 여부를 결정한다.

## 1차 정리 결과

- `12_source_retrieval_merger.py`는 여러 retrieval branch의 `source_results`만 병합한다.
- `intent_plan`과 `state`의 canonical 위치는 main payload이므로, `12`의 `retrieval_payload` wrapper에는 더 이상 `route`, `intent_plan`, `state`를 복사하지 않는다.
- `13_retrieval_payload_adapter.py`는 main payload와 merged retrieval payload를 분리해서 받으며, merged payload에서는 `source_results`만 읽는다.
- 회귀 방지를 위해 `tests/test_source_retrievers.py`에 merged wrapper key가 `source_results`만 남는지 확인하는 assertion을 추가했다.

검증:

```powershell
python -m pytest -q tests/test_source_retrievers.py
# 17 passed
```

## 2차 정리 결과

- `21_api_response_builder.py`는 최종 API 응답에서 `developer`와 동일한 `debug` 객체를 더 이상 복사하지 않는다.
- 웹 클라이언트는 legacy 응답 호환을 위해 입력 payload의 `debug`를 계속 읽을 수 있지만, 현재 data analysis flow output의 canonical developer payload는 `developer` 하나로 둔다.
- 회귀 방지를 위해 `tests/test_main_flow_api_response_builder.py`에 `developer`가 유지되고 `debug`가 생성되지 않는 assertion을 추가했다.

검증:

```powershell
python -m pytest -q tests/test_main_flow_api_response_builder.py tests/test_web_app_langflow_client.py
# 25 passed
```

대표 기능 회귀:

```powershell
python -m pytest -q tests/test_langflow_llm_node_flow.py::test_intent_normalizer_routes_unregistered_product_tokens_to_function_case tests/test_langflow_llm_node_flow.py::test_intent_normalizer_routes_product_token_metric_filters_to_function_case tests/test_langflow_llm_node_flow.py::test_intent_normalizer_keeps_registered_product_terms_out_of_function_case tests/test_langflow_llm_node_flow.py::test_intent_normalizer_prunes_lot_status_for_followup_equipment_count tests/test_langflow_llm_node_flow.py::test_intent_normalizer_uses_state_product_key_summary_without_full_rows tests/test_langflow_llm_node_flow.py::test_pandas_executor_loads_function_case_helper_from_text_input_message_object
# 6 passed
```

## Sub-agent Audit 요약

- 노드 계약 관점: `02`, `14`, `16B`, `18`은 prompt-only 노드이고, 실행 payload는 각각 `03`, `15`, `19`가 canonical payload를 직접 받는 구조가 가장 안정적이다.
- 중복/bloat 관점: top-level `retrieval_jobs`, `12` wrapper의 `intent_plan/state`, API `developer/debug` 중복, `analysis.rows`와 `data.rows` 중복이 상대적으로 안전한 축소 후보로 보인다.
- 복잡도 관점: `03`은 intent 보정과 도메인 planner 역할이 많이 섞여 있고, `15`는 실행 안정 fallback과 recipe별 fallback이 섞여 있다. 이 둘은 회귀 위험이 크므로 먼저 representative question과 metadata/recipe 이관 계획을 만든 뒤 줄인다.
- 테스트 관점: payload 축소 후에는 `tests/test_source_retrievers.py` 같은 계층별 테스트를 먼저 돌리고, 의미 해석이나 prompt를 건드릴 때는 product-token, registered product term, follow-up equipment, process-scope 질문을 함께 검증한다.

## 순차 점검: 00~06

### 00 Request Loader

- 역할은 question/session/state를 compact request payload로 만드는 것이다.
- `state.current_data.rows`는 preview limit만 남기고 `row_count`, `columns`, `product_key_values`를 보존한다.
- 현재 단계에서 줄일 중복은 크지 않다. follow-up 성능에 필요한 state summary가 있으므로 섣불리 축소하지 않는다.

### 01 Metadata Context Loader

- `metadata`에는 full domain/table/filter metadata가 들어간다.
- `metadata_context.metadata_load`에는 MongoDB load status/count/collection 정보가 들어간다.
- 이후 03에서 같은 `metadata_context` key를 used refs 구조로 교체하므로 의미 충돌 후보가 있다.
- 다만 18/19는 03 이후 `metadata_context`를 metadata refs로 사용하므로 즉시 key 변경은 위험하다. 다음 단계 후보는 `metadata_load`와 `metadata_refs`를 분리하는 설계안 작성이다.

### 02 Intent Prompt Builder

- prompt-only 노드다. 실행 payload로는 01 payload가 03에 직접 들어가야 한다.
- `prompt_payload` output은 디버그/검사용으로는 유용하지만, 03 payload input에 연결하면 `{prompt, payload, prompt_type}` wrapper가 들어가므로 top-level `request/metadata/state`를 잃는다.
- 지금은 output 제거 대신 `CONNECTION_GUIDE.md`의 연결 규칙을 유지한다.

### 03 Intent Plan Normalizer

- canonical 조회 계획은 `intent_plan.retrieval_jobs`다.
- top-level `retrieval_jobs`는 현재 Langflow/legacy/test 편의 mirror로 남아 있다.
- `07 Dummy Retriever`가 plan에 job이 없을 때 top-level fallback을 아직 읽고 있고, 테스트도 top-level mirror를 많이 assert하므로 즉시 제거하지 않는다.
- fallback/repair logic은 안정장치와 도메인 보정이 섞여 있어, prompt/metadata 이관 계획 없이 한 번에 줄이지 않는다.

### 04~06 Previous Restore

- full previous row restore는 follow-up 분석과 직결되어 blast radius가 크다.
- 단, full restore가 필요 없는 summary mode에서는 `04.restore_payload`가 전체 payload를 복사할 필요가 없다.
- 3차 정리로 skip restore branch의 restore payload를 decision/mode만 담는 compact payload로 줄였다. full restore branch는 기존처럼 전체 payload를 유지한다.

검증:

```powershell
python -m pytest -q tests/test_split_flow_contracts.py::test_previous_result_restore_router_and_merger_skip_loader_for_summary_mode tests/test_split_flow_contracts.py::test_previous_result_restore_router_and_merger_use_loader_for_full_mode tests/test_split_flow_contracts.py::test_previous_result_restore_router_uses_source_refs_without_current_data_ref tests/test_mongodb_result_store_flow.py::test_mongodb_loader_restores_followup_source_results_when_full_requested
# 4 passed
```

## 순차 점검: 14~17 Preview

- `14`의 Specialized Functions input은 LLM prompt/reference/runtime metadata로 쓰인다.
- `15`의 Specialized Functions input은 helper 호출만 남은 generated code를 실행하기 위한 runtime helper source로 쓰인다.
- helper 구현이 generic node에 직접 하드코딩된 형태는 아니다.
- `15` fallback은 안정성에는 기여하지만 `step_plan` primitive와 일부 특정 analysis kind 로직까지 포함해 넓다. 의미 품질 개선은 prompt/metadata 우선으로 하고, fallback 축소는 나중에 대표 질문 회귀 검증 후 진행한다.
- `runtime_sources`는 17에서 Mongo store가 성공해야 preview/ref로 줄어든다. Mongo disabled 또는 설정 누락 시에는 full runtime rows가 남으므로, 이 부분은 별도 저장 정책/로컬 실행 정책으로 다룬다.

## 순차 점검: 07~13

### 07~11 Source Retrievers

- 각 source retriever는 source-specific job을 실행하고 `source_results`를 만든다.
- 필요한 실행 정보는 source result item 안의 `dataset_key`, `source_alias`, `source_type`, `applied_params`, `applied_filters`, `source_execution`에 있다.
- branch wrapper 안의 `route`, `intent_plan`, `state`는 12/13에서 실제로 읽지 않는 중복이었다.
- 4차 정리로 `07~11` retrieval wrapper를 `source_type`, `source_results`, optional `skipped/skip_reason`, optional `early_result`만 갖도록 줄였다.

### 12 Source Retrieval Merger

- 여러 branch wrapper 중 skipped payload를 무시하고 `source_results`만 합친다.
- 1차 정리에서 merged wrapper도 `source_results`만 갖도록 줄였다.

### 13 Retrieval Payload Adapter

- canonical main payload와 retrieval payload를 분리해서 받는다.
- retrieval payload에서는 `source_results`만 읽고, main payload의 `intent_plan/state/metadata`를 보존한다.
- `runtime_sources`는 pandas 실행용 full rows이고, `source_results`는 preview/ref/metadata용 compact summary다.

검증:

```powershell
python -m pytest -q tests/test_source_retrievers.py tests/test_langflow_llm_node_flow.py::test_langflow_llm_node_style_flow_contract tests/test_metadata_qa_flow.py::test_direct_metadata_response_passes_through_downstream_nodes
# 19 passed
```

## 순차 점검: 14~17

### 14 Pandas Prompt Builder

- `Specialized Functions` input은 pandas LLM에게 함수 형태와 의도를 보여주는 prompt reference다.
- 선택된 `pandas_function_cases`는 metadata/domain에 있고, 실제 helper 구현은 `Specialized Functions` text 또는 metadata `function_code`에서 온다.
- 14의 `prompt_payload`는 디버그/호환 경로로 `payload`와 `pandas_function_case_runtime`을 함께 갖는다. 15가 이 wrapper도 받을 수 있도록 지원하므로, 지금 단계에서는 제거하지 않는다.

### 15 Pandas Code Executor

- canonical 연결은 13 payload와 14 LLM 응답, 그리고 동일한 `Specialized Functions` text를 15에 넣는 방식이다.
- 호환 연결로 14 `prompt_payload`가 15 payload에 들어와도 내부 `payload`와 `pandas_function_case_runtime`을 추출한다.
- helper 호출 결과에서 `matched_conditions`, `condition_trace`, DataFrame `attrs["matched_conditions"]`를 읽어 `analysis.function_case_trace`에 남긴다. 따라서 제품 토큰이 어떤 컬럼 조건으로 해석됐는지 기록할 수 있다.
- `_fallback_result_df` 계열은 아직 넓다. 다만 이번 정리의 목적은 payload 축소이므로 fallback 축소는 대표 LLM 질문 재검증 세트를 먼저 만든 뒤 별도 단계로 진행한다.

### 16A~16B Repair

- repair payload는 pandas 실패 또는 fallback repairable error가 있을 때만 의미 있게 커진다.
- 성공 경로에서는 `pandas_repair.required=False`만 남는 구조라, 현재 payload 비대화의 주범은 아니다.
- function case가 선택됐는데 helper를 우회한 경우를 repair prompt가 다시 helper 호출/inline 정의 쪽으로 유도한다.

### 17 MongoDB Data Store

- Mongo 저장이 켜져 있으면 `runtime_sources`와 `analysis.rows` 같은 큰 row list를 preview/ref로 축소한다.
- Mongo 저장이 꺼져 있거나 설정이 없으면 full row가 남을 수 있다. 이는 저장소 비활성 상태의 계약이므로 별도 정책 결정 없이 fallback 코드를 늘리지 않는다.

검증

```powershell
python -m pytest -q tests/test_langflow_llm_node_flow.py::test_pandas_executor_loads_function_case_helper_from_prompt_payload_text tests/test_langflow_llm_node_flow.py::test_pandas_executor_loads_function_case_helper_from_text_input_message_object tests/test_langflow_llm_node_flow.py::test_pandas_repair_prompt_preserves_selected_function_case_helper_call tests/test_prompt_language_guides.py::test_specialized_product_helper_uses_mcp_prefix_and_ignores_org tests/test_prompt_language_guides.py::test_component_token_product_lookup_metadata_is_selection_hint_only
# 5 passed
```

## 순차 점검: 18~21

### 18 Answer Prompt Builder

- answer LLM에는 `analysis.rows[:50]`만 전달한다. 이는 답변 품질용 preview이며 downstream 실행 payload가 아니다.
- LLM이 표를 직접 만들지 않도록 하고, 최종 표는 20 Answer Message Adapter가 `data.rows`에서 deterministic하게 렌더링한다.

### 19 Answer Response Builder

- 19가 `analysis`에서 canonical `data`를 만든 뒤에도 `analysis.rows`가 그대로 남아 `data.rows`와 중복됐다.
- 5차 정리로 19 이후 payload에서는 `analysis.rows`를 제거하고 `analysis.rows_moved_to_data=True`만 남긴다.
- `data.rows`, `state.current_data.rows`, `product_key_values`, `data_ref`는 유지되어 follow-up과 결과 테이블은 그대로 동작한다.

### 20 Answer Message Adapter

- 결과 테이블은 `data.rows`만 사용한다.
- pandas 처리 섹션은 `analysis.status`, `analysis.row_count`, `analysis.columns`, `analysis_code`, `function_case_trace`를 사용하므로 `analysis.rows` 제거에 영향이 없다.

### 21 API Response Builder

- 2차 정리에서 최종 API 응답의 `debug` 중복을 제거하고 `developer`만 유지했다.
- 21은 과거 payload 호환을 위해 `analysis.rows`가 있으면 읽을 수 있지만, 19 이후 정상 경로에서는 `data.rows`를 기준으로 응답한다.

검증

```powershell
python -m pytest -q tests/test_langflow_llm_node_flow.py::test_langflow_llm_node_style_flow_contract tests/test_main_flow_api_response_builder.py tests/test_web_app_langflow_client.py
# 26 passed

python -m pytest -q tests/test_langflow_llm_node_flow.py::test_answer_response_strips_llm_embedded_result_table_before_adapter_table tests/test_mongodb_result_store_flow.py::test_answer_response_state_keeps_product_key_summary_without_full_restore tests/test_mongodb_result_store_flow.py::test_answer_response_state_preserves_followup_source_refs tests/test_session_state_flow.py
# 7 passed
```

## 6차 정리 결과

- `18_answer_prompt_builder.py`의 `Prompt Payload`는 디버그/검사용 output이며, `19`에 연결하는 실행 payload가 아니다.
- 6차 정리로 `18`의 `prompt_payload.payload`에서 `metadata`, `runtime_sources`, `state`, `analysis.rows`, `analysis_code`, `pandas_code_json`, `data.rows`를 제거했다.
- `18`의 실제 LLM prompt와 `answer_context`는 그대로 유지하므로 답변 품질용 preview는 유지된다.
- `21_api_response_builder.py`는 top-level `data_refs`를 canonical data reference 위치로 유지하고, 동일한 값을 `developer.data_refs`에 다시 복사하지 않는다.
- `data.rows`와 `state.current_data.rows`, `runtime_source_refs`, `followup_source_results`는 후속 질문/복원 경로와 연결되어 있어 이번 단계에서는 줄이지 않았다.

검증:

```powershell
python -m pytest -q tests/test_langflow_llm_node_flow.py::test_answer_prompt_tells_llm_not_to_render_result_tables tests/test_langflow_llm_node_flow.py::test_answer_prompt_treats_mapped_physical_columns_as_normalized_contract tests/test_langflow_llm_node_flow.py::test_langflow_llm_node_style_flow_contract
# 3 passed

python -m pytest -q tests/test_main_flow_api_response_builder.py tests/test_web_app_langflow_client.py
# 25 passed

python -m pytest -q tests/test_session_state_flow.py tests/test_mongodb_result_store_flow.py::test_answer_response_state_keeps_product_key_summary_without_full_restore tests/test_mongodb_result_store_flow.py::test_answer_response_state_preserves_followup_source_refs tests/test_split_flow_contracts.py::test_previous_result_restore_router_uses_source_refs_without_current_data_ref
# 7 passed
```

## 7차 조사: top-level retrieval_jobs mirror

- canonical 조회 계획은 여전히 `intent_plan.retrieval_jobs`다.
- 운영 retriever(`08`~`11`)와 pandas/answer/display 노드는 `intent_plan.retrieval_jobs`를 기준으로 읽는다.
- `07_dummy_data_retriever.py`만 `intent_plan`이 없을 때 top-level `retrieval_jobs` fallback을 갖고 있다.
- 다만 tests, validation tools, 일부 web/debug 표시가 top-level `payload["retrieval_jobs"]`를 직접 많이 참조한다.
- 따라서 이번 단계에서 top-level mirror를 제거하지 않는다. 제거하려면 먼저 테스트/검증 도구를 `intent_plan.retrieval_jobs` 기준으로 바꾸고, Langflow 연결 가이드의 legacy fallback 필요 여부를 별도로 확인한다.

## 8차 정리 결과: 03 의미 보정과 15 fallback 범위

- `03_intent_plan_normalizer.py`의 제품 토큰 function case 선택은 코드에 박힌 컬럼 목록보다 `pandas_function_cases` metadata의 `required_question_cues`, `question_cues`, `token_columns`, 선택적 `dataset_cues`를 우선 사용한다.
- `POP`, `MOBILE`, `HBM`처럼 기존 `product_terms`로 등록된 제품군은 function case로 보내지 않고 기존 도메인 조건으로 처리한다.
- 사용자가 `512G G-777 제품 생산량`처럼 제품 속성을 일반 filter로 받은 경우, metadata의 token column 기준으로 해당 filter를 pandas helper 단계로 넘기고 source retrieval filter에서는 제거한다.
- `15_pandas_code_executor.py`의 특정 WIP/Lot fallback은 명시적 `analysis_kind`, `matched_analysis_recipe`, 또는 명시적 step operation/rank sequence가 있을 때만 실행한다.
- `HOLD_LOT_COUNT`, `AVG_IN_TAT` 같은 output column 단서만으로 특정 fallback을 발동하지 않는다.
- generic step primitive fallback(`rank_top_n`, aggregate, unique count, left join)은 유지한다.

검증:

```powershell
python -m pytest -q tests/test_langflow_llm_node_flow.py::test_intent_normalizer_routes_unregistered_product_tokens_to_function_case tests/test_langflow_llm_node_flow.py::test_intent_normalizer_rejects_ambiguous_product_token_dataset_guess tests/test_langflow_llm_node_flow.py::test_intent_normalizer_routes_product_token_metric_filters_to_function_case tests/test_langflow_llm_node_flow.py::test_intent_normalizer_uses_function_case_metadata_token_columns tests/test_langflow_llm_node_flow.py::test_intent_normalizer_keeps_registered_product_terms_out_of_function_case
# 5 passed

python -m pytest -q tests/test_pandas_executor_guards.py::test_pandas_executor_replaces_incomplete_top_wip_process_lot_metrics_result tests/test_pandas_executor_guards.py::test_pandas_executor_does_not_apply_specific_lot_fallback_without_recipe_or_step tests/test_pandas_executor_guards.py::test_pandas_executor_replaces_unfiltered_rank_result_with_filtered_step_fallback tests/test_langflow_llm_node_flow.py::test_pandas_executor_falls_back_when_llm_returns_empty_contract_for_wip_lot_sequence tests/test_langflow_llm_node_flow.py::test_pandas_executor_falls_back_from_step_plan_primitives_for_production_equipment_count
# 5 passed

python -m pytest -q
# 314 passed

python tools/validate_current_stage_questions.py
# 10/10 current-stage component LLM cases passed
```

## 9차 정리 결과: top-level retrieval_jobs mirror 제거

- `03_intent_plan_normalizer.py`는 더 이상 top-level `retrieval_jobs`를 만들지 않는다.
- 조회 계획의 canonical 위치는 `intent_plan.retrieval_jobs`로 고정한다.
- `07_dummy_data_retriever.py`의 legacy top-level `retrieval_jobs` fallback도 제거해 dummy retrieval branch가 `intent_plan`만 보게 했다.
- 검증/리포트 도구는 `payload.get("retrieval_jobs")` 대신 `intent_plan.retrieval_jobs`를 읽도록 바꿨다.
- `tests/test_langflow_llm_node_flow.py`는 테스트 helper `_retrieval_jobs(payload)`를 통해 canonical 위치를 검증하고, normalizer 출력에 top-level `retrieval_jobs`가 생기지 않는 것을 확인한다.

검증:

```powershell
python -m pytest -q tests/test_langflow_llm_node_flow.py::test_langflow_llm_node_style_flow_contract tests/test_langflow_llm_node_flow.py::test_intent_normalizer_routes_unregistered_product_tokens_to_function_case tests/test_langflow_llm_node_flow.py::test_intent_normalizer_rejects_ambiguous_product_token_dataset_guess tests/test_langflow_llm_node_flow.py::test_intent_normalizer_routes_product_token_metric_filters_to_function_case tests/test_langflow_llm_node_flow.py::test_intent_normalizer_uses_function_case_metadata_token_columns tests/test_langflow_llm_node_flow.py::test_intent_normalizer_keeps_registered_product_terms_out_of_function_case
# 6 passed

python -m pytest -q tests/test_source_retrievers.py
# 17 passed

python tools/validate_prompt_language_guides.py
# Prompt language guide validation passed

python -m pytest -q
# 314 passed

python tools/validate_current_stage_questions.py
# 10/10 current-stage component LLM cases passed
# report: C:\Users\qkekt\Desktop\metadata_driven_v3\validation_runs\20260628_110613_current_stage_component_llm\REPORT.md
```

## 10차 정리 결과: Playground pandas code 표시 보존

- `20_answer_message_adapter.py`의 `Pandas 처리` code block은 더 이상 `CODE_TEXT_LIMIT`으로 자르지 않는다.
- 결과 테이블 cell, JSON value 같은 일반 표시 값은 기존 `_truncate` 제한을 유지한다.
- API payload의 `analysis.analysis_code`는 이미 원문을 유지하므로, 이번 변경은 Playground message 표시 계층에만 해당한다.

검증:

```powershell
python -m pytest -q tests/test_langflow_llm_node_flow.py::test_answer_message_adapter_does_not_truncate_pandas_code_block tests/test_langflow_llm_node_flow.py::test_answer_message_adapter_koreanizes_plan_and_pandas_reasoning
# 2 passed

python -m pytest -q
# 315 passed
```

## 11차 정리 결과: 미사용 Lot/Hold function case 제거

- 미사용 Lot/Hold 특화 function case는 사용하지 않는 항목으로 판단해 예시와 검증에서 제거했다.
- `domain_authoring_flow/raw_text_input_example.md`의 Lot/Hold function-case 작성 예시를 삭제했다.
- `data_analysis_flow/prompts/SPECIALIZED_FUNCTIONS_INPUT_GUIDE.md`의 Lot/Hold helper 예시와 MongoDB JSON 예시를 삭제했다.
- `02_SPECIALIZED_INTENT_PROMPT.md`에서 복잡한 Lot/Hold 조건을 function case로 유도하는 문장을 제거했다.
- inline function-case 실행 가능성 검증은 Lot/Hold 이름 대신 generic `custom_inline_lookup` 예시로 유지한다.
- MongoDB `agent_v3_domain_items` 컬렉션에서 해당 미사용 function-case document 1건을 삭제했다.

검증:

```powershell
python tools/validate_prompt_language_guides.py
# Prompt language guide validation passed

python -m pytest -q
# 315 passed
```
