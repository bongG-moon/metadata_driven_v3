# Flow Audit and V3 Design

## 목적

이 문서는 `C:\Users\qkekt\Desktop\pkg_agent_langflow`와 `C:\Users\qkekt\Desktop\metadata_driven_v2`를 v3 구현 전 기준 flow로 감사한 결과와, `metadata_driven_v3`의 구현 결정을 정리한다. 판단 기준은 다음 두 가지다.

1. metadata만 바꾸면 다른 업무에도 재사용 가능한가.
2. 현재 제조 업무 특화 지식이 Python 하드코딩으로 들어가지 않고 metadata, prompt contract, step plan으로 표현되는가.

## 역할 분담

v3 구현은 아래 관점의 서브 에이전트 팀으로 나누어 검토한 것으로 설계했다.

| 역할 | 책임 | v3 반영 |
| --- | --- | --- |
| Flow Auditor | 기존 Langflow canvas와 payload 흐름을 감사 | v2 split-flow를 기본 구조로 선택 |
| Metadata Architect | domain/table/filter/recipe metadata 경계를 설계 | 자연어 authoring flow 3종 유지 |
| Retrieval Engineer | Oracle, H-API, Datalake, Goodocs, dummy 조회 경계를 관리 | source retriever flow를 data_analysis_flow 안에서 명확히 유지 |
| Pandas Runtime Engineer | LLM pandas code, AST guard, fallback, repair route를 담당 | generic aggregate primitive 추가 |
| QA Engineer | 기존 질문 세트, component shape, compile, regression 검증 담당 | regression_questions와 pytest 기반 검증 유지 |

## pkg_agent_langflow 감사

### 구조

`pkg_agent_langflow`는 `langflow_main/1.main_flow_components`에 00부터 31까지 이어지는 canonical main canvas가 있고, `langflow_main/2.data_retrieval_flow_components`는 별도 Run Flow로 Oracle, H-API, Datalake, Goodocs, dummy 조회를 담당한다. metadata 등록은 `3.domain_authoring_flow_components`, `4.table_catalog_authoring_flow_components`, `5.main_flow_filters_authoring_flow_components`로 분리되어 있다.

### 장점

- `analysis_steps` 계약이 명확하다. pandas 단계가 질문을 다시 해석하지 않고 계획된 step을 실행하게 만드는 방향이 좋다.
- pandas 실패 시 repair payload가 실패 코드, 오류, source schema/preview, plan을 포함해 재작성 route로 넘어간다.
- data retrieval은 별도 Run Flow로 빠져 있어 source별 배포 차이를 흡수하기 쉽다.
- authoring flow가 자연어 입력에서 metadata item을 만드는 구조를 이미 갖고 있다.
- 회귀 질문과 컴포넌트 단위 테스트가 많아 실제 질문 실패를 재현하기 좋다.

### 한계

- main canvas가 31개 노드로 길어져 Langflow 화면에서 전체 흐름을 읽기 어렵다.
- `analysis_steps` executor는 강력하지만 main flow 내부에 많은 책임이 몰려 있다.
- 제조 업무 특화 fallback과 호환 코드가 누적되어, 새 업무 적용 시 어디를 metadata로 바꿔야 하는지 찾기 어렵다.
- v3의 목표인 router/data-analysis/metadata-QA/report/diagnosis 같은 서비스 단위 분리에는 `metadata_driven_v2` 구조가 더 적합하다.

## metadata_driven_v2 감사

### 구조

`metadata_driven_v2`는 combined main flow 대신 backend orchestrator가 `router_flow`로 질문 유형을 먼저 분류하고, `metadata_qa_flow`, `data_analysis_flow`, `report_generation_flow`, `operations_diagnosis_flow` 중 필요한 flow를 호출하는 split runtime을 제안한다. `data_analysis_flow`는 request, metadata load, intent prompt, intent normalizer, previous result restore, source retriever, pandas prompt/executor, repair prompt, result store, answer builder로 나뉜다.

### 장점

- Langflow canvas를 기능별로 나눠 운영자가 흐름을 이해하기 쉽다.
- `analysis_recipes`와 `step_plan_template`를 domain metadata의 1급 항목으로 다룬다.
- `runtime_sources`는 pandas 실행 직전까지만 쓰고, result store 이후에는 `data_ref` 중심 compact payload로 줄인다.
- previous result restore가 summary/full을 나누어 follow-up state 폭증을 막는다.
- domain/table catalog/main flow filter authoring flow가 자연어 입력을 MongoDB 저장 item으로 정규화한다.
- standalone custom component 규칙이 문서와 테스트로 명확하다.

### 한계

- pandas fallback primitive가 `rank_top_n`, unique count, `hold_lot_in_tat_by_process`, `left_join` 중심이라 단순 범용 집계도 별도 `analysis_kind` fallback에 기대는 구간이 있었다.
- 일부 prompt와 fallback 이름에는 제조 도메인 표현이 남아 있어 새 업무로 옮길 때 generic primitive를 더 늘릴 필요가 있다.
- v2 identity와 MongoDB collection 기본값이 v3 산출물에는 맞지 않았다.

