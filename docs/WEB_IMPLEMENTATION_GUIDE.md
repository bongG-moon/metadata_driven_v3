# Web Implementation Guide

이 문서는 `metadata_driven_v3`의 현재 Langflow 구성 기준으로 backend orchestrator, split query flows, metadata authoring flow를 web에서 안전하게 사용하기 위한 구현 가이드다.

## 0. Current Runtime Direction

신규 운영 구조는 단일 `main_flow`가 아니라 아래처럼 분리한다.

```text
Web/API
-> router_flow
-> backend orchestrator
-> metadata_qa_flow | data_analysis_flow | report_generation_flow | operations_diagnosis_flow
```

combined `main_flow` canvas는 제거되었다. web backend는 router를 먼저 실행하고, router의 `selected_flow`에 따라 하위 flow를 한 번 더 호출한다.

대상 사용자는 Langflow, Python, JSON, MongoDB를 직접 다루지 않는 현업 작업자다. Web은 Langflow canvas 편집기를 노출하는 도구가 아니라, 자연어 질의, metadata 등록, 검토, 검증을 업무 화면으로 감싸는 얇은 운영 레이어여야 한다.

기준이 되는 현재 flow 문서:

- `langflow_components/router_flow/CONNECTION_GUIDE.md`
- `langflow_components/metadata_qa_flow/CONNECTION_GUIDE.md`
- `langflow_components/data_analysis_flow/CONNECTION_GUIDE.md`
- `langflow_components/report_generation_flow/CONNECTION_GUIDE.md`
- `langflow_components/operations_diagnosis_flow/CONNECTION_GUIDE.md`
- `langflow_components/domain_authoring_flow/CONNECTION_GUIDE.md`
- `langflow_components/table_catalog_authoring_flow/CONNECTION_GUIDE.md`
- `langflow_components/main_flow_filters_authoring_flow/CONNECTION_GUIDE.md`
- `docs/METADATA_AUTHORING_FLOW_GUIDE.md`
- `docs/DATA_RETRIEVAL_SOURCES.md`

## 1. 구현 범위

Web에서 제공해야 하는 기능은 네 가지다.

1. 제조 데이터 질의/분석 실행
2. 자연어 기반 metadata 등록
3. 기존 metadata 조회/검토
4. 등록 후 main flow 검증 질문 실행

Web에서 일반 사용자에게 제공하지 않을 기능:

- Langflow node/canvas 편집
- raw MongoDB write/edit
- source credential, MongoDB URI, Langflow API key 노출
- main agent prompt 또는 pandas code 직접 수정
- metadata collection과 result row collection의 직접 조작

## 2. 현재 Flow 구조

권장 운영 구조:

```text
Browser UI
-> Web Backend API
-> Langflow Run API
-> Langflow router/subflows/authoring flows
-> MongoDB metadata collections and result store
```

Query runtime은 split mode로 동작한다. Router가 만든 `selected_flow`에 따라 backend가 `metadata_qa_flow`, `data_analysis_flow`, `report_generation_flow`, `operations_diagnosis_flow` 중 하나를 호출한다.

현재 `metadata_driven_v3`의 flow는 아래 다섯 묶음으로 본다.

| Flow | 폴더 | Web 관점의 역할 |
| --- | --- | --- |
| Query router | `langflow_components/router_flow/` | 질문 유형을 분류하고 호출할 하위 flow를 선택 |
| Metadata QA | `langflow_components/metadata_qa_flow/` | metadata 질문에 직접 답변 |
| Data analysis | `langflow_components/data_analysis_flow/` | 질문, state, metadata를 받아 retrieval, pandas, 답변, next state 생성 |
| Data retrieval | `langflow_components/data_analysis_flow/07~12_*` | `source_type`별 조회 결과를 `retrieval_payload`로 병합 |
| Domain authoring | `langflow_components/domain_authoring_flow/` | domain 용어/규칙을 자연어에서 MongoDB item으로 저장 |
| Table catalog authoring | `langflow_components/table_catalog_authoring_flow/` | dataset/source/column/filter mapping을 자연어에서 저장 |
| Main flow filter authoring | `langflow_components/main_flow_filters_authoring_flow/` | 날짜, 공정, 제품, LOT, 장비 등 filter metadata 저장 |

Web backend가 담당해야 하는 일:

- Langflow flow id와 API key 관리
- MongoDB URI, LLM key, source credential 같은 secret 관리
- 사용자 session과 main flow `state` 저장
- authoring 중복 선택용 pending record 저장
- Langflow 응답을 화면용 response로 정리
- 큰 result row가 `data_ref`로 축약된 경우 필요 시 backend에서 재조회

