# Langflow Node Connection Guide Index

현재 권장 구조는 main router가 질문 유형을 분류하고, `06 Run Flow Text Switch`가 목적별 하위 Run Flow 하나에만 질문 text를 전달한 뒤, `07 Selected Run Flow Message Merger`가 실행된 Run Flow의 message 하나만 Chat Output으로 넘기는 방식입니다.

먼저 읽을 문서:

| Guide | When to read |
| --- | --- |
| `docs/ROUTED_RUN_FLOW_SESSION_WIRING_GUIDE.md` | main router, Run Flow, session state 연결 전체 그림 |
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
-> router_flow 00~07
-> selected Run Flow
-> 07 Selected Run Flow Message Merger
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
- session id는 별도 포트로 연결하지 않고 Chat/Run Flow message 또는 final API response에서 자동 추론합니다.
- main router는 subflow payload를 조립하지 않습니다.
- Run Flow는 text input만 받으므로 `06 Run Flow Text Switch`에서 선택된 branch 하나에만 질문 text를 전달합니다.
- Chat Output은 입력을 하나만 받으므로 `07 Selected Run Flow Message Merger`에서 선택된 Run Flow message 하나만 전달합니다.
- 선택되지 않은 Run Flow는 실행되지 않아야 합니다.
- custom component는 standalone 파일로 동작해야 하며 sibling helper import를 사용하지 않습니다.
- input 이름과 output 이름이 같은 component 안에서 겹치지 않게 합니다.
