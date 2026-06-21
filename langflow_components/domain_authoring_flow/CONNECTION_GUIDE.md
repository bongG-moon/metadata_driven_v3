# Domain Authoring Flow Connection Guide

이 flow는 현업 사용자가 자연어로 공정 그룹, 제품 용어, 수량 용어, 지표, 상태 용어, 제품 key column 같은 domain metadata를 추가/수정할 수 있게 해줍니다.

## Nodes

| # | Node | Role |
| --- | --- | --- |
| 00 | `00 Domain Authoring Request Loader` | 사용자 자연어와 MongoDB 설정을 받아 기존 domain item 요약을 로드 |
| 01 | `01 Domain Text Refinement Prompt Builder` | 자연어 정제용 prompt 생성 |
| LLM | Gemini/LLM refinement node | 정제된 설명과 부족 정보 반환 |
| 02 | `02 Domain Text Refinement Normalizer` | 정제 결과를 payload에 반영 |
| 03 | `03 Domain Authoring Prompt Builder` | MongoDB 저장용 domain JSON 생성 prompt 생성 |
| LLM | Gemini/LLM authoring node | `section/key/payload` item 생성 |
| 04 | `04 Domain Authoring Result Normalizer` | authoring JSON을 저장 가능한 item으로 정규화 |
| 05 | `05 Domain Similarity Checker` | 같은 key, alias 겹침, process 겹침 경고 생성 |
| 06 | `06 Domain Review Prompt Builder` | 저장 전 검증 prompt 생성 |
| LLM | Gemini/LLM review node | 저장 가능 여부와 보강 요청 반환 |
| 07 | `07 Domain Review Writer` | 검증 통과 시 MongoDB upsert |
| 08 | `08 Domain Authoring Response Builder` | Playground/API 응답 생성 |

## Required Connections

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | `Chat Input` or Text input | natural language text | `00 Domain Authoring Request Loader` | `raw_text` |
| 2 | Text input | MongoDB URI | `00 Domain Authoring Request Loader` | `mongo_uri` |
| 3 | Text input | DB name | `00 Domain Authoring Request Loader` | `mongo_database` |
| 4 | Text input | full collection name, e.g. `agent_v3_domain_items` | `00 Domain Authoring Request Loader` | `collection_name` |
| 5 | `00 Domain Authoring Request Loader` | `payload_out` | `01 Domain Text Refinement Prompt Builder` | `payload` |
| 6 | `01 Domain Text Refinement Prompt Builder` | `refinement_prompt` | Gemini/LLM refinement node | prompt/message input |
| 7 | `00 Domain Authoring Request Loader` | `payload_out` | `02 Domain Text Refinement Normalizer` | `payload` |
| 8 | Gemini/LLM refinement node | text/message output | `02 Domain Text Refinement Normalizer` | `llm_response` |
| 9 | `02 Domain Text Refinement Normalizer` | `payload_out` | `03 Domain Authoring Prompt Builder` | `payload` |
| 10 | `03 Domain Authoring Prompt Builder` | `authoring_prompt` | Gemini/LLM authoring node | prompt/message input |
| 11 | `02 Domain Text Refinement Normalizer` | `payload_out` | `04 Domain Authoring Result Normalizer` | `payload` |
| 12 | Gemini/LLM authoring node | text/message output | `04 Domain Authoring Result Normalizer` | `llm_response` |
| 13 | `04 Domain Authoring Result Normalizer` | `payload_out` | `05 Domain Similarity Checker` | `payload` |
| 14 | `05 Domain Similarity Checker` | `payload_out` | `06 Domain Review Prompt Builder` | `payload` |
| 15 | `06 Domain Review Prompt Builder` | `review_prompt` | Gemini/LLM review node | prompt/message input |
| 16 | `05 Domain Similarity Checker` | `payload_out` | `07 Domain Review Writer` | `payload` |
| 17 | Gemini/LLM review node | text/message output | `07 Domain Review Writer` | `llm_response` |
| 18 | Optional Text input | MongoDB URI override | `07 Domain Review Writer` | `mongo_uri` |
| 19 | Dropdown input | `use_payload`, `ask`, `merge`, `replace`, `skip`, `create_new` | `07 Domain Review Writer` | `duplicate_action` |
| 20 | `07 Domain Review Writer` | `payload_out` | `08 Domain Authoring Response Builder` | `payload` |
| 21 | `08 Domain Authoring Response Builder` | `message` | `Chat Output` | `message` |

## Duplicate Handling

- 기본값은 `ask`입니다.
- 같은 `section/key`가 있으면 저장하지 않고 `merge`, `replace`, `skip`, `create_new` 중 선택하라는 응답을 반환합니다.
- `00`의 `duplicate_action` dropdown은 기본값 `ask`이고, `05`/`07`의 override dropdown은 기본값 `use_payload`입니다.
- 사용자가 선택한 뒤 같은 입력을 다시 실행할 때 `00` 또는 `07`의 `duplicate_action`에서 선택값을 고릅니다.
- `merge`는 기존 doc과 새 payload를 병합하고, list는 중복 제거합니다.
- `replace`는 같은 key의 doc을 새 내용으로 교체합니다.

## MongoDB Shape

```json
{
  "_id": "domain:process_groups:DA",
  "section": "process_groups",
  "key": "DA",
  "status": "active",
  "payload": {
    "display_name": "D/A",
    "aliases": ["DA", "D/A"],
    "processes": ["D/A1", "D/A2"]
  }
}
```