Browser가 직접 하지 말아야 하는 일:

- MongoDB URI, source credential, Langflow admin token 보관
- MongoDB collection 직접 write
- Langflow 내부 payload 전체 표시
- `runtime_sources`, full prompt, raw source rows, secret 포함 config 표시

## 3. 현재 Query Flow 계약

현재 query runtime은 router/subflow 연결 순서를 따른다.

```text
Web/API
-> router_flow 00~05
-> selected subflow Run API
-> selected subflow API response
```

Web/API backend는 `05`의 route response JSON을 코드에서 읽고 다음 subflow API를 직접 호출한다. Langflow canvas 안에서 Run Flow node를 연결할 때는 Run Flow가 text input만 받으므로 `router_flow 00~07`까지 사용한다. `06 Run Flow Text Switch`의 선택된 text output을 Run Flow input에 연결하고, 각 Run Flow output은 `07 Selected Run Flow Message Merger`로 모아 선택된 message 하나만 Chat Output에 연결한다.

`data_analysis_flow`가 선택된 경우 subflow 내부 순서는 다음과 같다.

```text
00 MongoDB Session State Loader
-> 00 Analysis Request Loader
-> 01 Metadata Context Loader
-> 02 Intent Prompt Builder
-> Intent LLM
-> 03 Intent Plan Normalizer
-> 04 Previous Result Restore Router
-> 05 MongoDB Data Loader, only when full restore is required
-> 06 Previous Result Restore Merger
-> 07~11 source retrievers
-> 12 Source Retrieval Merger
-> 13 Retrieval Payload Adapter
-> 14 Pandas Prompt Builder
-> Pandas Code LLM
-> 15 Pandas Code Executor
-> 16A/16B repair branch
-> second 15 Pandas Code Executor
-> 17 MongoDB Data Store
-> 18 Answer Prompt Builder
-> Answer LLM
-> 19 Answer Response Builder
-> 20 Answer Message Adapter
-> Chat Output

parallel:
19 Answer Response Builder
-> 21 API Response Builder
-> API/Data Output
```

Web에서 중요한 차이:

- `18 MongoDB Data Store`가 pandas 직후 `runtime_sources` 원본 rows와 `analysis.rows` 결과 rows를 `MONGODB_RESULT_COLLECTION`에 저장하고 preview row와 `data_ref`로 축약한다.
- metadata QA flow가 `direct_response_ready=true`를 만든 질문은 데이터 retrieval/pandas 저장 대상이 아니다.
- `metadata_route.target_dataset`은 dataset 설명/쿼리/활용 예시 같은 metadata QA에서만 쓰는 대상 포인터다. 일반 분석 질문에서 조회할 dataset 목록은 intent plan이 별도로 결정한다.
- 사용자는 dataset key를 몰라도 된다. `생산량 데이터 조회 쿼리 알려줘` 같은 표현은 `domain_items.quantity_terms`의 alias와 dataset mapping을 통해 대표 dataset으로 해석한다.
- `20 Answer Response Builder`의 `payload_out`이 답변, 표, 적용 scope, next `state`를 만들며, `analysis.data_ref`를 `data.data_ref`와 `state.current_data.data_ref`로 이어받는다.
- `21 Answer Message Adapter`는 Langflow Playground/Chat Output용 Markdown message만 만든다. Web API의 표준 JSON으로 파싱하지 않는다.
- Web backend는 선택된 subflow의 API response output을 표준 query response로 사용한다.
- Langflow Run API가 text/message 포트만 반환하는 운영 방식이면 API message의 JSON 문자열을 파싱한다.
- `12` node는 새 비즈니스 로직을 만들지 않고 `10.payload_out`의 projection만 수행한다.

Web/API query 입력:

```json
{
  "question": "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아줘",
  "session_id": "user-session-id"
}
```

선택된 subflow의 `00 ... Request Loader`가 만드는 내부 request payload:

```json
{
  "payload_version": "agent-v1",
  "status": "ok",
  "request": {
    "session_id": "user-session-id",
    "question": "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아줘",
    "timezone": "Asia/Seoul"
  },
  "state": {
    "chat_history": [],
    "context": {},
    "current_data": {}
  },
  "warnings": [],
  "errors": []
}
```

Web에서 노출할 main response shape:

