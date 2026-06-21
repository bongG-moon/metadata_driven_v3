# Metadata QA Flow Connection Guide

`metadata_qa_flow`는 등록된 데이터 카탈로그, query template, 활용 예시, domain metadata, greeting/help 질문만 답합니다. 실제 제조 데이터 조회, pandas 분석, MongoDB result 저장은 하지 않습니다.

## Sequence

```text
Chat Input
-> 00 MongoDB Session State Loader
-> 00 Metadata QA Request Loader
-> 01 Metadata Context Loader
-> 02 Metadata QA Response Builder
-> 03 Metadata QA Message Adapter
-> Chat Output

parallel:
02 Metadata QA Response Builder -> 04 Metadata QA API Response Builder -> 01 MongoDB Session State Writer
```

## Inputs

| Node | Input | Value |
| --- | --- | --- |
| `00 MongoDB Session State Loader` | `Question` | `Chat Input.Chat Message` 또는 Run Flow가 넘긴 text/message |
| `00 Metadata QA Request Loader` | `Question` | 같은 text/message |
| `00 Metadata QA Request Loader` | `Previous State` | `00 MongoDB Session State Loader.Loaded State` |

`Session ID`는 보통 비워둡니다. Chat Input/Run Flow message에 session id가 있으면 loader가 읽고, 없으면 단독 테스트용 fallback만 사용합니다.

기존 `Router Payload` 입력은 backend orchestrator 호환용입니다. Langflow canvas에서 직접 구성할 때는 기본 연결로 쓰지 않아도 됩니다.

## Outputs and Session Writer

| Node output | Use |
| --- | --- |
| `04 Metadata QA API Response Builder.API Response` | `01 MongoDB Session State Writer.Response Payload` |
| `03 Metadata QA Message Adapter.Message` | Chat Output 표시용 |

## Supported Actions

| metadata_action | Behavior |
| --- | --- |
| `greeting` / `help` | 간단한 안내와 예시 질문 |
| `catalog_list` | 조회 가능한 dataset 목록 |
| `dataset_examples` | 특정 dataset 활용 질문 예시 |
| `dataset_detail` | 컬럼, 필터, source type, 필수 파라미터 등 등록 상세 |
| `dataset_query` | 등록된 query template/API 조회 정보 |
| `domain_search` | 등록된 domain/alias/condition 검색 |
