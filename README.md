# Metadata Driven Langflow V3

`metadata_driven_v3`는 제조 데이터 질의/분석 Agent를 처음부터 다시 구현할 개발자에게 넘기기 위한 독립 실행형 Langflow 구현본입니다.

구현 기준은 다음 두 문서입니다.

- `docs/METADATA_AUTHORING_FLOW_GUIDE.md`
- `docs/DATA_RETRIEVAL_SOURCES.md`
- `langflow_components/domain_authoring_flow/raw_text_input_example.md`
- `langflow_components/table_catalog_authoring_flow/raw_text_input_example.md`
- `langflow_components/main_flow_filters_authoring_flow/raw_text_input_example.md`

핵심 흐름은 아래 계약을 따릅니다.

```text
state -> metadata load -> intent plan -> retrieval routing -> retrieval -> pandas postprocess -> final answer/state
```

메타데이터/도움말/카탈로그 질문은 intent plan 전에 별도 라우팅합니다. `03`는 metadata 기반 후보 컨텍스트만 만들고, 작은 route-classifier LLM이 질문 유형 기준으로 metadata QA인지 실제 데이터 분석인지 판정합니다.

## 폴더 구조

| path | 설명 |
| --- | --- |
| `metadata/` | domain, table catalog, main flow filter, regression question seed |
| `reference_runtime/` | Langflow 없이 로컬에서 검증하는 Python reference runtime |
| `langflow_components/router_flow/` | 질문 유형을 분류하는 router flow components |
| `langflow_components/data_analysis_flow/` | source 조회, pandas 분석, result store, 답변 생성 components |
| `langflow_components/*_authoring_flow/` | 자연어 metadata authoring flows |
| `sample_data/` | dummy/source 검증용 fixture |
| `tools/` | 실행, 검증, MongoDB 업로드 스크립트 |
| `tests/` | runtime, component contract, LLM-node-style flow tests |
| `docs/` | 구현/연결/운영/검증 가이드 |

## Recommended Split Runtime

신규 운영 기준은 combined `main_flow`가 아니라 backend orchestrator가 flow를 분기 호출하는 구조입니다.

```text
Web/API
-> router_flow
-> backend orchestrator
-> metadata_qa_flow | data_analysis_flow | report_generation_flow | operations_diagnosis_flow
```

- `router_flow/`: 질문 유형을 분류하고 `selected_flow`를 반환합니다.
- `metadata_qa_flow/`: 조회 가능한 데이터 목록, query template, 활용 예시, domain 정보, greeting/help를 답합니다.
- `data_analysis_flow/`: 실제 source 조회, pandas 분석, MongoDB result store, 최종 답변을 담당합니다.
- `report_generation_flow/`: 리포트 생성 요청 확장 flow입니다.
- `operations_diagnosis_flow/`: 운영 이상/병목 진단 요청 확장 flow입니다.

## Data Analysis Flow

Langflow canvas에서는 LLM node를 중간에 명시적으로 둡니다.

```text
Chat Input
-> router_flow
-> data_analysis_flow 00 Analysis Request Loader
-> 01 Metadata Context Loader
-> 02 Intent Prompt Builder
-> Gemini/LLM Intent JSON
-> 03 Intent Plan Normalizer
-> 04 Previous Result Restore Router
-> 05 MongoDB Data Loader (only when previous_result_restore.required=true)
-> 06 Previous Result Restore Merger
-> 07~12 source retriever/merger nodes
-> 13 Retrieval Payload Adapter
-> 14 Pandas Prompt Builder
-> Gemini/LLM Pandas Code JSON
-> 15 Pandas Code Executor
-> 16A Pandas Repair Payload Builder
-> 16B Pandas Repair Prompt Builder
-> optional Pandas Repair LLM + second 15 Pandas Code Executor
-> 17 MongoDB Data Store
-> 18 Answer Prompt Builder
-> Gemini/LLM Final Answer
-> 19 Answer Response Builder
-> 20 Answer Message Adapter
-> Chat Output
```