```json
{
  "status": "ok",
  "answer_message": "...",
  "data": {
    "columns": [],
    "rows": [],
    "row_count": 0,
    "data_ref": {
      "store": "mongodb",
      "collection_name": "agent_v3_result_store",
      "ref_id": "..."
    }
  },
  "applied_scope": {
    "intent_type": "multi_step_analysis",
    "analysis_kind": "rank_wip_then_join_production",
    "datasets": ["wip_today", "production_today"],
    "source_aliases": [],
    "filters_by_source": {},
    "params_by_source": {},
    "metadata_refs": {}
  },
  "intent_plan": {},
  "analysis": {
    "status": "ok",
    "safety_passed": true,
    "executed": true,
    "columns": [],
    "rows": [],
    "row_count": 0,
    "analysis_code": "",
    "errors": []
  },
  "state": {},
  "warnings": [],
  "errors": []
}
```

주의:

- `data.rows`는 전체 row가 아니라 preview일 수 있다. `row_count`와 `data_ref`를 함께 봐야 한다.
- 전체 row 다운로드/상세 보기가 필요하면 backend가 `MONGODB_RESULT_COLLECTION`에서 `data_ref.ref_id`로 조회하는 별도 endpoint를 둔다.
- 후속 질문을 위해 backend는 반환된 `state`를 session별로 저장한다.
- 다음 query 실행 시 저장된 compact `state`는 선택된 subflow 내부의 session state loader가 복원한다.
- 이전 결과 전체 rows가 필요한 follow-up이면 `data_analysis_flow`의 `04 Previous Result Restore Router`가 `05 MongoDB Data Loader` branch를 실행한다.

## 4. 현재 Metadata Authoring Flow 계약

세 authoring flow는 같은 패턴을 사용한다.

```text
00 Request Loader
-> 01 Text Refinement Prompt Builder
-> Gemini/LLM refinement
-> 02 Text Refinement Normalizer
-> 03 Authoring Prompt Builder
-> Gemini/LLM authoring JSON
-> 04 Authoring Result Normalizer
-> 05 Similarity Checker
-> 06 Review Prompt Builder
-> Gemini/LLM review
-> 07 Review Writer
-> 08 Authoring Response Builder
```

현재 authoring flow의 표준 web/API 응답은 별도 신규 adapter가 아니라 각 flow의 `08 ... Authoring Response Builder`가 만드는 `api_response`다. `message` output은 Chat Output/Playground 표시용이다.

Authoring flow 입력:

```json
{
  "raw_text": "W/B공정은 W/B1부터 W/B6까지야. 재공 수량은 WIP 컬럼을 합산해.",
  "duplicate_action": "ask"
}
```

Backend가 flow에 전달해야 하는 설정:

| Metadata type | Flow id | collection name input |
| --- | --- | --- |
| `domain` | `LANGFLOW_DOMAIN_AUTHORING_FLOW_ID` | `agent_v3_domain_items` |
| `table_catalog` | `LANGFLOW_TABLE_CATALOG_AUTHORING_FLOW_ID` | `agent_v3_table_catalog_items` |
| `main_flow_filter` | `LANGFLOW_MAIN_FILTER_AUTHORING_FLOW_ID` | `agent_v3_main_flow_filters` |

중요한 현재 기준:

- collection은 prefix 조합이 아니라 full collection name을 직접 넘긴다.
- `collection_prefix`는 legacy fallback으로만 생각하고 새 web 구현의 기본값으로 쓰지 않는다.
- `duplicate_action`은 `ask`, `merge`, `replace`, `skip`, `create_new` 중 하나다.
- 사용자가 중복 처리 action을 선택해 재실행할 때는 같은 `raw_text`와 선택한 `duplicate_action`을 flow에 다시 넘긴다.
- 가능하면 `00 Request Loader`, `05 Similarity Checker`, `07 Review Writer`에 같은 `duplicate_action` override를 넣어 화면 선택과 writer 동작이 어긋나지 않게 한다.

`08 ... Response Builder`의 `api_response` shape:

```json
{
  "status": "ok | skipped | error",
  "message": "사용자 표시 메시지",
  "metadata_type": "domain | table_catalog | main_flow_filter",
  "items": [],
  "existing_matches": [],
  "conflict_warnings": [],
  "review": {
    "ready_to_save": false,
    "supplement_requests": []
  },
  "write_result": {
    "status": "ok | skipped | error",
    "saved_count": 0,
    "saved_items": [],
    "errors": [],
    "skipped_reason": ""
  },
  "trace": {
    "raw_text": "...",
    "refined_text": "...",
    "duplicate_decision": {
      "action": "ask",
      "requires_user_choice": false
    }
  }
}
```

UI status는 다음처럼 해석한다.