## V3 설계 결정

v3는 `metadata_driven_v2`를 구조적 base로 삼는다. 이유는 실제 서비스에서는 사용자가 Langflow 연결을 볼 때 flow의 책임이 분리되어 있어야 하고, metadata QA/실제 데이터 분석/리포트/운영 진단/metadata authoring을 한 canvas에 과도하게 몰아넣지 않는 편이 유지보수에 유리하기 때문이다.

다만 pandas 계획 실행 철학은 `pkg_agent_langflow`의 `analysis_steps` 접근을 받아들인다. v3에서는 우선 `step_plan` fallback primitive를 넓혀, 단순 합계/평균/최대/최소/count/nunique 집계가 metadata recipe와 LLM plan 필드만으로 실행되도록 했다.

## V3 구현 사항

- 프로젝트 identity를 `metadata_driven_v3`, `metadata-driven-v3`, `metadata_driven_agent_v3`, `agent_v3_*` 기본 collection으로 정리했다.
- 복사 산출물인 실행 로그, zip bundle, 비어 있는 staging 폴더는 제거했다.
- `15_pandas_code_executor.py`에 `aggregate`, `aggregate_by_group`, `aggregate_metric`, `aggregate_sum`, `aggregate_sum_by_group`, `sum_by_group` primitive를 추가했다.
- `14_pandas_prompt_builder.py`의 sequential plan rule에 aggregate primitive 계약을 추가했다.
- `tests/test_pandas_executor_guards.py`에 generic aggregate fallback 회귀 테스트를 추가했다.
- `reference_runtime/planner.py`도 `analysis_recipes`의 required cue, dataset family, source alias, step template을 읽어 plan을 만들도록 맞춰 Langflow 정상화 로직과 검증 런타임의 계약 차이를 줄였다.
- `reference_runtime/analysis.py`에 `rank_top_n`, generic aggregate, `equipment_count_by_product`, `hold_lot_in_tat_by_process`, `left_join` step primitive 실행기를 추가해 recipe 기반 순차 분석을 로컬 회귀 검증에서도 실행한다.
- 자연어 metadata authoring flow 3종과 split-flow connection guide는 유지했다.

## Payload 원칙

v3 중간 payload는 아래 항목만 지속적으로 전달한다.

| key | 사용 구간 |
| --- | --- |
| `request` | session id, question, timezone/date |
| `state` | compact previous state, current_data summary, data_ref |
| `metadata` | domain/table catalog/main flow filters |
| `intent_plan` | route, analysis_kind, step_plan, output contract |
| `retrieval_jobs` | source별 조회 요청 |
| `runtime_sources` | pandas 실행 직전까지만 유지되는 source rows |
| `source_results` | compact retrieval trace |
| `analysis` | pandas execution result and repair status |
| `data` | user/API-facing result preview/ref |
| `applied_scope` | dataset/filter/params/metadata refs |
| `answer_message` | final Korean answer |

full rows는 session state에 복사하지 않고 MongoDB result store의 `data_ref`로 복원한다.

## 현재 검증 결과

2026-06-20 기준 로컬 검증 결과는 다음과 같다.

- AST parse: `reference_runtime/planner.py`, `reference_runtime/analysis.py` 통과
- Pytest: `python -m pytest tests -q -p no:cacheprovider` -> 166 passed
- Regression: `python tools\validate_regression.py` -> 23/23 passed
- 최신 회귀 리포트: `validation_runs/20260620_142530/REPORT.md`
- 제한 live Gemini component 검증: `python tools\validate_component_llm_flow.py --case multi_step_rank_wip_with_production --case top_wip_process_hold_lot_in_tat` -> 2/2 passed, report `validation_runs/20260620_141405_component_llm/REPORT.md`
- 제한 LLM-in-the-loop 검증: `python tools\validate_llm_in_loop.py --limit 2` -> 2/2 passed, report `validation_runs/20260620_142650_llm/REPORT.md`

특히 추가 회귀 케이스인 `top_wip_process_hold_lot_in_tat`, `top_production_products_equipment_count`, `top_wip_product_oldest_lot`은 hardcoded question branch가 아니라 metadata `analysis_recipes` 기반으로 intent, dataset, step plan, pandas-style execution 계약을 만족한다.
## 남은 운영 검증 게이트

1. `python -m compileall -q reference_runtime langflow_components tools tests`
2. `python -m pytest tests -q`
3. `python tools\validate_regression.py`
4. `python tools\upload_json_to_mongodb.py --dry-run`
5. 실제 `.env` 주입 후 `validate_env.py`, `validate_gemini_connection.py`, `validate_llm_in_loop.py`

5번 중 대표 2건 live Gemini component 검증과 대표 2건 LLM-in-the-loop 검증은 통과했다. 전체 regression prompt 및 live source system 검증은 운영 환경의 비용/권한 정책에 맞춰 별도 게이트로 실행한다.





