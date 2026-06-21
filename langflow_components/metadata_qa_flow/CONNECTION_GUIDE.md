# Metadata QA Flow Connection Guide

`metadata_qa_flow`는 등록된 데이터셋 목록, query template, 활용 예시, 컬럼 설명, domain metadata, greeting/help 질문만 처리하는 독립 subflow입니다. 실제 제조 데이터 조회나 pandas 분석은 `data_analysis_flow`에서 처리합니다.

## External Inputs

| External input | Connect to |
| --- | --- |
| 사용자 질문 | `00 MongoDB Session State Loader.Question`, `00 Metadata QA Request Loader.Question` |

metadata route나 router payload는 더 이상 00번 loader에 넣지 않습니다. `02 Metadata QA Response Builder`가 질문과 metadata를 보고 `catalog_list`, `dataset_query`, `dataset_examples`, `dataset_detail`, `domain_search`, `help/greeting` 중 하나를 내부에서 판단합니다.

## Recommended Wiring

```text
Chat Input.Chat Message
  -> 00 MongoDB Session State Loader.Question
  -> 00 Metadata QA Request Loader.Question

00 MongoDB Session State Loader.Loaded State
  -> 00 Metadata QA Request Loader.Previous State

00 Metadata QA Request Loader.Payload
  -> 01 Metadata Context Loader.Payload

01 Metadata Context Loader.Payload
  -> 02 Metadata QA Response Builder.Payload

02 Metadata QA Response Builder.Payload
  -> 03 Metadata QA Message Adapter.Payload
  -> 04 Metadata QA API Response Builder.Payload

03 Metadata QA Message Adapter.Message
  -> Chat Output

04 Metadata QA API Response Builder.API Response
  -> 01 MongoDB Session State Writer.Response Payload
```

`00 Metadata QA Request Loader`에는 `Question`과 `Previous State`만 남아 있습니다. session id는 Chat/Run Flow message 또는 state 안에서 자동 추론합니다.

## Outputs

| Output | Use |
| --- | --- |
| `03 Metadata QA Message Adapter.Message` | Chat Output |
| `04 Metadata QA API Response Builder.API Response` | Session State Writer 또는 API/Data output |
| `04 Metadata QA API Response Builder.API Message` | API response JSON을 message로 확인할 때만 사용 |

## Supported Actions

| Action | Behavior |
| --- | --- |
| `greeting` / `help` | 간단한 안내와 예시 질문 |
| `catalog_list` | 조회 가능한 dataset 목록 |
| `dataset_examples` | 특정 dataset 활용 질문 예시 |
| `dataset_detail` | 컬럼, 필터, source type, 필수 파라미터 등 상세 정보 |
| `dataset_query` | 등록된 query template/API 조회 정보 |
| `domain_search` | 등록된 domain/alias/condition 검색 |