| 조건 | Web 표시 상태 |
| --- | --- |
| `write_result.status == "ok"` | 저장 완료 |
| `write_result.status == "skipped"` and `review.supplement_requests` 있음 | 추가 정보 필요 |
| `existing_matches` 있음 또는 `trace.duplicate_decision.requires_user_choice == true` | 중복 선택 필요 |
| `conflict_warnings`만 있음 | 저장 결과와 함께 경고 표시 |
| `write_result.status == "error"` 또는 `errors` 있음 | 오류 |

`existing_matches` 또는 `duplicate_decision.requires_user_choice=true`가 있으면 저장 완료로 보여주면 안 된다. `duplicate_action=ask`는 안전 기본값이며, 중복 후보가 있을 때 저장을 막는 동작이 정상이다.

## 5. Metadata 저장 Schema

### 5.1 Domain

Collection: `agent_v3_domain_items`

Writer key: `section + key`

Main flow load 위치: `metadata.domain_items`

```json
{
  "_id": "domain:process_groups:DA",
  "section": "process_groups",
  "key": "DA",
  "status": "active",
  "payload": {
    "display_name": "D/A",
    "aliases": ["DA", "D/A"],
    "processes": ["D/A1", "D/A2"]
  }
}
```

허용 section 예:

- `process_groups`
- `product_terms`
- `quantity_terms`
- `metric_terms`
- `status_terms`
- `product_key_columns`

Authoring normalizer는 `count_distinct` 집계를 main/runtime에서 쓰기 쉬운 `nunique`로 정규화한다.

### 5.2 Table Catalog

Collection: `agent_v3_table_catalog_items`

Writer key: `dataset_key`

Main flow load 위치: `metadata.table_catalog.datasets`

```json
{
  "_id": "table_catalog:wip_today",
  "dataset_key": "wip_today",
  "status": "active",
  "payload": {
    "display_name": "WIP Today",
    "dataset_family": "wip",
    "date_scope": "current_day",
    "source_type": "oracle",
    "source_config": {
      "source_type": "oracle",
      "db_key": "PNT_RPT",
      "query_template": "SELECT WORK_DT, OPER_NAME, WIP FROM PKG_WIP_TODAY WHERE WORK_DT = {DATE}"
    },
    "required_params": ["DATE"],
    "required_param_mappings": {"DATE": ["WORK_DT"]},
    "filter_mappings": {"DATE": ["WORK_DT"], "OPER_NAME": ["OPER_NAME"]},
    "columns": ["WORK_DT", "OPER_NAME", "WIP"],
    "primary_quantity_column": "WIP"
  }
}
```

`source_type`별 최소 저장 정보:

| source_type | Required source_config |
| --- | --- |
| `oracle` | `db_key`, `query_template` |
| `h_api` | `api_url` |
| `datalake` | `query_template` |
| `goodocs` | `doc_id`, `sheet_name` |
| `dummy` | 운영용이 아니면 최소 `columns`, `dataset_family` |

주의:

- SQL은 source 조회에 필요한 `query_template`으로만 저장한다. DB password/token은 절대 metadata에 저장하지 않는다.
- `filter_mappings`의 key는 main flow filter key이고, value는 실제 dataset column 후보 목록이다.
- `DATE` 같은 filter key가 실제 column 목록에 없다는 이유만으로 막으면 안 된다. 실제 column은 value 쪽 `WORK_DT` 같은 이름이다.

### 5.3 Main Flow Filter

Collection: `agent_v3_main_flow_filters`

Writer key: `filter_key`

Main flow load 위치: `metadata.main_flow_filters`

```json
{
  "_id": "main_flow_filter:DATE",
  "filter_key": "DATE",
  "status": "active",
  "payload": {
    "display_name": "기준일",
    "aliases": ["오늘", "금일", "작업일"],
    "column_candidates": ["WORK_DT", "DATE", "BASE_DT"],
    "semantic_role": "date",
    "value_type": "date",
    "value_shape": "scalar",
    "operator": "eq",
    "normalized_format": "YYYYMMDD"
  }
}
```

저장 가능한 filter item의 최소 정보:

- `filter_key`
- `payload.aliases`
- `payload.column_candidates`
- `payload.semantic_role`

`value_type`, `value_shape`, `operator`가 누락되면 authoring normalizer가 보수적으로 `string`, `scalar`, `eq`를 기본값으로 넣는다.

## 6. 필요한 환경 변수

Web backend와 Langflow 운영 기준으로 아래 설정을 분리한다.