각 component 파일은 Langflow Desktop에 하나씩 붙여 넣어도 동작하도록 sibling helper import 없이 작성되어 있습니다.


## V3 구현 기준

v3는 `metadata_driven_v2`의 split-flow 구조를 기준으로 삼고, `pkg_agent_langflow`에서 검증된 analysis-step 중심 사고를 pandas fallback primitive로 더 흡수한 버전입니다. 운영 flow는 router, data analysis, metadata QA, report, diagnosis, session state, metadata authoring으로 분리해 Langflow canvas에서 흐름을 읽기 쉽게 유지합니다.

v3에서 새로 보강한 핵심은 `step_plan`의 범용 집계 primitive입니다. `aggregate_sum`, `aggregate_by_group`, `aggregate_metric`, `aggregate_sum_by_group`, `sum_by_group`은 `source_alias`, `group_by`, `metric` 또는 `metrics`, `aggregation`만으로 실행됩니다. 이로써 새 업무의 단순 집계/그룹핑은 Python의 `analysis_kind` 분기 추가 없이 metadata recipe와 LLM plan 계약만으로 처리할 수 있습니다.
## 빠른 검증

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v3
python -m compileall -q reference_runtime langflow_components tools tests
python -m pytest tests -q
python tools\validate_regression.py
python tools\upload_json_to_mongodb.py --dry-run
python tools\validate_service_readiness.py
```

현재 로컬 검증 기준으로 `python -m pytest tests -q -p no:cacheprovider`는 166개 테스트 통과, `python tools\validate_regression.py`는 23/23 회귀 케이스 통과 상태입니다. 최신 리포트는 `validation_runs/20260620_142530/REPORT.md`입니다.

Gemini component-level live 검증은 토큰 사용을 줄이기 위해 대표 2건만 실행했습니다. `multi_step_rank_wip_with_production`, `top_wip_process_hold_lot_in_tat` 모두 통과했으며, 리포트는 `validation_runs/20260620_141405_component_llm/REPORT.md`입니다.

LLM-in-the-loop 검증도 대표 2건만 실행했고 `2/2` 통과했습니다. 리포트는 `validation_runs/20260620_142650_llm/REPORT.md`입니다.

`validate_service_readiness.py`는 AST, pytest, regression, MongoDB metadata dry-run을 한 번에 실행하고 `validation_runs/<timestamp>_service_readiness/REPORT.md`를 남깁니다. `.env`에 `LLM_API_KEY`와 `LLM_MODEL_NAME`이 있으면 component-level Gemini 검증도 자동으로 1건 실행합니다. 비용 없이 로컬/구조 게이트만 갱신하려면 `--skip-live-llm`, production cutover 전에 live LLM 검증을 필수로 강제하려면 `--require-live-llm`을 사용합니다.

실제 LLM 검증은 `.env`의 Gemini/MongoDB 설정을 사용합니다.

```powershell
python tools\validate_env.py
python tools\validate_gemini_connection.py
python tools\validate_component_llm_flow.py --case multi_step_rank_wip_with_production --case top_wip_process_hold_lot_in_tat
python tools\validate_llm_in_loop.py --limit 1
python tools\validate_llm_in_loop.py
```

## 주요 검증 질문

`metadata/regression_questions.json`에는 현재 필수 회귀 질문 23개가 들어 있습니다. 검증 범위는 단순 답변 문구가 아니라 아래 계약입니다.

- intent type과 analysis kind
- 사용 dataset과 source별 date/filter scope
- DA/WB 같은 공정 그룹 확장
- LPDDR5/HBM 같은 제품 조건 적용
- lot count는 `LOT_ID.nunique()` 사용
- follow-up state 사용 및 scope reset
- production/wip/target join과 achievement/balance 계산
- pandas code JSON 생성, AST guardrail, in-memory frame 실행

검증 결과는 `validation_runs/<timestamp>/REPORT.md`와 `results.json`에 저장됩니다.

## MongoDB

Main flow result rows use a separate full-name collection, `MONGODB_RESULT_COLLECTION` (default `agent_v3_result_store`).
If the caller passes compact previous `state.current_data` with preview rows, row count, columns, `data_ref`, and product key summary, `00 Request State Loader` is enough before metadata loading.
In `data_analysis_flow`, `04 Previous Result Restore Router` decides whether full previous rows are needed. Backend or Langflow branch logic should call `05 MongoDB Data Loader` only when `previous_result_restore.required=true`; `06 Previous Result Restore Merger` then merges the optional loader branch back into the main payload.
When a follow-up question must recalculate, filter, sort, regroup, or show detail rows from the previous result itself, `03 Intent Plan Normalizer` sets `requires_full_previous_result_restore=true` or `previous_result_restore_mode=full`.
`17 MongoDB Data Store` writes both source `runtime_sources` and final pandas `analysis.rows` right after the pandas repair branch, then leaves preview rows plus MongoDB `data_ref` pointers in the payload.
Follow-up product context is carried in `state.current_data.product_key_values`, so product-key follow-ups do not need to load full previous rows.

`.env`는 보안상 복사하지 않았습니다. `.env.example`을 기준으로 로컬 값을 채워 사용합니다. MongoDB metadata는 prefix로 collection을 조합하지 않고 full collection name 3개를 그대로 입력합니다. 기본값은 `MONGODB_DATABASE=metadata_driven_agent_v3`, `MONGODB_DOMAIN_COLLECTION=agent_v3_domain_items`, `MONGODB_TABLE_CATALOG_COLLECTION=agent_v3_table_catalog_items`, `MONGODB_MAIN_FLOW_FILTER_COLLECTION=agent_v3_main_flow_filters`입니다.

업로드 전 dry-run으로 collection과 document count를 확인하세요.

```powershell
python tools\upload_json_to_mongodb.py --dry-run
python tools\validate_service_readiness.py
```

필요한 metadata만 부분 업로드하려면 `--metadata-kind`를 사용합니다. 기본값은 3종 전체 업로드입니다.

```powershell
# domain metadata만 확인/업로드
python tools\upload_json_to_mongodb.py --dry-run --metadata-kind domain
python tools\upload_json_to_mongodb.py --metadata-kind domain

