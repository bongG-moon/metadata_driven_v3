# Router Flow Connection Guide

`router_flow`는 사용자 질문을 받아 어떤 하위 flow를 실행할지만 결정하는 main 분기 flow입니다. 데이터 조회, pandas 분석, 리포트 작성, session state 저장은 이 flow에서 처리하지 않습니다.

## Node Map

| Node | Role |
| --- | --- |
| `00 Router Request Loader` | Chat Input의 질문을 route 판단 payload로 변환 |
| `01 Metadata Context Loader` | route 판단에 필요한 metadata 요약 로드 |
| `02 Route Candidate Builder` | rule 기반 1차 후보와 LLM 분류 필요 여부 생성 |
| `03A Route Prompt Context Builder` | 기본 Prompt Template에 넣을 route context 하나 생성 |
| Langflow Prompt Template | `ROUTE_CLASSIFIER_PROMPT_TEMPLATE.md` 또는 `ROUTE_CLASSIFIER_PROMPT_TEMPLATE_KO.md` 내용을 사용해 route/API 매핑 prompt 생성 |
| Route Classifier LLM | `metadata_qa`, `data_analysis`, `report_generation`, `operations_diagnosis` 중 선택 |
| `04 Route Classifier Normalizer` | LLM 응답을 표준 route payload로 정규화 |
| `05 Orchestrator Response Builder` | 최종 `selected_flow`와 실행용 `subflow_call` 생성 |
| `06 Selected Flow API Runner` | `subflow_call` 기준으로 선택된 subflow API 하나만 호출하고 Chat Output message 생성 |

native Run Flow node는 text/message input만 받을 수 있어 `05.Route Response`를 직접 받을 수 없습니다. 또 여러 Run Flow output을 한 노드로 모으면 Langflow 실행기가 연결된 upstream을 모두 기다릴 수 있습니다. 그래서 direct router canvas 실행은 API 호출 방식의 `06 Selected Flow API Runner`만 사용합니다.

Chat Output은 `06.Message` 하나만 연결합니다. `05`가 `subflow_call.api_url`, `subflow_call.input_value`, `subflow_call.session_id`를 만들고, `06`은 이 실행 지시서대로 metadata QA, data analysis, report, diagnosis 중 하나만 `/api/v1/run/{flow_id}`로 호출합니다.

## Recommended Wiring

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
  -> Prompt Template.route_prompt_context

Prompt Template.Prompt
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

기본 Prompt Template에는 `ROUTE_CLASSIFIER_PROMPT_TEMPLATE.md` 또는 `ROUTE_CLASSIFIER_PROMPT_TEMPLATE_KO.md` 내용을 붙여 넣습니다. API를 바꾸고 싶으면 템플릿 안의 route/API catalog에서 `api_url`만 수정합니다.

## 06 Runner Settings

`06 Selected Flow API Runner`에는 하위 flow별 API URL 입력칸을 두지 않습니다. API 주소는 `05.Route Response.subflow_call.api_url`에서만 받습니다.

주소를 수정하는 위치는 아래 둘 중 하나입니다.

1. 기본 Prompt Template의 `Editable route/API catalog` 안 `api_url`
2. `.env`의 full API URL 또는 `LANGFLOW_BASE_URL + *_FLOW_ID`

`api_url`을 Prompt Template에서 비워두면 `05 Orchestrator Response Builder`가 아래 환경변수로 `subflow_call.api_url`을 채웁니다.

| selected_flow | Env fallback |
| --- | --- |
| `metadata_qa_flow` | `LANGFLOW_METADATA_QA_API_URL` 또는 `LANGFLOW_BASE_URL + LANGFLOW_METADATA_QA_FLOW_ID` |
| `data_analysis_flow` | `LANGFLOW_DATA_ANALYSIS_API_URL` 또는 `LANGFLOW_BASE_URL + LANGFLOW_DATA_ANALYSIS_FLOW_ID` |
| `report_generation_flow` | `LANGFLOW_REPORT_GENERATION_API_URL` 또는 `LANGFLOW_BASE_URL + LANGFLOW_REPORT_GENERATION_FLOW_ID` |
| `operations_diagnosis_flow` | `LANGFLOW_OPERATIONS_DIAGNOSIS_API_URL` 또는 `LANGFLOW_BASE_URL + LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID` |

