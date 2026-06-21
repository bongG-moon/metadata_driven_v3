# Main Flow Filter Authoring Flow Connection Guide

이 flow는 현업 사용자가 자연어로 날짜, 공정, 제품, LOT, 상태, 장비 같은 주요 parameter/filter 정보를 등록할 수 있게 해줍니다.

## Nodes

| # | Node | Role |
| --- | --- | --- |
| 00 | `00 Main Flow Filter Authoring Request Loader` | 사용자 자연어와 MongoDB 설정을 받아 기존 filter 요약을 로드 |
| 01 | `01 Main Flow Filter Text Refinement Prompt Builder` | 자연어 정제용 prompt 생성 |
| LLM | Gemini/LLM refinement node | 정제된 설명과 부족 정보 반환 |
| 02 | `02 Main Flow Filter Text Refinement Normalizer` | 정제 결과를 payload에 반영 |
| 03 | `03 Main Flow Filter Authoring Prompt Builder` | MongoDB 저장용 filter JSON 생성 prompt 생성 |
| LLM | Gemini/LLM authoring node | `filter_key/payload` item 생성 |
| 04 | `04 Main Flow Filter Authoring Result Normalizer` | authoring JSON을 저장 가능한 item으로 정규화 |
| 05 | `05 Main Flow Filter Similarity Checker` | 같은 filter_key, alias/column 겹침 경고 생성 |
| 06 | `06 Main Flow Filter Review Prompt Builder` | 저장 전 검증 prompt 생성 |
| LLM | Gemini/LLM review node | 저장 가능 여부와 보강 요청 반환 |
| 07 | `07 Main Flow Filter Review Writer` | 검증 통과 시 MongoDB upsert |
| 08 | `08 Main Flow Filter Authoring Response Builder` | Playground/API 응답 생성 |

## Required Connections

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | `Chat Input` or Text input | natural language text | `00 Main Flow Filter Authoring Request Loader` | `raw_text` |
| 2 | Text input | MongoDB URI | `00 Main Flow Filter Authoring Request Loader` | `mongo_uri` |
| 3 | Text input | DB name | `00 Main Flow Filter Authoring Request Loader` | `mongo_database` |
| 4 | Text input | full collection name, e.g. `agent_v3_main_flow_filters` | `00 Main Flow Filter Authoring Request Loader` | `collection_name` |
| 5 | `00 Main Flow Filter Authoring Request Loader` | `payload_out` | `01 Main Flow Filter Text Refinement Prompt Builder` | `payload` |
| 6 | `01 Main Flow Filter Text Refinement Prompt Builder` | `refinement_prompt` | Gemini/LLM refinement node | prompt/message input |
| 7 | `00 Main Flow Filter Authoring Request Loader` | `payload_out` | `02 Main Flow Filter Text Refinement Normalizer` | `payload` |
| 8 | Gemini/LLM refinement node | text/message output | `02 Main Flow Filter Text Refinement Normalizer` | `llm_response` |
| 9 | `02 Main Flow Filter Text Refinement Normalizer` | `payload_out` | `03 Main Flow Filter Authoring Prompt Builder` | `payload` |
| 10 | `03 Main Flow Filter Authoring Prompt Builder` | `authoring_prompt` | Gemini/LLM authoring node | prompt/message input |
| 11 | `02 Main Flow Filter Text Refinement Normalizer` | `payload_out` | `04 Main Flow Filter Authoring Result Normalizer` | `payload` |
| 12 | Gemini/LLM authoring node | text/message output | `04 Main Flow Filter Authoring Result Normalizer` | `llm_response` |
| 13 | `04 Main Flow Filter Authoring Result Normalizer` | `payload_out` | `05 Main Flow Filter Similarity Checker` | `payload` |
| 14 | `05 Main Flow Filter Similarity Checker` | `payload_out` | `06 Main Flow Filter Review Prompt Builder` | `payload` |
| 15 | `06 Main Flow Filter Review Prompt Builder` | `review_prompt` | Gemini/LLM review node | prompt/message input |
| 16 | `05 Main Flow Filter Similarity Checker` | `payload_out` | `07 Main Flow Filter Review Writer` | `payload` |
| 17 | Gemini/LLM review node | text/message output | `07 Main Flow Filter Review Writer` | `llm_response` |
| 18 | Optional Text input | MongoDB URI override | `07 Main Flow Filter Review Writer` | `mongo_uri` |
| 19 | Dropdown input | `use_payload`, `ask`, `merge`, `replace`, `skip`, `create_new` | `07 Main Flow Filter Review Writer` | `duplicate_action` |
| 20 | `07 Main Flow Filter Review Writer` | `payload_out` | `08 Main Flow Filter Authoring Response Builder` | `payload` |
| 21 | `08 Main Flow Filter Authoring Response Builder` | `message` | `Chat Output` | `message` |

## Required Filter Information

저장 가능한 filter item에는 최소 다음 정보가 필요합니다.

- `filter_key`
- `payload.aliases`
- `payload.column_candidates`
- `payload.semantic_role`

값 타입과 연산자는 누락 시 `value_type=string`, `value_shape=scalar`, `operator=eq`로 보수적으로 기본값을 넣습니다.

## MongoDB Shape

```json
{
  "_id": "main_flow_filter:DATE",
  "filter_key": "DATE",
  "status": "active",
  "payload": {
    "display_name": "기준일",
    "aliases": ["오늘", "금일", "작업일"],
    "column_candidates": ["WORK_DT", "DATE", "BASE_DT"],
    "semantic_role": "date",
    "value_type": "date",
    "value_shape": "scalar",
    "operator": "eq",
    "normalized_format": "YYYYMMDD"
  }
}
```
