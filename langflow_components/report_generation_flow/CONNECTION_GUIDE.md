# Report Generation Flow Connection Guide

`report_generation_flow`는 이전 분석 결과와 session state를 바탕으로 리포트 초안을 만드는 독립 subflow입니다. 이 flow는 데이터 분석을 새로 수행하지 않습니다. 필요한 데이터가 없으면 먼저 `data_analysis_flow`를 실행해 결과와 `data_ref`를 만든 뒤 호출합니다.

## Recommended Wiring

```text
Chat Input.Chat Message
  -> 00 MongoDB Session State Loader.Question
  -> 00 Report Request Loader.Question

00 MongoDB Session State Loader.Loaded State
  -> 00 Report Request Loader.Previous State

00 Report Request Loader.Payload
  -> 01 Report Outline Builder.Payload

01 Report Outline Builder.Payload
  -> 02 Report Data Selector.Payload

02 Report Data Selector.Payload
  -> 03 Report Response Builder.Payload

03 Report Response Builder.Message
  -> Chat Output

03 Report Response Builder.API Response
  -> 01 MongoDB Session State Writer.Response Payload
```

`00 Report Request Loader`에는 `Question`과 `Previous State`만 남아 있습니다. session id는 Chat/Run Flow message 또는 state 안에서 자동 추론합니다.

## Outputs

| Output | Use |
| --- | --- |
| `03 Report Response Builder.Message` | Chat Output |
| `03 Report Response Builder.API Response` | Session State Writer 또는 API/Data output |
