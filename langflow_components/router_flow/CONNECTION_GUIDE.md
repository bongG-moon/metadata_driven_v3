# Router Flow Connection Guide

`router_flow`는 사용자 질문을 받아 어떤 하위 flow를 실행할지만 결정하는 main 분기 flow입니다. 데이터 조회, pandas 분석, 리포트 작성, session state 저장은 이 flow에서 처리하지 않습니다.

## Node Map

| Node | Role |
| --- | --- |
| `00 Router Request Loader` | Chat Input의 질문을 route 판단 payload로 변환 |
| `01 Metadata Context Loader` | route 판단에 필요한 metadata 요약 로드 |
| `02 Route Candidate Builder` | rule 기반 1차 후보와 LLM 분류 필요 여부 생성 |
| `03 Route Classifier Prompt Builder` | 애매한 질문일 때 route classifier prompt 생성 |
| Route Classifier LLM | `metadata_qa`, `data_analysis`, `report_generation`, `operations_diagnosis` 중 선택 |
| `04 Route Classifier Normalizer` | LLM 응답을 표준 route payload로 정규화 |
| `05 Orchestrator Response Builder` | 최종 `selected_flow`가 들어 있는 route decision 생성 |
| `06 Run Flow Text Switch` | Run Flow가 받을 수 있는 text output으로 선택 branch 하나만 열기 |
| `07 Selected Run Flow Message Merger` | 선택된 Run Flow의 message 하나만 Chat Output으로 전달 |

Run Flow node는 text/message input만 받을 수 있습니다. 그래서 `05.Route Response`를 Run Flow에 직접 연결하지 않고, `06 Run Flow Text Switch`를 거쳐 선택된 Run Flow에 질문 text를 보냅니다.

Chat Output은 입력을 하나만 받을 수 있습니다. 그래서 네 Run Flow output을 Chat Output에 직접 연결하지 않고, `07 Selected Run Flow Message Merger`에서 선택된 message 하나로 합친 뒤 Chat Output에 연결합니다.

## Recommended Wiring

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
  -> 07 Selected Run Flow Message Merger.Route Response
```

`03 Route Classifier Prompt Builder.Prompt Payload`는 디버그용입니다. `04 Route Classifier Normalizer.Payload`에는 `02 Route Candidate Builder.Payload`를 연결합니다.

## Run Flow Inputs

`06 Run Flow Text Switch`의 output을 각각 해당 Run Flow node의 text input에 연결합니다.

| `06` output | Connect to |
| --- | --- |
| `Metadata QA Text` | Metadata QA Run Flow input |
| `Data Analysis Text` | Data Analysis Run Flow input |
| `Report Generation Text` | Report Generation Run Flow input |
| `Operations Diagnosis Text` | Operations Diagnosis Run Flow input |

```text
06 Run Flow Text Switch.Metadata QA Text
  -> RF Metadata QA.input

06 Run Flow Text Switch.Data Analysis Text
  -> RF Data Analysis.input

06 Run Flow Text Switch.Report Generation Text
  -> RF Report Generation.input

06 Run Flow Text Switch.Operations Diagnosis Text
  -> RF Operations Diagnosis.input
```

`06`은 `selected_flow`와 맞는 output 하나만 질문 text를 내보내고, 나머지 output은 `stop()` 처리합니다. 따라서 skip은 각 subflow 안에서 처리하지 않고 main router의 `06`에서 처리됩니다.

## Run Flow Outputs

각 Run Flow의 output은 `07 Selected Run Flow Message Merger`로 모읍니다.

| Run Flow output | Connect to |
| --- | --- |
| Metadata QA Run Flow output | `07.Metadata QA Output` |
| Data Analysis Run Flow output | `07.Data Analysis Output` |
| Report Generation Run Flow output | `07.Report Generation Output` |
| Operations Diagnosis Run Flow output | `07.Operations Diagnosis Output` |

```text
RF Metadata QA.output
  -> 07 Selected Run Flow Message Merger.Metadata QA Output

RF Data Analysis.output
  -> 07 Selected Run Flow Message Merger.Data Analysis Output

RF Report Generation.output
  -> 07 Selected Run Flow Message Merger.Report Generation Output

RF Operations Diagnosis.output
  -> 07 Selected Run Flow Message Merger.Operations Diagnosis Output

07 Selected Run Flow Message Merger.Message
  -> Chat Output
```

`07`은 payload를 다시 조립하지 않습니다. `selected_flow`에 해당하는 Run Flow message만 골라서 그대로 Chat Output으로 넘깁니다.

## Adding A New Flow Later

1. 새 subflow를 `Chat Input -> 00 Request Loader -> ... -> Response Builder -> Chat Output` 형태로 독립 실행 가능하게 만듭니다.
2. session state가 필요하면 새 subflow 내부에 `00 MongoDB Session State Loader`와 `01 MongoDB Session State Writer`를 둡니다.
3. `02 Route Candidate Builder`에 새 route 후보 rule 또는 hint를 추가합니다.
4. `03 Route Classifier Prompt Builder`의 route 설명에 새 route를 추가합니다.
5. `04 Route Classifier Normalizer`의 허용 route에 새 route를 추가합니다.
6. `05 Orchestrator Response Builder.FLOW_BY_ROUTE`에 `route -> selected_flow` 매핑을 추가합니다.
7. `06 Run Flow Text Switch`에 새 text output을 추가합니다.
8. `07 Selected Run Flow Message Merger`에 새 message input을 추가합니다.
9. main canvas에 새 Run Flow node를 추가하고 `06`의 새 output 및 `07`의 새 input을 연결합니다.

핵심 원칙은 main flow가 subflow 내부 payload를 조립하지 않는 것입니다. main flow는 분기와 text 전달, 최종 message 선택만 하고, 각 subflow가 자기 안에서 state load/write와 실행 준비를 담당합니다.
