# Table Catalog Authoring Flow Connection Guide

이 flow는 현업 사용자가 자연어로 데이터셋의 조회 방식, source, column, filter mapping을 등록할 수 있게 해줍니다.

## Nodes

| # | Node | Role |
| --- | --- | --- |
| 00 | `00 Table Catalog Authoring Request Loader` | 사용자 자연어와 MongoDB 설정을 받아 기존 dataset 요약을 로드 |
| 01 | `01 Table Catalog Text Refinement Prompt Builder` | 자연어 정제용 prompt 생성 |
| LLM | Gemini/LLM refinement node | 정제된 설명과 부족 정보 반환 |
| 02 | `02 Table Catalog Text Refinement Normalizer` | 정제 결과를 payload에 반영 |
| 03 | `03 Table Catalog Authoring Prompt Builder` | MongoDB 저장용 table catalog JSON 생성 prompt 생성 |
| LLM | Gemini/LLM authoring node | `dataset_key/payload` item 생성 |
| 04 | `04 Table Catalog Authoring Result Normalizer` | authoring JSON을 저장 가능한 item으로 정규화 |
| 05 | `05 Table Catalog Similarity Checker` | 같은 dataset_key, 유사 source 역할, column 겹침 경고 생성 |
| 06 | `06 Table Catalog Review Prompt Builder` | 저장 전 검증 prompt 생성 |
| LLM | Gemini/LLM review node | 저장 가능 여부와 보강 요청 반환 |
| 07 | `07 Table Catalog Review Writer` | 검증 통과 시 MongoDB upsert |
| 08 | `08 Table Catalog Authoring Response Builder` | Playground/API 응답 생성 |

## Required Connections

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | `Chat Input` or Text input | natural language text | `00 Table Catalog Authoring Request Loader` | `raw_text` |
| 2 | Text input | MongoDB URI | `00 Table Catalog Authoring Request Loader` | `mongo_uri` |
| 3 | Text input | DB name | `00 Table Catalog Authoring Request Loader` | `mongo_database` |
| 4 | Text input | full collection name, e.g. `agent_v3_table_catalog_items` | `00 Table Catalog Authoring Request Loader` | `collection_name` |
| 5 | `00 Table Catalog Authoring Request Loader` | `payload_out` | `01 Table Catalog Text Refinement Prompt Builder` | `payload` |
| 6 | `01 Table Catalog Text Refinement Prompt Builder` | `refinement_prompt` | Gemini/LLM refinement node | prompt/message input |
| 7 | `00 Table Catalog Authoring Request Loader` | `payload_out` | `02 Table Catalog Text Refinement Normalizer` | `payload` |
| 8 | Gemini/LLM refinement node | text/message output | `02 Table Catalog Text Refinement Normalizer` | `llm_response` |
| 9 | `02 Table Catalog Text Refinement Normalizer` | `payload_out` | `03 Table Catalog Authoring Prompt Builder` | `payload` |
| 10 | `03 Table Catalog Authoring Prompt Builder` | `authoring_prompt` | Gemini/LLM authoring node | prompt/message input |
| 11 | `02 Table Catalog Text Refinement Normalizer` | `payload_out` | `04 Table Catalog Authoring Result Normalizer` | `payload` |
| 12 | Gemini/LLM authoring node | text/message output | `04 Table Catalog Authoring Result Normalizer` | `llm_response` |
| 13 | `04 Table Catalog Authoring Result Normalizer` | `payload_out` | `05 Table Catalog Similarity Checker` | `payload` |
| 14 | `05 Table Catalog Similarity Checker` | `payload_out` | `06 Table Catalog Review Prompt Builder` | `payload` |
| 15 | `06 Table Catalog Review Prompt Builder` | `review_prompt` | Gemini/LLM review node | prompt/message input |
| 16 | `05 Table Catalog Similarity Checker` | `payload_out` | `07 Table Catalog Review Writer` | `payload` |
| 17 | Gemini/LLM review node | text/message output | `07 Table Catalog Review Writer` | `llm_response` |
| 18 | Optional Text input | MongoDB URI override | `07 Table Catalog Review Writer` | `mongo_uri` |
| 19 | Dropdown input | `use_payload`, `ask`, `merge`, `replace`, `skip`, `create_new` | `07 Table Catalog Review Writer` | `duplicate_action` |
| 20 | `07 Table Catalog Review Writer` | `payload_out` | `08 Table Catalog Authoring Response Builder` | `payload` |
| 21 | `08 Table Catalog Authoring Response Builder` | `message` | `Chat Output` | `message` |

## Required Dataset Information

`source_type`별로 최소한 다음 정보가 있어야 저장됩니다.

| source_type | Required source_config |
| --- | --- |
| `oracle` | `db_key`, `query_template` |
| `h_api` | `api_url` |
| `datalake` | `query_template` |
| `goodocs` | `doc_id` (`sheet_name`은 특정 시트를 고정해서 읽을 때만 선택 입력) |
| `dummy` | 운영용이 아니면 최소 `columns`, `dataset_family` |

## MongoDB Shape

```json
{
  "_id": "table_catalog:wip_today",
  "dataset_key": "wip_today",
  "status": "active",
  "payload": {
    "display_name": "WIP Today",
    "dataset_family": "wip",
    "source_type": "oracle",
    "source_config": {"source_type": "oracle", "db_key": "PNT_RPT", "query_template": "SELECT ..."},
    "required_params": ["DATE"],
    "filter_mappings": {"DATE": ["WORK_DT"]},
    "columns": ["WORK_DT", "OPER_NAME", "WIP"]
  }
}
```
