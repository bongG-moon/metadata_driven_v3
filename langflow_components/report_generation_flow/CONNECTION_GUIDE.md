# Report Generation Flow Connection Guide

`report_generation_flow`는 리포트 생성 요청을 별도 분기로 받기 위한 확장 flow입니다. 현재는 이전 분석 결과와 session state를 기반으로 리포트 초안 계획을 만들고, 이후 PPTX/Excel/Markdown 렌더러를 붙일 수 있는 구조입니다.

## Sequence

```text
Chat Input
-> 00 MongoDB Session State Loader
-> 00 Report Request Loader
-> 01 Report Outline Builder
-> 02 Report Data Selector
-> 03 Report Response Builder
-> Chat Output

parallel:
03 Report Response Builder.API Response -> 01 MongoDB Session State Writer
```

## Inputs

| Node | Input | Value |
| --- | --- | --- |
| `00 MongoDB Session State Loader` | `Question` | `Chat Input.Chat Message` 또는 Run Flow가 넘긴 text/message |
| `00 Report Request Loader` | `Question` | 같은 text/message |
| `00 Report Request Loader` | `Previous State` | `00 MongoDB Session State Loader.Loaded State` |

이 flow는 data_analysis_flow를 대신 실행하지 않습니다. 리포트에 필요한 데이터가 없으면 먼저 분석 flow를 실행해 결과와 `data_ref`를 만든 뒤 다시 호출하는 방식으로 확장합니다.

`Session ID`는 보통 비워둡니다. Chat Input/Run Flow message에 session id가 있으면 loader가 읽고, 없으면 단독 테스트용 fallback만 사용합니다.

기존 `Router Payload` 입력은 backend orchestrator 호환용입니다. Langflow canvas에서 직접 구성할 때는 기본 연결로 쓰지 않아도 됩니다.

## Outputs and Session Writer

| Node output | Use |
| --- | --- |
| `03 Report Response Builder.API Response` | `01 MongoDB Session State Writer.Response Payload` |
| `03 Report Response Builder.Message` | Chat Output 표시용 |