보통은 Prompt Template의 `api_url`에 full URL을 직접 적거나, `.env`에 `LANGFLOW_BASE_URL`, `LANGFLOW_METADATA_QA_FLOW_ID`, `LANGFLOW_DATA_ANALYSIS_FLOW_ID`, `LANGFLOW_REPORT_GENERATION_FLOW_ID`, `LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID`를 넣습니다.

## Route Test Examples

| Example question | Expected selected flow |
| --- | --- |
| `현재 조회 가능한 DATA LIST 알려줘` | `metadata_qa_flow` |
| `공정 그룹관련해서 등록된 도메인정보들 알려줘` | `metadata_qa_flow` |
| `오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘` | `data_analysis_flow` |
| `오늘 WB공정 기준으로 생산량, 재공, 목표 달성률을 포함한 요약 리포트 만들어줘` | `report_generation_flow` |
| `오늘 HBM 제품군 생산 저조 원인을 장비, 재공, HOLD LOT 관점으로 진단해줘` | `operations_diagnosis_flow` |

`report_generation_flow`와 `operations_diagnosis_flow`의 예시는 후속 질문이 아니라 신규 E2E 업무 요청 기준입니다.
명확한 metadata/catalog/domain 질문은 `02 Route Candidate Builder`가 1차 후보를 `metadata_qa_flow`로 둡니다. Route Classifier LLM 응답이 비어도 `04 Route Classifier Normalizer`는 이 후보를 fallback으로 사용하므로, 이런 질문이 `data_analysis_flow`로 잘못 떨어지지 않아야 합니다.

## Metadata QA API Troubleshooting

metadata QA flow를 단독 실행하면 답변이 나오는데 router에서 다음으로 넘어가지 않으면 아래 순서로 확인합니다.

1. `04 Route Classifier Normalizer` status의 `route`가 `metadata_qa`인지 확인합니다. `data_analysis`로 남아 있으면 Route Classifier LLM 연결/응답이 비었거나 오래된 02/03/04 노드 template일 수 있으므로 노드를 다시 불러옵니다.
2. `05 Orchestrator Response Builder` status의 `selected_flow`가 `metadata_qa_flow`인지 확인합니다.
3. `05.Route Response.subflow_call.input_value`에 사용자 질문이 있고, `subflow_call.api_url`이 비어 있지 않은지 확인합니다.
4. `06 Selected Flow API Runner` status의 `selected_flow`가 `metadata_qa_flow`인지 확인합니다.
5. `06` message가 `API URL is not configured`이면 Prompt Template의 `metadata_qa` catalog에 `api_url`을 적거나, `LANGFLOW_BASE_URL + LANGFLOW_METADATA_QA_FLOW_ID` 또는 `LANGFLOW_METADATA_QA_API_URL`을 설정합니다.
6. metadata QA subflow의 최종 Chat Output은 `04 Metadata QA Message Adapter.Message`를 사용합니다. `05 Metadata QA API Response Builder.API Response`는 session writer나 API 응답용입니다.

## Adding A New Flow Later

1. 새 subflow를 `Chat Input -> 00 Request Loader -> ... -> Response Builder -> Chat Output` 형태로 독립 실행 가능하게 만듭니다.
2. session state가 필요하면 새 subflow 내부에 `00 MongoDB Session State Loader`와 `01 MongoDB Session State Writer`를 둡니다.
3. `02 Route Candidate Builder`에 새 route 후보 rule 또는 hint를 추가합니다.
4. `ROUTE_CLASSIFIER_PROMPT_TEMPLATE.md` 또는 `ROUTE_CLASSIFIER_PROMPT_TEMPLATE_KO.md`와 Langflow 기본 Prompt Template의 route 설명에 새 route를 추가합니다.
5. `04 Route Classifier Normalizer`의 허용 route에 새 route를 추가합니다.
6. `05 Orchestrator Response Builder.FLOW_BY_ROUTE`에 `route -> selected_flow` 매핑을 추가합니다.
7. `06 Selected Flow API Runner`의 URL/env 매핑에 새 `selected_flow`를 추가합니다.

핵심 원칙은 main flow가 subflow 내부 payload를 조립하지 않는 것입니다. main flow는 분기와 text 전달, 최종 message 선택만 하고, 각 subflow가 자기 안에서 state load/write와 실행 준비를 담당합니다.