```env
# Langflow backend wrapper
LANGFLOW_BASE_URL=http://127.0.0.1:7860
LANGFLOW_API_KEY=
LANGFLOW_ROUTER_FLOW_ID=
LANGFLOW_DATA_ANALYSIS_FLOW_ID=
LANGFLOW_METADATA_QA_FLOW_ID=
LANGFLOW_REPORT_GENERATION_FLOW_ID=
LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID=
LANGFLOW_DOMAIN_AUTHORING_FLOW_ID=
LANGFLOW_TABLE_CATALOG_AUTHORING_FLOW_ID=
LANGFLOW_MAIN_FILTER_AUTHORING_FLOW_ID=

# LLM
LLM_PROVIDER=gemini
LLM_API_KEY=
LLM_MODEL_NAME=
LLM_TEMPERATURE=0
LLM_TIMEOUT_SECONDS=60

# MongoDB metadata and result store
MONGODB_URI=
MONGODB_DATABASE=metadata_driven_agent_v3
MONGODB_DOMAIN_COLLECTION=agent_v3_domain_items
MONGODB_TABLE_CATALOG_COLLECTION=agent_v3_table_catalog_items
MONGODB_MAIN_FLOW_FILTER_COLLECTION=agent_v3_main_flow_filters
MONGODB_RESULT_COLLECTION=agent_v3_result_store

# Source retrieval
RUN_LIVE_SOURCE_RETRIEVAL=false
ORACLE_CONFIG_JSON=
H_API_TOKEN=
LAKEHOUSE_USER_ID=
LAKEHOUSE_TOKEN=
LAKEHOUSE_S3_ACCESS_KEY=
LAKEHOUSE_S3_SECRET_KEY=
GOODOCS_USER_ID=
GOODOCS_TOKEN_SOURCE=
GOODOCS_TOKEN_KEY=
GOODOCS_MODULE_NAME=
SOURCE_FETCH_LIMIT=5000

# Web-owned storage
WEB_SESSION_STORE=mongodb
WEB_PENDING_AUTHORING_COLLECTION=agent_v3_pending_authoring
```

`web_app.langflow_client`는 `LANGFLOW_BASE_URL + *_FLOW_ID`로 `/api/v1/run/{flow_id}` URL을 만들고, 이미 wrapper URL이 있으면 `LANGFLOW_ROUTER_API_URL`, `LANGFLOW_DATA_ANALYSIS_API_URL`, `LANGFLOW_METADATA_QA_API_URL`, `LANGFLOW_DOMAIN_AUTHORING_API_URL`, `LANGFLOW_TABLE_CATALOG_AUTHORING_API_URL`, `LANGFLOW_MAIN_FILTER_AUTHORING_API_URL`을 우선 사용한다.

`MONGODB_RESULT_COLLECTION`은 metadata가 아니라 query result row 저장소다. `18 MongoDB Data Store`는 pandas 직후 source rows와 result rows를 저장한다. 다음 turn에서는 compact state를 그대로 넘기는 것이 기본이며, optional first `01 MongoDB Data Loader`는 이전 state에 `data_ref`만 있고 preview/summary가 없을 때 사용한다. 이전 결과 전체 rows가 필요한 후속 분석은 data analysis flow의 “이전 결과 복원” 브랜치에서 MongoDB loader를 실행한다.

## 7. 화면 구성

### 7.1 질의/분석 화면

필수 UI:

- 질문 입력창
- session 선택 또는 새 대화 시작
- 실행 버튼
- 최종 답변 영역
- 결과 table 영역
- 사용 dataset/source alias 영역
- 적용 filter/param 영역
- 의도 분석 요약 영역
- pandas 처리 요약과 code 접기 영역
- 오류/경고 영역
- 전체 row 다운로드 또는 상세 보기 버튼

표시 필드:

- `answer_message`
- `data.columns`
- `data.rows`
- `data.row_count`
- `data.data_ref`
- `applied_scope.datasets`
- `applied_scope.source_aliases`
- `applied_scope.filters_by_source`
- `applied_scope.params_by_source`
- `intent_plan.intent_type`
- `intent_plan.analysis_kind`
- `intent_plan.step_plan`
- `intent_plan.retrieval_jobs`
- `analysis.status`
- `analysis.safety_passed`
- `analysis.executed`
- `analysis.analysis_code` 또는 `analysis.pandas_code_json.code`
- `analysis.errors`

기본 정책:

- pandas code는 기본 접힘 상태로 둔다.
- `data_ref`는 사용자가 직접 수정할 값이 아니라 전체 결과 로딩/다운로드용 참조로만 쓴다.
- 후속 질문을 위해 `state`는 backend session store에 저장한다.

### 7.2 Metadata 등록 허브

탭은 세 개로 나눈다.

- Domain 용어/규칙 등록
- Table catalog 데이터셋 등록
- Main flow filter/parameter 등록

