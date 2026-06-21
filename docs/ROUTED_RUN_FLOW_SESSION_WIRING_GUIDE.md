# Routed Run Flow + Session State Wiring Guide

이 문서는 main router flow와 하위 Run Flow를 연결하는 기준입니다. 현재 권장 구조는 단순합니다.

```text
main router flow
Chat Input
-> router_flow 00~07
-> selected Run Flow
-> Chat Output
```

각 subflow는 독립 실행 가능한 flow로 둡니다.

```text
subflow
Chat Input
-> 00 MongoDB Session State Loader
-> 00 Request Loader
-> subflow logic
-> Final API Response
-> 01 MongoDB Session State Writer

Final Message
-> Chat Output
```

main flow는 state, metadata route, router payload, session id를 조립하지 않습니다. main flow는 질문을 분류하고 선택된 Run Flow에 원래 사용자 질문 text만 넘깁니다.

## Main Router Connections

```text
Chat Input.Chat Message
  -> 00 Router Request Loader.Question

00 Router Request Loader.Payload
  -> 01 Metadata Context Loader.Payload

01 Metadata Context Loader.Payload
  -> 02 Route Candidate Builder.Payload

02 Route Candidate Builder.Payload
  -> 03 Route Classifier Prompt Builder.Payload

03 Route Classifier Prompt Builder.Route Prompt
  -> Route Classifier LLM.Input

02 Route Candidate Builder.Payload
  -> 04 Route Classifier Normalizer.Payload

Route Classifier LLM.Output
  -> 04 Route Classifier Normalizer.Route LLM Response

04 Route Classifier Normalizer.Payload
  -> 05 Orchestrator Response Builder.Payload

05 Orchestrator Response Builder.Route Response
  -> 06 Run Flow Text Switch.Route Response
```

Run Flow node는 text/message input만 받을 수 있으므로 `05.Route Response`를 Run Flow에 직접 연결하지 않습니다. `06 Run Flow Text Switch`가 `selected_flow`를 보고 선택된 branch 하나에만 질문 text를 내보냅니다.

Chat Output은 입력을 하나만 받을 수 있으므로 여러 Run Flow output을 직접 연결하지 않습니다. `07 Selected Run Flow Message Merger`가 선택된 Run Flow message 하나만 Chat Output으로 넘깁니다.

| `selected_flow` | Run Flow target |
| --- | --- |
| `metadata_qa_flow` | Metadata QA Flow |
| `data_analysis_flow` | Data Analysis Flow |
| `report_generation_flow` | Report Generation Flow |
| `operations_diagnosis_flow` | Operations Diagnosis Flow |

각 branch에서는 `06`의 해당 text output을 Run Flow input에 연결합니다.

```text
06 Run Flow Text Switch.Metadata QA Text
  -> Metadata QA Run Flow input

06 Run Flow Text Switch.Data Analysis Text
  -> Data Analysis Run Flow input

06 Run Flow Text Switch.Report Generation Text
  -> Report Generation Run Flow input

06 Run Flow Text Switch.Operations Diagnosis Text
  -> Operations Diagnosis Run Flow input
```

skip은 각 subflow 안에서 처리하지 않습니다. `06 Run Flow Text Switch`가 선택되지 않은 output을 `stop()` 처리하므로 선택된 Run Flow 하나만 실행되어야 합니다.

Run Flow 출력은 `07`로 모읍니다.

```text
05 Orchestrator Response Builder.Route Response
  -> 07 Selected Run Flow Message Merger.Route Response

Metadata QA Run Flow output
  -> 07 Selected Run Flow Message Merger.Metadata QA Output

Data Analysis Run Flow output
  -> 07 Selected Run Flow Message Merger.Data Analysis Output

Report Generation Run Flow output
  -> 07 Selected Run Flow Message Merger.Report Generation Output

Operations Diagnosis Run Flow output
  -> 07 Selected Run Flow Message Merger.Operations Diagnosis Output

07 Selected Run Flow Message Merger.Message
  -> Chat Output
```

## Subflow Standard Connections

모든 subflow의 시작부는 같은 패턴입니다.

```text
Chat Input.Chat Message
  -> 00 MongoDB Session State Loader.Question
  -> 00 Request Loader.Question

00 MongoDB Session State Loader.Loaded State
  -> 00 Request Loader.Previous State
```

모든 subflow의 종료부도 같은 패턴입니다.

```text
Final API Response
  -> 01 MongoDB Session State Writer.Response Payload

Final Message
  -> Chat Output
```

## Flow-Specific Ports

| Subflow | First loader | Previous state input | Final API response | Final human message |
| --- | --- | --- | --- | --- |
| `metadata_qa_flow` | `00 Metadata QA Request Loader.Question` | `00 Metadata QA Request Loader.Previous State` | `04 Metadata QA API Response Builder.API Response` | `03 Metadata QA Message Adapter.Message` |
| `data_analysis_flow` | `00 Analysis Request Loader.Question` | `00 Analysis Request Loader.Previous State` | `21 API Response Builder.API Response` | `20 Answer Message Adapter.Message` |
| `report_generation_flow` | `00 Report Request Loader.Question` | `00 Report Request Loader.Previous State` | `03 Report Response Builder.API Response` | `03 Report Response Builder.Message` |
| `operations_diagnosis_flow` | `00 Diagnosis Request Loader.Question` | `00 Diagnosis Request Loader.Previous State` | `03 Diagnosis Response Builder.API Response` | `03 Diagnosis Response Builder.Message` |

## Session Id

별도 `Session ID` 포트는 request loader와 session loader/writer에서 제거했습니다. Langflow API payload의 `session_id`가 Chat/Run Flow message에 포함되면 컴포넌트가 자동으로 읽습니다. 응답 저장 시에는 final API response의 `request.session_id`를 사용합니다.

단독 테스트에서 message에 session id가 없으면 `demo-session` fallback이 사용됩니다.

## Adding A New Routed Flow

1. 새 subflow가 질문 하나만 받아 독립 실행되도록 만듭니다.
2. 필요하면 subflow 내부에 session state loader/writer를 둡니다.
3. `router_flow/02_route_candidate_builder.py`에 새 route hint를 추가합니다.
4. `router_flow/03_route_classifier_prompt_builder.py`의 route 설명에 새 route를 추가합니다.
5. `router_flow/04_route_classifier_normalizer.py`의 허용 route에 새 route를 추가합니다.
6. `router_flow/05_orchestrator_response_builder.py`의 `FLOW_BY_ROUTE`에 route 매핑을 추가합니다.
7. `06 Run Flow Text Switch`에 새 text output을 추가합니다.
8. `07 Selected Run Flow Message Merger`에 새 message input을 추가합니다.
9. main canvas에 새 Run Flow node를 추가하고 `06`의 새 output 및 `07`의 새 input을 연결합니다.
