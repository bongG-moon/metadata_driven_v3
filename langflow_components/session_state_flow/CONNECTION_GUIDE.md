# Session State Flow Connection Guide

## Why MongoDB

후속분석 state는 기본 Langflow Message History보다 MongoDB session state store를 권장합니다.

- `data_analysis_flow`는 source/result rows를 이미 MongoDB result store에 `data_ref`로 저장합니다.
- session state에는 full rows가 아니라 `data_ref`, `row_count`, `columns`, preview rows, product key summary, `followup_source_results`만 있으면 됩니다.
- backend orchestrator, web app, Langflow subflow를 분리해도 `session_id` 기준으로 같은 state를 다시 주입할 수 있습니다.
- Langflow 기본 Memory는 단일 canvas 내부 대화에는 편하지만, 분리된 router/subflow 구조나 API 서버 재시작 이후 복원에는 약합니다.

## Recommended Runtime Wiring

```text
User/API request
-> 00 MongoDB Session State Loader
-> router_flow
-> backend orchestrator
-> selected flow
   -> metadata_qa_flow
   -> data_analysis_flow
   -> report_generation_flow
   -> operations_diagnosis_flow
-> 01 MongoDB Session State Writer
-> API/Web response
```

## Loader

`00 MongoDB Session State Loader`는 `session_id`로 이전 compact state를 읽습니다.

Inputs:

- `question`: 현재 사용자 질문
- `session_id`: 대화 세션 키. Web/API 실행에서는 backend가 자동 주입합니다. Langflow 단독 테스트에서만 같은 값을 직접 넣습니다.
- `mongo_uri`: 비워두면 `MONGODB_URI` 또는 `MONGO_URI`를 사용합니다.
- `mongo_database`: 기본 `metadata_driven_agent_v3`
- `session_collection_name`: 기본 `agent_v3_session_states`
- `preview_row_limit`: state 안의 preview rows 최대 개수

Outputs:

- `payload`: router 또는 request loader에 넘길 수 있는 request payload
- `loaded_state`: 기존 `00 Router Request Loader.state` 또는 `00 Analysis Request Loader.state`에 연결할 수 있는 compact state

## Writer

`01 MongoDB Session State Writer`는 최종 flow 응답의 `state`를 compact해서 저장합니다.

Inputs:

- `response_payload`: selected flow의 final/API response payload
- `session_id`: API response wrapper처럼 request 정보가 없는 payload를 저장할 때 사용
- `mongo_uri`, `mongo_database`, `session_collection_name`: loader와 동일
- `preview_row_limit`: state 안에 남길 preview rows 개수
- `history_limit`: `chat_history` 보존 개수

Stored document:

```json
{
  "_id": "session_state:<session_id>",
  "session_id": "<session_id>",
  "state_version": "agent-v1",
  "state": {
    "chat_history": [],
    "context": {},
    "current_data": {
      "columns": [],
      "rows": [],
      "row_count": 0,
      "data_ref": {},
      "product_key_columns": [],
      "product_key_values": []
    },
    "followup_source_results": [],
    "runtime_source_refs": {}
  },
  "last_question": "",
  "last_response_type": "analysis",
  "turn_count": 1,
  "updated_at": "..."
}
```

## Important Policy

Full rows are not stored in the session state collection. Full previous rows stay in `MONGODB_RESULT_COLLECTION` through `data_ref`.

For a follow-up like `이때 상세 device별로 알려줄래?`, the session state loader restores the compact state first. Then `data_analysis_flow` decides whether it needs full previous rows:

- product-key follow-up: use `state.current_data.product_key_values`, no full restore
- previous-result recalculation/detail: `03 Intent Plan Normalizer` sets `previous_result_restore_mode=full`
- `04 Previous Result Restore Router` conditionally calls `05 MongoDB Data Loader`

## Web/API Environment

The web API client also supports the same MongoDB session state collection.

```powershell
$env:WEB_SESSION_STORE="mongodb"
$env:MONGODB_URI="mongodb://user:password@host:27017"
$env:MONGODB_DATABASE="metadata_driven_agent_v3"
$env:MONGODB_SESSION_STATE_COLLECTION="agent_v3_session_states"
$env:SESSION_STATE_PREVIEW_ROW_LIMIT="5"
$env:SESSION_STATE_HISTORY_LIMIT="10"
```

If `state` is explicitly passed to `LangflowApiClient.run_query`, the web/API client uses that state first. If `state=None`, the client loads state by `session_id` and saves the response state after the call.