공통 필수 UI:

- 자연어 설명 입력창
- 예시 문장 선택 버튼
- 저장 방식 선택
- 실행 버튼
- 정제된 설명 표시
- 생성 후보 item 표시
- 부족한 정보 표시
- 비슷한 기존 정보 표시
- 충돌/경고 표시
- 저장 결과 표시
- 고급 JSON 보기 접기 영역

저장 방식 문구:

| 내부 action | 화면 문구 | 의미 |
| --- | --- | --- |
| `ask` | 먼저 확인 | 같은 key나 강한 유사 항목이 있으면 저장하지 않고 선택 요구 |
| `merge` | 기존 내용 보강 | 기존 doc과 새 payload를 deep merge |
| `replace` | 기존 내용 교체 | 같은 key의 기존 doc을 새 item으로 교체 |
| `skip` | 저장하지 않음 | 이번 입력을 저장하지 않음 |
| `create_new` | 새 key로 등록 | 기존 key와 다를 때만 신규 저장 |

기본값은 반드시 `ask`로 둔다.

### 7.3 중복/유사 정보 처리 화면

필수 UI:

- 새 입력으로 생성된 item
- 비슷한 기존 item
- `existing_matches.reason` 또는 `conflict_warnings.reason`
- 추천 action이 있으면 표시
- 선택 버튼: 보강, 교체, 저장 안 함, 새 key로 저장
- 새 key 입력창
- 선택 action으로 재실행 버튼

Backend 처리:

1. 첫 실행은 `duplicate_action=ask`.
2. 응답에 `existing_matches`, `conflict_warnings`, `trace.duplicate_decision.requires_user_choice=true`가 있으면 pending record 저장.
3. 사용자가 action을 선택하면 같은 `raw_text`와 선택 action으로 같은 authoring flow를 재호출.
4. 저장 성공 후 pending record를 완료 처리.

### 7.4 Metadata 조회/검토 화면

필수 UI:

- metadata type 필터: `domain`, `table_catalog`, `main_flow_filter`
- key 검색
- alias 검색
- dataset family/source type 검색
- active/inactive 상태 필터
- 상세 보기
- JSON 보기
- 자연어로 수정 요청 버튼

일반 사용자는 직접 JSON 수정 버튼 대신 자연어 수정 요청을 사용한다. Backend는 기존 metadata 요약을 자연어 등록 화면의 context로 넘기고, 실제 저장은 authoring flow를 통해 수행한다.

### 7.5 등록 후 검증 화면

필수 UI:

- smoke question 목록
- 직접 질문 입력
- 실행 버튼
- 성공/실패 표시
- 기대 dataset/filter 표시
- 실제 `applied_scope.datasets`, `filters_by_source`, `params_by_source`
- 결과 row count
- 오류 메시지

검증 질문 범주:

- 방금 추가한 domain 용어가 intent에 반영되는 질문
- 방금 추가한 dataset이 선택되는 질문
- 방금 추가한 filter가 retrieval/pandas 조건으로 적용되는 질문
- 중복 metadata가 agent 판단을 흐리지 않는지 확인하는 질문
- 후속 질문에서 이전 `state.current_data`를 재사용하는 질문

## 8. Backend API 설계

권장 endpoint:

| Method | Path | 역할 |
| --- | --- | --- |
| `GET` | `/api/health` | Web, Langflow, MongoDB, result store 연결 상태 확인 |
| `POST` | `/api/query` | main query/analysis flow 실행 |
| `GET` | `/api/query/{query_id}/rows` | `data_ref` 기반 전체 row 조회 또는 다운로드 |
| `GET` | `/api/sessions/{session_id}` | session state 조회 |
| `DELETE` | `/api/sessions/{session_id}` | session 초기화 |
| `POST` | `/api/metadata/domain/run` | domain authoring flow 실행 |
| `POST` | `/api/metadata/table-catalog/run` | table catalog authoring flow 실행 |
| `POST` | `/api/metadata/main-filter/run` | main flow filter authoring flow 실행 |
| `GET` | `/api/metadata/{type}` | metadata 검색 |
| `GET` | `/api/metadata/{type}/{key}` | metadata 상세 조회 |
| `POST` | `/api/metadata/{type}/validate` | 저장 후 main flow smoke 검증 |
| `GET` | `/api/metadata/pending/{pending_id}` | 중복 선택 pending record 조회 |
| `DELETE` | `/api/metadata/pending/{pending_id}` | pending record 취소 |

### 8.1 `/api/query` request

```json
{
  "session_id": "user-session-id",
  "question": "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아줘"
}
```

