# Operations Diagnosis Flow Connection Guide

`operations_diagnosis_flow`는 병목, 이상 징후, 목표 미달, 장비 이슈 같은 운영 진단 요청을 별도 분기로 받기 위한 확장 flow입니다. 현재는 질문과 이전 분석 state에서 신호를 수집하고, 후속 조회/조치 추천을 만드는 구조입니다.

## Sequence

```text
Chat Input
-> 00 MongoDB Session State Loader
-> 00 Diagnosis Request Loader
-> 01 Diagnosis Signal Collector
-> 02 Diagnosis Rule Evaluator
-> 03 Diagnosis Response Builder
-> Chat Output

parallel:
03 Diagnosis Response Builder.API Response -> 01 MongoDB Session State Writer
```

## Inputs

| Node | Input | Value |
| --- | --- | --- |
| `00 MongoDB Session State Loader` | `Question` | `Chat Input.Chat Message` 또는 Run Flow가 넘긴 text/message |
| `00 Diagnosis Request Loader` | `Question` | 같은 text/message |
| `00 Diagnosis Request Loader` | `Previous State` | `00 MongoDB Session State Loader.Loaded State` |

`Session ID`는 보통 비워둡니다. Chat Input/Run Flow message에 session id가 있으면 loader가 읽고, 없으면 단독 테스트용 fallback만 사용합니다.

기존 `Router Payload` 입력은 backend orchestrator 호환용입니다. Langflow canvas에서 직접 구성할 때는 기본 연결로 쓰지 않아도 됩니다.

## Outputs and Session Writer

| Node output | Use |
| --- | --- |
| `03 Diagnosis Response Builder.API Response` | `01 MongoDB Session State Writer.Response Payload` |
| `03 Diagnosis Response Builder.Message` | Chat Output 표시용 |

## Extension Point

`01 Diagnosis Signal Collector` 뒤에 실제 source 조회나 `data_analysis_flow` Run Flow 호출을 붙일 수 있습니다.

예:

- WIP 증가 신호가 있으면 공정별 WIP/생산량 조회를 요청
- 목표 미달 신호가 있으면 target/production 달성률 분석을 요청
- 장비 이슈 신호가 있으면 장비 현황 detail과 장비 대수 분석을 분리 호출
