# Routed API + Session State Wiring Guide

이 문서는 main router flow와 하위 flow API를 연결하는 기준입니다. 현재 권장 구조는 단순합니다.

```text
main router flow
Chat Input
-> router_flow 00~05
-> 06 Selected Flow API Runner
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

main flow는 subflow 내부 payload를 조립하지 않습니다. main flow는 질문을 분류하고, `05 Orchestrator Response Builder`가 `api_url + input_value + session_id` 형태의 `subflow_call`을 만든 뒤, `06 Selected Flow API Runner`가 선택된 subflow 하나만 호출하게 합니다.

## Main Router Connections

```text
Chat Input.Chat Message
  -> 00 Router Request Loader.Question

00 Router Request Loader.Payload
  -> 01 Metadata Context Loader.Payload

01 Metadata Context Loader.Payload
  -> 02 Route Candidate Builder.Payload

02 Route Candidate Builder.Payload
  -> 03A Route Prompt Context Builder.Payload

03A Route Prompt Context Builder.Route Prompt Context
  -> Langflow Prompt Template.route_prompt_context

Langflow Prompt Template.Prompt
  -> Route Classifier LLM.Input

02 Route Candidate Builder.Payload
  -> 04 Route Classifier Normalizer.Payload

Route Classifier LLM.Output
  -> 04 Route Classifier Normalizer.Route LLM Response

04 Route Classifier Normalizer.Payload
  -> 05 Orchestrator Response Builder.Payload

05 Orchestrator Response Builder.Route Response
  -> 06 Selected Flow API Runner.Route Response

06 Selected Flow API Runner.Message
  -> Chat Output
```

native Run Flow node는 text/message input만 받을 수 있고 여러 Run Flow output을 한 노드로 모으면 Langflow 실행기가 연결된 upstream을 모두 기다릴 수 있습니다. direct router canvas에서는 `05`가 만든 `subflow_call`을 `06 Selected Flow API Runner`가 읽어서 선택된 subflow API 하나만 호출합니다.

| `selected_flow` | Called subflow |
| --- | --- |
| `metadata_qa_flow` | Metadata QA Flow |
| `data_analysis_flow` | Data Analysis Flow |
| `report_generation_flow` | Report Generation Flow |
| `operations_diagnosis_flow` | Operations Diagnosis Flow |

`05`와 `06`은 아래 환경변수를 사용합니다. 보통은 `.env`에 base URL과 flow id만 넣으면 `05`가 `subflow_call.api_url`을 만들어줍니다. `06`은 먼저 이 값을 사용하고, 비어 있으면 자기 advanced input과 환경변수를 fallback으로 확인합니다.

| selected_flow | Required env |
| --- | --- |
| `metadata_qa_flow` | `LANGFLOW_BASE_URL` + `LANGFLOW_METADATA_QA_FLOW_ID` or `LANGFLOW_METADATA_QA_API_URL` |
| `data_analysis_flow` | `LANGFLOW_BASE_URL` + `LANGFLOW_DATA_ANALYSIS_FLOW_ID` or `LANGFLOW_DATA_ANALYSIS_API_URL` |
| `report_generation_flow` | `LANGFLOW_BASE_URL` + `LANGFLOW_REPORT_GENERATION_FLOW_ID` or `LANGFLOW_REPORT_GENERATION_API_URL` |
| `operations_diagnosis_flow` | `LANGFLOW_BASE_URL` + `LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID` or `LANGFLOW_OPERATIONS_DIAGNOSIS_API_URL` |

예를 들어 subflow API가 `http://localhost:7860/api/v1/run/3023ab38-a7a3-475b-83c8-c04bd90a16c5`라면:

```text
LANGFLOW_BASE_URL=http://localhost:7860
LANGFLOW_METADATA_QA_FLOW_ID=3023ab38-a7a3-475b-83c8-c04bd90a16c5
```

또는 `LANGFLOW_METADATA_QA_API_URL`에 full URL을 바로 넣어도 됩니다.

예전 native Run Flow 분기용 switch/merger 노드는 제거했습니다. main router canvas는 `05 -> 06 -> Chat Output` 경로만 사용합니다.

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
| `metadata_qa_flow` | `00 Metadata QA Request Loader.Question` | `00 Metadata QA Request Loader.Previous State` | `05 Metadata QA API Response Builder.API Response` | `04 Metadata QA Message Adapter.Message` |
| `data_analysis_flow` | `00 Analysis Request Loader.Question` | `00 Analysis Request Loader.Previous State` | `21 API Response Builder.API Response` | `20 Answer Message Adapter.Message` |
| `report_generation_flow` | `00 Report Request Loader.Question` | `00 Report Request Loader.Previous State` | `03 Report Response Builder.API Response` | `03 Report Response Builder.Message` |
| `operations_diagnosis_flow` | `00 Diagnosis Request Loader.Question` | `00 Diagnosis Request Loader.Previous State` | `05 Diagnosis API Response Builder.API Response` | `04 Diagnosis Message Adapter.Message` |

## E2E Example Questions

`report_generation_flow`와 `operations_diagnosis_flow`는 현재 예시 기준으로 후속 질문이 아니라 신규 E2E 업무 요청을 테스트 문장으로 사용합니다.

Report generation examples:

```text
오늘 DA공정 일일 운영 리포트 만들어줘
오늘 WB공정 기준으로 생산량, 재공, 목표 달성률을 포함한 요약 리포트 만들어줘
오늘 HBM 제품군의 생산 실적, 재공 현황, 목표 대비 차이를 리포트로 정리해줘
오늘 DA/WB공정의 주요 이상 징후와 우선 확인 항목을 포함해서 운영 리포트 작성해줘
```

Operations diagnosis examples:

```text
오늘 DA공정 병목 원인을 진단해줘
오늘 WB공정에서 재공이 많이 쌓인 원인 후보를 진단해줘
오늘 목표 대비 생산량이 저조한 제품들의 원인 후보를 진단해줘
오늘 HBM 제품군 생산 저조 원인을 장비, 재공, HOLD LOT 관점으로 진단해줘
오늘 DA공정에서 재공 상위 공정의 HOLD LOT 수와 평균 IN TAT를 보고 병목 여부를 진단해줘
```

## Session Id

별도 `Session ID` 포트는 request loader와 session loader/writer에서 제거했습니다. Langflow API payload의 `session_id`가 Chat/API message에 포함되면 컴포넌트가 자동으로 읽습니다. 응답 저장 시에는 final API response의 `request.session_id`를 사용합니다.

단독 테스트에서 message에 session id가 없으면 `demo-session` fallback이 사용됩니다.

## Adding A New Routed Flow

1. 새 subflow가 질문 하나만 받아 독립 실행되도록 만듭니다.
2. 필요하면 subflow 내부에 session state loader/writer를 둡니다.
3. `router_flow/02_route_candidate_builder.py`에 새 route hint를 추가합니다.
4. `router_flow/ROUTE_CLASSIFIER_PROMPT_TEMPLATE.md`와 Langflow 기본 Prompt Template의 route 설명에 새 route를 추가합니다.
5. `router_flow/04_route_classifier_normalizer.py`의 허용 route에 새 route를 추가합니다.
6. `router_flow/05_orchestrator_response_builder.py`의 `FLOW_BY_ROUTE`에 route 매핑을 추가합니다.
7. `06 Selected Flow API Runner`에 새 `selected_flow`의 API URL/env 매핑을 추가합니다.
