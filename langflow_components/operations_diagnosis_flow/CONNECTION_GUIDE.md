# Operations Diagnosis Flow Connection Guide

`operations_diagnosis_flow`는 병목, 이상 징후, 목표 미달, 장비 이슈 같은 운영 진단 요청을 별도 branch로 받기 위한 독립 subflow입니다. 현재 구현은 이전 분석 state에서 신호를 수집하고 rule 기반 진단/추가 조회 필요성을 정리하는 구조입니다.

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

03 Diagnosis Response Builder.Message
  -> Chat Output

03 Diagnosis Response Builder.API Response
  -> 01 MongoDB Session State Writer.Response Payload
```

`00 Diagnosis Request Loader`에는 `Question`과 `Previous State`만 남아 있습니다. session id는 Chat/Run Flow message 또는 state 안에서 자동 추론합니다.

## Outputs

| Output | Use |
| --- | --- |
| `03 Diagnosis Response Builder.Message` | Chat Output |
| `03 Diagnosis Response Builder.API Response` | Session State Writer 또는 API/Data output |

## Extension Point

향후 실제 진단 source 조회가 필요하면 `01 Diagnosis Signal Collector` 뒤에 source 조회 branch를 추가하거나, 필요한 경우 `data_analysis_flow`를 별도 Run Flow로 호출하는 구조를 붙이면 됩니다.