Backend 처리:

1. `session_id`로 이전 `state` 조회.
2. Langflow router flow 호출 후 선택된 subflow 호출.
3. selected subflow의 compacted `api_response` payload를 읽는다.
4. 응답의 `state`를 session store에 저장.
5. 화면용 response 반환.

### 8.2 `/api/metadata/{type}/run` request

```json
{
  "raw_text": "wip_today는 Oracle PNT_RPT에서 SELECT WORK_DT, OPER_NAME, WIP FROM PKG_WIP_TODAY WHERE WORK_DT = {DATE}로 조회해. DATE는 WORK_DT에 매핑해.",
  "duplicate_action": "ask",
  "pending_authoring_id": null
}
```

Backend 처리:

1. `type`에 맞는 Langflow authoring flow id 선택.
2. full collection name과 MongoDB 설정을 flow input 또는 노드 입력값 설정으로 주입.
3. `08 ... Response Builder.api_response`를 읽는다.
4. 중복 선택이 필요하면 pending record를 저장하고 `pending_authoring_id`를 response에 덧붙인다.
5. 저장 성공이면 등록 후 검증 화면에서 실행할 smoke question 후보를 생성한다.

### 8.3 Authoring response normalization

Backend는 Langflow `api_response`를 거의 그대로 전달하되, 화면 상태 계산 필드를 추가해도 된다.

```json
{
  "ui_status": "saved | needs_more_input | duplicate_choice_required | warning | error",
  "status": "skipped",
  "message": "...",
  "metadata_type": "table_catalog",
  "items": [],
  "existing_matches": [],
  "conflict_warnings": [],
  "review": {},
  "write_result": {},
  "trace": {},
  "pending_authoring_id": "optional"
}
```

`ui_status`는 backend 편의 필드다. Langflow flow 자체의 기본 status 값은 `ok`, `skipped`, `error`를 유지한다.

## 9. Langflow Run API 호출 시 입력 매핑

Langflow Run API wrapper는 flow별 parser와 노드 입력값 설정 builder를 분리한다.

Query runtime에서 기본 전달 값:

- `input_value`: 사용자 질문 text
- `session_id`: 웹/API 대화별 session id
- router flow 노드 입력값 설정: 기본적으로 없음
- selected subflow 노드 입력값 설정: 필요할 때만 `00 ... Request Loader.state`

Langflow canvas의 request loader에는 별도 `Session ID` 또는 `Router Payload` 입력을 연결하지 않는다. session id는 Langflow Run API payload의 `session_id`와 message/payload 내부 값에서 자동 추론한다.

MongoDB URI/database/collection override는 운영에서는 env를 우선 사용한다. 특정 Langflow deployment에서 env를 쓸 수 없을 때만 metadata loader, result store, session state loader/writer의 advanced Mongo 입력을 노드 입력값 설정으로 넣는다.

Authoring flow에 전달할 값:

- `00 ... Authoring Request Loader.raw_text`
- `00 ... Authoring Request Loader.mongo_uri`
- `00 ... Authoring Request Loader.mongo_database`
- `00 ... Authoring Request Loader.collection_name`
- `00 ... Authoring Request Loader.duplicate_action`
- `05 ... Similarity Checker.duplicate_action` if exposed
- `07 ... Review Writer.mongo_uri`
- `07 ... Review Writer.duplicate_action`

Parsing 원칙:

- Query flow: selected subflow의 `api_response`를 우선 사용한다. 이 payload는 답변, preview data, `data_ref`, state만 projection한 상태다.
- Authoring flow: `08 ... Response Builder.api_response`만 사용한다.
- `21 Answer Message Adapter.message`와 authoring `message`는 사람이 보는 Markdown/text다. JSON 계약으로 파싱하지 않는다.
- Langflow wrapper가 response를 여러 겹 감싸더라도 backend parser는 대상 output name을 찾아 꺼낸다.

## 10. Pending Authoring 저장

중복 선택이 필요한 경우 backend가 pending record를 저장한다.

```json
{
  "_id": "pending_authoring_id",
  "metadata_type": "domain",
  "raw_text": "...",
  "last_response": {},
  "created_by": "user id",
  "created_at": "ISO datetime",
  "expires_at": "ISO datetime"
}
```

보관 기간은 1~7일 정도가 적당하다.

Pending record에 저장하지 않을 값:

- MongoDB URI
- Langflow API key
- LLM API key
- Oracle/H-API/Datalake/Goodocs credential
- full source rows

## 11. 권한

권장 역할:

