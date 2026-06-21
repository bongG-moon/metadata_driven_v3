# Data Analysis Flow Connection Guide

`data_analysis_flow`는 실제 데이터 조회, pandas 분석, 결과 저장, 최종 답변 생성을 담당하는 독립 subflow입니다. main router는 이 flow를 선택만 하고, 이 flow에는 사용자 질문 하나를 Run Flow input으로 넘깁니다.

## External Inputs

Langflow 화면에서 외부에서 직접 넣는 값은 기본적으로 하나입니다.

| External input | Connect to |
| --- | --- |
| 사용자 질문 | `00 MongoDB Session State Loader.Question`, `00 Analysis Request Loader.Question` |

이전 대화 state는 외부에서 직접 넣지 않습니다. flow 내부의 session state loader가 같은 session의 state를 읽고, `Loaded State`를 request loader로 넘깁니다.

## Required Opening Wiring

```text
Chat Input.Chat Message
  -> 00 MongoDB Session State Loader.Question
  -> 00 Analysis Request Loader.Question

00 MongoDB Session State Loader.Loaded State
  -> 00 Analysis Request Loader.Previous State

00 Analysis Request Loader.Payload
  -> 01 Metadata Context Loader.Payload

01 Metadata Context Loader.Payload
  -> 02 Intent Prompt Builder.Payload

02 Intent Prompt Builder.Intent Prompt
  -> Intent LLM.Input

02 Intent Prompt Builder.Payload
  -> 03 Intent Plan Normalizer.Payload

Intent LLM.Output
  -> 03 Intent Plan Normalizer.Intent LLM Response
```

`00 Analysis Request Loader`에는 `Question`과 `Previous State`만 남아 있습니다. session id는 Chat/Run Flow message 또는 state 안에서 자동 추론합니다.

## Previous Result Restore

이전 결과 전체 row가 필요한 follow-up일 때만 MongoDB result store에서 full restore를 수행합니다.

```text
03 Intent Plan Normalizer.Payload
  -> 04 Previous Result Restore Router.Payload

04 Previous Result Restore Router.payload_out
  -> 06 Previous Result Restore Merger.main_payload

04 Previous Result Restore Router.restore_payload
  -> 05 MongoDB Data Loader.Payload
  -> 06 Previous Result Restore Merger.restored_payload
```

`04`가 restore가 필요 없다고 판단하면 `05 MongoDB Data Loader`는 실행하지 않고 `main_payload`만 `06`으로 보냅니다. 이 분기 덕분에 Langflow 화면에서 “이전 데이터 복원 여부”가 명확하게 보입니다.

## Source Retrieval

처음 검증은 dummy retriever만 연결해도 됩니다.

```text
06 Previous Result Restore Merger.payload_out
  -> 07 Dummy Data Retriever.Payload

07 Dummy Data Retriever.Retrieval Payload
  -> 12 Source Retrieval Merger.Dummy Retrieval
```

운영 source를 붙일 때는 같은 payload를 source별 retriever에 병렬로 연결합니다.

```text
06 Previous Result Restore Merger.payload_out
  -> 08 Oracle Query Retriever.Payload
  -> 09 H API Retriever.Payload
  -> 10 Datalake Retriever.Payload
  -> 11 Goodocs Retriever.Payload

08 Oracle Query Retriever.Retrieval Payload
  -> 12 Source Retrieval Merger.Oracle Retrieval
09 H API Retriever.Retrieval Payload
  -> 12 Source Retrieval Merger.H API Retrieval
10 Datalake Retriever.Retrieval Payload
  -> 12 Source Retrieval Merger.Datalake Retrieval
11 Goodocs Retriever.Retrieval Payload
  -> 12 Source Retrieval Merger.Goodocs Retrieval
```

각 retriever는 자기 `source_type`에 맞는 retrieval job이 없으면 `skipped=true`를 반환하고, merger는 skipped payload를 무시합니다.

## Pandas Analysis And Repair

```text
12 Source Retrieval Merger.Retrieval Payload
  -> 13 Retrieval Payload Adapter.Retrieval Payload

13 Retrieval Payload Adapter.Payload
  -> 14 Pandas Prompt Builder.Payload

14 Pandas Prompt Builder.Pandas Prompt
  -> Pandas Code LLM.Input

13 Retrieval Payload Adapter.Payload
  -> 15 Pandas Code Executor.Payload

Pandas Code LLM.Output
  -> 15 Pandas Code Executor.LLM Response

15 Pandas Code Executor.Payload Out
  -> 16A Pandas Repair Payload Builder.Payload

16A Pandas Repair Payload Builder.Payload Out
  -> 16B Pandas Repair Prompt Builder.Payload
  -> second 15 Pandas Code Executor.Payload

16B Pandas Repair Prompt Builder.Repair Prompt
  -> Pandas Repair LLM.Input

Pandas Repair LLM.Output
  -> second 15 Pandas Code Executor.LLM Response
```

`16B`는 repair prompt만 만드는 노드입니다. repair가 필요 없으면 `16A.payload_out`이 pass-through되고, 두 번째 executor는 원래 성공 payload를 그대로 다음 단계로 넘깁니다.

## Answer, Store, Output

```text
second 15 Pandas Code Executor.Payload Out
  -> 17 MongoDB Data Store.Payload
  -> 18 Answer Prompt Builder.Payload

18 Answer Prompt Builder.Answer Prompt
  -> Answer LLM.Input

17 MongoDB Data Store.Payload Out
  -> 19 Answer Response Builder.Payload

Answer LLM.Output
  -> 19 Answer Response Builder.Answer LLM Response

19 Answer Response Builder.Payload Out
  -> 20 Answer Message Adapter.Payload
  -> 21 API Response Builder.Payload

20 Answer Message Adapter.Message
  -> Chat Output

21 API Response Builder.API Response
  -> 01 MongoDB Session State Writer.Response Payload
```

결과 저장은 pandas 분석이 끝난 직후인 `17 MongoDB Data Store`에서 수행합니다. 최종 session state 저장은 `21 API Response Builder.API Response`를 writer에 연결합니다.
