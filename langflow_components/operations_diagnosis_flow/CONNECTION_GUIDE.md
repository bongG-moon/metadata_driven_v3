# Operations Diagnosis Flow Connection Guide

`operations_diagnosis_flow`는 병목, 이상 징후, 목표 미달, 장비 이슈 같은 운영 진단 요청 하나를 받아 원인 후보와 권장 확인 순서를 만드는 독립 E2E 업무 subflow입니다. 예시 질문은 "방금 결과 기준" 같은 후속 요청보다, 처음부터 진단 목적과 범위를 담은 완성 요청 형태로 작성합니다.

## Recommended Wiring

```text
Chat Input.Chat Message
  -> 00 MongoDB Session State Loader.Question
  -> 00 Diagnosis Request Loader.Question

00 MongoDB Session State Loader.Loaded State
  -> 00 Diagnosis Request Loader.Previous State

00 Diagnosis Request Loader.Payload
  -> 01 Diagnosis Signal Collector.Payload

01 Diagnosis Signal Collector.Payload
  -> 02 Diagnosis Rule Evaluator.Payload

02 Diagnosis Rule Evaluator.Payload
  -> 03 Diagnosis Response Builder.Payload

03 Diagnosis Response Builder.Payload
  -> 04 Diagnosis Message Adapter.Payload

04 Diagnosis Message Adapter.Message
  -> Chat Output

03 Diagnosis Response Builder.Payload
  -> 05 Diagnosis API Response Builder.Payload

05 Diagnosis API Response Builder.API Response
  -> 01 MongoDB Session State Writer.Response Payload
```

`00 Diagnosis Request Loader`에는 `Question`과 `Previous State`만 남아 있습니다. session id는 Chat/API message 또는 state 안에서 자동 추론합니다.

`03 Diagnosis Response Builder`는 더 이상 Chat Output에 직접 연결하지 않습니다. Langflow가 한 노드 안의 Data/Message 다중 출력을 잘못 판정해 연결을 끊는 경우가 있어, Chat 표시용은 `04`, API/Data용은 `05`로 분리했습니다.

## E2E Test Questions

아래 질문들은 `operations_diagnosis_flow`가 선택되어야 하는 대표 예시입니다.

```text
오늘 DA공정 병목 원인을 진단해줘

오늘 WB공정에서 재공이 많이 쌓인 원인 후보를 진단해줘

오늘 목표 대비 생산량이 저조한 제품들의 원인 후보를 진단해줘

오늘 HBM 제품군 생산 저조 원인을 장비, 재공, HOLD LOT 관점으로 진단해줘

오늘 DA공정에서 재공 상위 공정의 HOLD LOT 수와 평균 IN TAT를 보고 병목 여부를 진단해줘
```

이 예시들의 의도는 `operations_diagnosis_flow` 안에서 진단 목적, 필요한 증거 데이터, 분석 관점, 원인 후보, 권장 확인 순서까지 이어지는 것입니다. 후속 state 재사용은 나중에 확장할 수 있지만, 현재 예시 기준은 신규 E2E 진단 요청입니다.

## Outputs

| Output | Use |
| --- | --- |
| `03 Diagnosis Response Builder.Payload` | `04 Diagnosis Message Adapter`와 `05 Diagnosis API Response Builder`로 전달 |
| `04 Diagnosis Message Adapter.Message` | Chat Output |
| `05 Diagnosis API Response Builder.API Response` | Session State Writer 또는 API/Data output |

## Extension Point

향후 실제 진단 source 조회가 필요하면 `01 Diagnosis Signal Collector` 뒤에 source 조회 branch를 추가하거나, 필요한 경우 `data_analysis_flow`를 별도 API 호출로 붙이면 됩니다.
