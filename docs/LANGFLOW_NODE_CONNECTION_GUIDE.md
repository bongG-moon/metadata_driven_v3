# Langflow Node Connection Guide Index

현재 권장 구조는 main router가 질문 유형을 분류하고, `05 Orchestrator Response Builder`가 선택된 하위 flow의 `api_url + input_value` 실행 요청을 만든 뒤, `06 Selected Flow API Runner`가 그 API 하나만 호출해 message 하나를 Chat Output으로 넘기는 방식입니다.

먼저 읽을 문서:

| Guide | When to read |
| --- | --- |
| `docs/ROUTED_RUN_FLOW_SESSION_WIRING_GUIDE.md` | main router, 하위 flow API, session state 연결 전체 그림 |
| `langflow_components/router_flow/CONNECTION_GUIDE.md` | main router canvas를 만들 때 |
| `langflow_components/data_analysis_flow/CONNECTION_GUIDE.md` | 실제 데이터 조회/분석 flow를 만들 때 |
| `langflow_components/metadata_qa_flow/CONNECTION_GUIDE.md` | metadata/catalog/help 답변 flow를 만들 때 |
| `langflow_components/report_generation_flow/CONNECTION_GUIDE.md` | 리포트 생성 branch를 붙일 때 |
| `langflow_components/operations_diagnosis_flow/CONNECTION_GUIDE.md` | 운영 진단 branch를 붙일 때 |
| `langflow_components/session_state_flow/CONNECTION_GUIDE.md` | 대화별 state load/write를 연결할 때 |

## Common Runtime Rule

main router flow:

```text
Chat Input
-> router_flow 00~05
-> 06 Selected Flow API Runner
-> Chat Output
```

subflow:

```text
Chat Input
-> 00 MongoDB Session State Loader
-> 00 Request Loader
-> subflow logic
-> Final API Response
-> 01 MongoDB Session State Writer

Final Message
-> Chat Output
```

## Common Component Rules

- 하위 flow의 00 request loader는 `Question`과 `Previous State`만 직접 연결합니다.
- session id는 별도 포트로 연결하지 않고 Chat/API message 또는 final API response에서 자동 추론합니다.
- main router는 subflow payload를 조립하지 않습니다.
- main router의 `05 Route Response`는 `subflow_call.api_url`, `subflow_call.input_value`, `subflow_call.session_id`만 준비합니다.
- direct router canvas에서는 여러 native Run Flow output을 한 노드에 모으지 않습니다. 이 구조는 선택되지 않은 branch까지 기다릴 수 있습니다.
- `06 Selected Flow API Runner`는 `subflow_call`에 적힌 selected flow API 하나만 호출하고 `Message` 하나만 Chat Output으로 전달합니다.
- custom component는 standalone 파일로 동작해야 하며 sibling helper import를 사용하지 않습니다.
- input 이름과 output 이름이 같은 component 안에서 겹치지 않게 합니다.
