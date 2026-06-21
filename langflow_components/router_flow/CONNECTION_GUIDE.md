# Router Flow Connection Guide

`router_flow`는 사용자의 질문을 먼저 받아서 실행할 하위 flow를 선택하는 앞단 분기 flow입니다. 데이터 조회, pandas 실행, 결과 저장은 하지 않습니다.

## Recommended Main Canvas

각 하위 flow가 독립 실행 가능하게 구성되어 있다면 main flow는 아래처럼 단순하게 둡니다.

```text
Chat Input
-> 00 Router Request Loader
-> 01 Metadata Context Loader
-> 02 Route Candidate Builder
-> 03 Route Classifier Prompt Builder
-> Route Classifier LLM
-> 04 Route Classifier Normalizer
-> 05 Orchestrator Response Builder
-> Route Switch
-> selected Run Flow
-> Chat Output
```

main flow는 session state loader/writer를 직접 갖지 않습니다. state load/write는 선택된 subflow 내부에서 처리합니다.

## Required Input

| Node | Input | Connect |
| --- | --- | --- |
| `00 Router Request Loader` | `Question` | `Chat Input.Chat Message` 또는 text |

`Session ID`는 보통 비워둡니다. Chat Input message에 session id가 있으면 loader가 읽고, 없으면 단독 테스트용 fallback만 사용합니다.

## Router Connections

```text
00 Router Request Loader.Payload
  -> 01 Metadata Context Loader.Payload

01 Metadata Context Loader.Payload
  -> 02 Route Candidate Builder.Payload

02 Route Candidate Builder.Payload
  -> 03 Route Classifier Prompt Builder.Payload
  -> 04 Route Classifier Normalizer.Payload

03 Route Classifier Prompt Builder.Route Prompt
  -> Route Classifier LLM.Input

Route Classifier LLM.Output
  -> 04 Route Classifier Normalizer.Route LLM Response

04 Route Classifier Normalizer.Payload
  -> 05 Orchestrator Response Builder.Payload
```

## Route Switch

`05 Orchestrator Response Builder.Route Response`의 `selected_flow` 또는 `route` 값으로 branch를 나눕니다.

| selected_flow | Run Flow target |
| --- | --- |
| `metadata_qa_flow` | Metadata QA Flow |
| `data_analysis_flow` | Data Analysis Flow |
| `report_generation_flow` | Report Generation Flow |
| `operations_diagnosis_flow` | Operations Diagnosis Flow |

각 branch에서 Run Flow에는 같은 사용자 입력만 넘깁니다.

```text
Chat Input.Chat Message
  -> selected Run Flow input

selected Run Flow output
  -> Chat Output
```

Run Flow node가 target flow의 Chat Input을 dynamic input으로 보여주면 그 포트에 연결합니다. text input만 보이면 같은 질문 text를 연결해도 됩니다.

## Optional Advanced Payload Mode

`06 Run Flow Branch Router`와 `07 Selected Run Flow Response Merger`는 backend orchestrator처럼 main flow가 `Router Payload`를 만들어 subflow에 넘기는 고급 구성용입니다.

현재처럼 Langflow 화면에서 흐름을 쉽게 파악하는 목적이라면 이 방식은 기본으로 쓰지 않는 것이 좋습니다. 각 subflow가 자체 Chat Input/Session Loader/Session Writer/Chat Output을 갖고 있으면 main flow는 route/run만 담당하면 됩니다.