# table catalog와 main flow filter만 업로드
python tools\upload_json_to_mongodb.py --metadata-kind table-catalog --metadata-kind main-flow-filter
```

현장 작업자가 JSON을 직접 올리는 대신 자연어로 metadata를 등록하는 경우에는 각 authoring flow 폴더의 `raw_text_input_example.md` 예시 문장을 해당 flow 입력으로 사용하세요.

## Langflow 연결 문서

- `langflow_components/domain_authoring_flow/raw_text_input_example.md` - 업무 용어 metadata 입력 예시
- `langflow_components/table_catalog_authoring_flow/raw_text_input_example.md` - 데이터셋/table catalog metadata 입력 예시
- `langflow_components/main_flow_filters_authoring_flow/raw_text_input_example.md` - main flow filter metadata 입력 예시
- `langflow_components/router_flow/CONNECTION_GUIDE.md`
- `langflow_components/metadata_qa_flow/CONNECTION_GUIDE.md`
- `langflow_components/data_analysis_flow/CONNECTION_GUIDE.md`
- `langflow_components/report_generation_flow/CONNECTION_GUIDE.md`
- `langflow_components/operations_diagnosis_flow/CONNECTION_GUIDE.md`
- `langflow_components/domain_authoring_flow/CONNECTION_GUIDE.md`
- `langflow_components/table_catalog_authoring_flow/CONNECTION_GUIDE.md`
- `langflow_components/main_flow_filters_authoring_flow/CONNECTION_GUIDE.md`
- `docs/LANGFLOW_NODE_CONNECTION_GUIDE.md`
- `docs/LANGFLOW_IMPLEMENTATION_GUIDE.md`
- `docs/WEB_IMPLEMENTATION_GUIDE.md` - main flow와 metadata authoring flow를 업무 web으로 감싸기 위한 구현 요구사항