| Role | 가능 작업 |
| --- | --- |
| Viewer | 질의/분석 실행, metadata 조회 |
| Editor | 자연어 metadata 등록 요청, 등록 후 검증 실행 |
| Approver | 중복 처리 선택, 저장 승인 |
| Admin | flow id, collection name, 권한, 배포 설정 관리 |

운영 초기에는 `Editor`와 `Approver`를 분리하는 것이 안전하다.

## 12. 구현 순서

1. Backend health check와 Langflow Run API wrapper 구현
2. router/subflow output에서 compacted payload를 꺼내는 parser 구현
3. `/api/query`와 session state store 구현
4. result `data_ref` 기반 전체 row 조회 endpoint 구현
5. 질의/분석 화면 구현
6. authoring flow별 `api_response` parser 구현
7. `/api/metadata/{type}/run` 공통 handler 구현
8. Metadata 등록 허브 화면 구현
9. 중복/유사 정보 선택 화면과 pending store 구현
10. Metadata 조회/검색 화면 구현
11. 등록 후 검증 화면 구현
12. 권한, 감사 로그, 운영 배포 설정 추가

## 13. 완료 기준

### 질의/분석 화면

- 사용자가 질문을 입력하면 답변과 table preview를 한 화면에서 확인할 수 있다.
- `row_count`와 preview row가 구분된다.
- 전체 결과가 필요하면 `data_ref`로 전체 row를 불러올 수 있다.
- 사용 dataset, source alias, 적용 filter/param을 볼 수 있다.
- 후속 질문에서 이전 결과를 참조할 수 있다.

### Metadata 등록 화면

- 사용자가 JSON 없이 자연어로 입력할 수 있다.
- 부족한 정보가 있으면 저장되지 않고 한국어로 안내된다.
- 비슷한 기존 정보가 있으면 저장되지 않고 선택지가 표시된다.
- 저장 성공 시 저장된 key와 count가 표시된다.
- `api_response.trace.refined_text`는 고급 접기 영역에서만 표시한다.

### Metadata 검증 화면

- 등록 직후 smoke 질문을 실행할 수 있다.
- 기대 dataset/filter와 실제 `applied_scope`를 비교할 수 있다.
- 실패 시 intent, retrieval, pandas, answer 중 어느 단계에서 실패했는지 볼 수 있다.

## 14. 구현 시 주의사항

- 일반 metadata 저장은 authoring flow를 통해서만 수행한다.
- Web backend의 MongoDB 직접 write는 관리자용 예외 또는 pending/session/result store에 한정한다.
- metadata collection과 result row collection을 섞지 않는다.
- table catalog metadata에는 credential을 저장하지 않는다. `db_key`, `doc_id`, endpoint id 같은 참조만 저장한다.
- source credential은 backend secret store 또는 배포 환경변수로 관리한다.
- `RUN_LIVE_SOURCE_RETRIEVAL=false` 상태에서는 deterministic dummy rows를 사용하되, `source_type` 경계는 유지된다.
- Browser에는 Langflow response payload 전체를 그대로 노출하지 않는다.
- 오류 메시지는 사용자 메시지와 기술 로그를 분리한다.
- `state`, `current_data`, `followup_source_results`, `data_ref`는 session store에 유지한다.
- full prompt, raw source rows, MongoDB URI는 화면 response와 pending record에서 제외한다.

## 15. Web 검증 체크리스트

- router flow와 selected subflow가 정상 호출되는가
- selected subflow `api_response`의 compacted payload를 JSON으로 받을 수 있는가
- text/message 포트만 받을 때 `12.api_message` JSON 문자열 fallback을 파싱하는가
- `21 Answer Message Adapter.message`를 API JSON으로 오인하지 않는가
- session별 follow-up 질문이 유지되는가
- `state.current_data.data_ref`가 다음 질문 전에 preview/summary로 복원되고, full rows가 초반 payload에 불필요하게 붙지 않는가
- `MONGODB_RESULT_COLLECTION`에 큰 row가 저장되고 전체 row 조회가 되는가
- domain authoring에서 `count_distinct`가 `nunique`로 정규화되는가
- table catalog authoring에서 source 필수 정보 누락 시 저장이 차단되는가
- main flow filter authoring에서 alias/column 중복 경고가 표시되는가
- `duplicate_action=ask`일 때 저장 완료로 오인하지 않는가
- `duplicate_action=merge/replace` 선택 후 저장 결과가 표시되는가
- 저장 후 main flow metadata loader가 새 metadata를 읽는가
- authoring flow의 `08 ... Response Builder.api_response`를 화면 계약으로 사용하고 있는가
- Browser에 secret이 노출되지 않는가




