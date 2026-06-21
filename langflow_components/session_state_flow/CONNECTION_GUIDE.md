# Session State Flow Connection Guide

session state flow는 대화별 compact state를 MongoDB에서 읽고 다시 저장하기 위한 공통 부품입니다. main router가 아니라 각 subflow 내부에 두는 것을 기본으로 합니다.

## Why It Exists

Langflow의 기본 message history만으로는 분리된 flow API 호출, API 서버 재시작, 큰 결과 row reference를 안정적으로 이어가기 어렵습니다. 그래서 session state collection에는 full rows를 저장하지 않고, 다음 turn에 필요한 요약만 저장합니다.

저장되는 주요 값은 다음과 같습니다.

| State field | Meaning |
| --- | --- |
| `chat_history` | 최근 대화 요약 |
| `context` | 마지막 route/analysis kind 등 작은 context |
| `current_data` | 결과 columns, preview rows, row_count, data_ref, product key summary |
| `followup_source_results` | 이전 조회 source별 data_ref와 요약 |
| `runtime_source_refs` | source alias별 원본 row reference |

full rows는 `data_analysis_flow`의 result store에 `data_ref`로 저장됩니다.

## Minimal Subflow Pattern

```text
Chat Input.Chat Message
  -> 00 MongoDB Session State Loader.Question
  -> 00 Request Loader.Question

00 MongoDB Session State Loader.Loaded State
  -> 00 Request Loader.Previous State

Final API Response
  -> 01 MongoDB Session State Writer.Response Payload
```

main router flow에는 session state loader/writer를 두지 않는 것을 권장합니다. main router는 분기만 하고, 선택된 subflow가 자기 session state를 직접 load/write합니다.

## Loader Inputs

| Input | Typical value |
| --- | --- |
| `Question` | `Chat Input.Chat Message` 또는 flow API가 넘긴 text/message |
| `Mongo URI` | 비워두면 `MONGODB_URI` 또는 `MONGO_URI` 사용 |
| `Mongo Database` | 기본 `metadata_driven_agent_v3` |
| `Session State Collection` | 기본 `agent_v3_session_states` |
| `Enabled` | 기본 `true` |
| `Preview Row Limit` | 기본 `5` |

별도 `Session ID` 포트는 제거했습니다. loader는 `Question` message의 `session_id`, `conversation_id`, `chat_id` 또는 state 안의 session id를 자동으로 찾습니다. 없으면 단독 테스트용 `demo-session` fallback을 사용합니다.

## Loader Outputs

| Output | Connect to |
| --- | --- |
| `Loaded State` | subflow의 `00 Request Loader.Previous State` |

## Writer Inputs

| Input | Typical value |
| --- | --- |
| `Response Payload` | subflow의 final API/Data response |
| `Mongo URI` | loader와 동일 |
| `Mongo Database` | loader와 동일 |
| `Session State Collection` | loader와 동일 |
| `Enabled` | 기본 `true` |
| `Preview Row Limit` | 기본 `5` |
| `History Limit` | 기본 `10` |

별도 `Session ID` 포트는 제거했습니다. writer는 `Response Payload.request.session_id` 또는 `Response Payload.api_response.request.session_id`를 사용합니다.

## Stored Document Shape

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

## Environment

```powershell
$env:MONGODB_URI="mongodb://user:password@host:27017"
$env:MONGODB_DATABASE="metadata_driven_agent_v3"
$env:MONGODB_SESSION_STATE_COLLECTION="agent_v3_session_states"
$env:SESSION_STATE_PREVIEW_ROW_LIMIT="5"
$env:SESSION_STATE_HISTORY_LIMIT="10"
```
