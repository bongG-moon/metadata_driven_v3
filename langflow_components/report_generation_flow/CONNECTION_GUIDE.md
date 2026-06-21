# Report Generation Flow Connection Guide

`report_generation_flow`는 사용자의 리포트 작성 요청 하나를 받아 필요한 분석 범위와 리포트 구성을 결정하는 독립 E2E 업무 subflow입니다. 예시 질문은 "방금 결과로" 같은 후속 요청보다, 처음부터 완성 리포트를 요구하는 형태로 작성합니다.

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

`00 Report Request Loader`에는 `Question`과 `Previous State`만 남아 있습니다. session id는 Chat/API message 또는 state 안에서 자동 추론합니다.

## E2E Test Questions

아래 질문들은 `report_generation_flow`가 선택되어야 하는 대표 예시입니다.

```text
오늘 DA공정 일일 운영 리포트 만들어줘

오늘 WB공정 기준으로 생산량, 재공, 목표 달성률을 포함한 요약 리포트 만들어줘

오늘 HBM 제품군의 생산 실적, 재공 현황, 목표 대비 차이를 리포트로 정리해줘

오늘 DA/WB공정의 주요 이상 징후와 우선 확인 항목을 포함해서 운영 리포트 작성해줘
```

이 예시들의 의도는 `report_generation_flow` 안에서 리포트 목적, 필요한 지표, 데이터 확보 계획, 섹션 구성, 최종 메시지/API 응답까지 이어지는 것입니다. 후속 state 재사용은 나중에 확장할 수 있지만, 현재 예시 기준은 신규 E2E 리포트 요청입니다.

## Outputs

| Output | Use |
| --- | --- |
| `03 Report Response Builder.Message` | Chat Output |
| `03 Report Response Builder.API Response` | Session State Writer 또는 API/Data output |
