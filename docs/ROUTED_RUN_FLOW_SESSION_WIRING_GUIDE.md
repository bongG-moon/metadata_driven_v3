# Routed Run Flow + Session State Wiring Guide

이 문서는 `router_flow`가 질문을 분기하고, 선택된 하위 flow를 Langflow `Run Flow`로 실행할 때 어떤 값을 연결해야 하는지 정리합니다.

## Recommended Shape

현재 Langflow canvas에서 가장 이해하기 쉬운 기준은 **독립 subflow 방식**입니다.

```text
main router flow
Chat Input
-> 00 Router Request Loader
-> 01 Metadata Context Loader
-> 02 Route Candidate Builder
-> 03 Route Classifier Prompt Builder
-> Route Classifier LLM
-> 04 Route Classifier Normalizer
-> 05 Orchestrator Response Builder
-> route switch
-> selected Run Flow
-> Chat Output
```

각 subflow는 단독 실행 가능한 하나의 앱처럼 구성합니다.

```text
subflow
Chat Input
-> 00 MongoDB Session State Loader
-> 00 Request Loader
-> subflow logic
-> API/Response Builder
-> 01 MongoDB Session State Writer
-> Chat Output
```

즉, main flow는 **질문을 분류하고 선택된 flow를 실행하는 역할만** 합니다. 이전 state 조회, 분석 결과 저장, 최종 답변 생성은 각 subflow 안에서 처리합니다.

## Why This Is Preferred

이 방식이면 Langflow 화면에서 흐름이 분명합니다.

| 위치 | 책임 |
| --- | --- |
| main router flow | 질문 분류, 실행할 subflow 선택 |
| metadata_qa_flow | metadata/catalog/help 답변 |
| data_analysis_flow | 데이터 조회, pandas 분석, 결과 저장, 답변 생성 |
| report_generation_flow | 이전 분석 state 기반 리포트 생성 |
| operations_diagnosis_flow | 병목/이상/운영 진단 |

main flow가 `state`, `metadata_route`, `router_payload`, `session_id` 같은 내부 payload를 모두 조립하면 canvas 연결이 복잡해집니다. 반대로 각 subflow가 독립 실행 가능하면 main은 같은 사용자 입력을 선택된 Run Flow에 넘기기만 하면 됩니다.

## Main Flow Wiring

### 1. Router

```text
Chat Input.Chat Message
  -> 00 Router Request Loader.Question

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

`00 Router Request Loader.Session ID`는 기본적으로 비워둡니다. Chat Input/Run Flow가 가진 대화 session id를 loader가 읽을 수 있으면 그 값을 사용하고, 없으면 단독 테스트용 fallback만 사용합니다.

### 2. Route Switch and Run Flow

Run Flow node를 target flow별로 4개 두는 구성이 가장 안전합니다.

| route | Run Flow target |
| --- | --- |
| `metadata_qa` / `direct_answer` | `metadata_qa_flow` |
| `data_analysis` | `data_analysis_flow` |
| `report_generation` | `report_generation_flow` |
| `operations_diagnosis` | `operations_diagnosis_flow` |

연결 기준은 간단합니다.

```text
05 Orchestrator Response Builder.Route Response
  -> Route Switch condition

Chat Input.Chat Message
  -> selected Run Flow input

selected Run Flow output
  -> Chat Output
```

Run Flow가 target flow의 Chat Input을 dynamic input으로 보여주면 그 포트에 `Chat Input.Chat Message`를 연결합니다. 만약 Run Flow가 text input만 받는 형태로 보이면 같은 Chat Input의 text/message 값을 연결해도 됩니다. 각 subflow 첫 loader가 plain text와 Message-like 입력을 모두 처리합니다.

## Subflow Standalone Pattern

각 subflow는 아래 구조를 기본으로 둡니다. 이 구조여야 main flow에서 text/message 하나만 넘겨도 동작합니다.

### Common Session Load

```text
Chat Input.Chat Message
  -> 00 MongoDB Session State Loader.Question
  -> 00 Request Loader.Question

00 MongoDB Session State Loader.Loaded State
  -> 00 Request Loader.Previous State
```

`00 MongoDB Session State Loader.Session ID`와 `00 Request Loader.Session ID`는 보통 연결하지 않습니다. Chat Input message에 session id가 있으면 자동으로 읽고, Langflow 단독 테스트에서만 직접 입력합니다.

### Common Session Write

```text
Final API/Response Builder.API Response
  -> 01 MongoDB Session State Writer.Response Payload

01 MongoDB Session State Writer.Payload
  -> optional API/Data Output

Final Message output
  -> Chat Output
```

writer도 `Response Payload.request.session_id`를 우선 사용하므로 `Session ID` 포트는 보통 비워둘 수 있습니다.

## Flow-Specific End Nodes

| subflow | first loader | final data response | final chat message |
| --- | --- | --- | --- |
| `metadata_qa_flow` | `00 Metadata QA Request Loader` | `04 Metadata QA API Response Builder.API Response` | `04 Metadata QA API Response Builder.API Message` |
| `data_analysis_flow` | `00 Analysis Request Loader` | `21 API Response Builder.API Response` | `21 API Response Builder.API Message` |
| `report_generation_flow` | `00 Report Request Loader` | `03 Report Response Builder.API Response` | `03 Report Response Builder.Message` |
| `operations_diagnosis_flow` | `00 Diagnosis Request Loader` | `03 Diagnosis Response Builder.API Response` | `03 Diagnosis Response Builder.Message` |

## Optional Advanced Mode

기존 `Router Payload` 방식도 호환은 됩니다. backend orchestrator가 main에서 state를 한 번만 읽고, 선택된 subflow에 구조화 payload를 넘기고, main에서 한 번만 writer를 실행하는 방식입니다.

다만 Langflow canvas를 직접 보고 운영하려는 현재 목적에는 권장하지 않습니다. 연결 포트가 많아지고, main flow가 subflow 내부 계약을 너무 많이 알아야 해서 전체 흐름이 덜 직관적입니다.

## End-To-End Test Questions

같은 대화 session에서 순서대로 확인합니다.

```text
1. 오늘 WB공정 생산량 알려줘
2. 방금 결과에서 사용한 데이터셋 알려줘
3. 현재 WB공정에서 WIP가 가장 많은 제품 TOP 5 보여줘
4. 그 제품들의 장비 대수 알려줘
5. 방금 결과로 리포트 만들어줘
6. 현재 병목 원인이 뭔지 진단해줘
```

확인 포인트:

- main router가 질문 유형에 맞는 subflow 하나만 실행하는지
- 각 subflow가 Chat Input 하나로 단독 실행되는지
- 각 subflow가 Chat Output 하나로 최종 답변을 내보내는지
- 두 번째 턴부터 `00 MongoDB Session State Loader`가 같은 session id의 state를 읽는지
- 분석 flow 이후 `state.current_data.data_ref`가 다음 턴에 유지되는지
