# Router Flow2 Connection Guide

`router_flow2`는 기존 `router_flow`의 LLM route classifier 대신 Langflow 내장 `Smart Router` 컴포넌트를 사용해 route를 고르는 대안 flow입니다.

기존 subflow 실행 방식은 그대로 유지합니다. Smart Router는 route label만 선택하고, `01 Smart Router Route Response Builder`가 그 label을 기존 `06 Selected Flow API Runner`가 이해하는 `route_response.subflow_call`로 변환합니다.

## Node Map

| Node | Role |
| --- | --- |
| `00 Router2 Request Loader` | Chat Input 질문을 router payload로 변환 |
| Langflow `Smart Router` | 질문을 보고 route label 하나 선택 |
| `01 Smart Router Route Response Builder` | Smart Router 결과를 `route_response`로 변환 |
| `router_flow/06 Selected Flow API Runner` | 선택된 subflow API 하나만 호출 |
| Chat Output | 선택된 subflow 응답 표시 |

## Smart Router Route Labels

Smart Router route 이름은 아래 label을 그대로 사용합니다.

| Route label | Selected subflow |
| --- | --- |
| `metadata_qa` | `metadata_qa_flow` |
| `data_analysis` | `data_analysis_flow` |
| `report_generation` | `report_generation_flow` |
| `operations_diagnosis` | `operations_diagnosis_flow` |

Smart Router의 route 설명에는 [SMART_ROUTER_INSTRUCTIONS_KO.md](SMART_ROUTER_INSTRUCTIONS_KO.md) 내용을 붙여 넣습니다.

## Recommended Wiring

```text
Chat Input.Chat Message
  -> 00 Router2 Request Loader.Question

Chat Input.Chat Message
  -> Smart Router.Input

00 Router2 Request Loader.Payload
  -> 01 Smart Router Route Response Builder.Payload

Smart Router.Selected Route 또는 Output
  -> 01 Smart Router Route Response Builder.Smart Router Output

01 Smart Router Route Response Builder.Route Response
  -> router_flow/06 Selected Flow API Runner.Route Response

router_flow/06 Selected Flow API Runner.Message
  -> Chat Output
```

Smart Router가 `metadata_qa`, `data_analysis`, `report_generation`, `operations_diagnosis` 중 하나의 문자열을 output으로 줄 수 있으면 위 연결이 가장 단순합니다.

## Branch Output 방식일 때

Langflow Smart Router 버전에 따라 route마다 output port가 따로 있을 수 있습니다. 이 경우에는 route별 branch 뒤에 `01 Smart Router Route Response Builder`를 하나씩 두고 `Forced Route` 값을 해당 route로 지정합니다.

예:

| Smart Router branch | Builder `Forced Route` |
| --- | --- |
| metadata route branch | `metadata_qa` |
| data analysis route branch | `data_analysis` |
| report route branch | `report_generation` |
| diagnosis route branch | `operations_diagnosis` |

이 방식에서는 각 branch의 `01.Route Response`를 별도의 `06 Selected Flow API Runner`에 연결하고, 각 runner의 Message를 Chat Output으로 둡니다. Smart Router가 선택한 branch만 실행되는지 Langflow 캔버스에서 확인하세요.

## API URL 설정

`01 Smart Router Route Response Builder`는 기존 router와 같은 환경변수를 사용합니다.

| Selected subflow | Env fallback |
| --- | --- |
| `metadata_qa_flow` | `LANGFLOW_METADATA_QA_API_URL` 또는 `LANGFLOW_BASE_URL + LANGFLOW_METADATA_QA_FLOW_ID` |
| `data_analysis_flow` | `LANGFLOW_DATA_ANALYSIS_API_URL` 또는 `LANGFLOW_BASE_URL + LANGFLOW_DATA_ANALYSIS_FLOW_ID` |
| `report_generation_flow` | `LANGFLOW_REPORT_GENERATION_API_URL` 또는 `LANGFLOW_BASE_URL + LANGFLOW_REPORT_GENERATION_FLOW_ID` |
| `operations_diagnosis_flow` | `LANGFLOW_OPERATIONS_DIAGNOSIS_API_URL` 또는 `LANGFLOW_BASE_URL + LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID` |

Smart Router output이 JSON이면 `api_url`, `flow_id`, `selected_flow`, `confidence`, `reason`도 함께 받을 수 있습니다.

예:

```json
{"route": "metadata_qa", "confidence": "high", "reason": "metadata catalog question"}
```

## Route Test Examples

| Example question | Expected route |
| --- | --- |
| `현재 조회 가능한 DATA LIST 알려줘` | `metadata_qa` |
| `공정 그룹관련해서 등록된 도메인정보들 알려줘` | `metadata_qa` |
| `오늘 DA 공정 생산량 알려줘` | `data_analysis` |
| `512G G-777 제품의 어제 생산량과 재공을 세부 공정별로 알려줘` | `data_analysis` |
| `오늘 WB공정 기준으로 생산량, 재공, 목표 달성률을 포함한 요약 리포트 만들어줘` | `report_generation` |
| `오늘 HBM 제품군 생산 저조 원인을 장비, 재공, HOLD LOT 관점으로 진단해줘` | `operations_diagnosis` |

## 기존 router_flow와의 차이

기존 `router_flow`는 metadata context, 후보 rule, route classifier LLM, normalizer를 모두 커스텀 노드로 둡니다.

`router_flow2`는 이 중 route classifier 부분을 Langflow 내장 Smart Router에 맡깁니다. 그래서 구조는 더 단순하지만, 세부 metadata action이나 target dataset 추론은 기존 router보다 약할 수 있습니다. data analysis subflow 자체가 intent 분석을 다시 수행하므로 일반 질의 실행에는 큰 문제가 없도록 설계했습니다.
