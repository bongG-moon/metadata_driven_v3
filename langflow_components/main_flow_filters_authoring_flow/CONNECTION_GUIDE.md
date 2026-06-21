# Main Flow Filter Authoring Flow Connection Guide

이 flow는 사용자가 자연어로 날짜, 공정, 제품, LOT, 상태, 장비 같은 주요 parameter/filter 정보를 등록할 수 있게 해줍니다.

긴 프롬프트 본문은 커스텀 컴포넌트가 아니라 Langflow 기본 `Prompt Template` 노드에서 관리합니다. `01/03/06 ... Variables Builder`는 Prompt Template에 넣을 값만 준비합니다.
아래 `.md` 파일들은 복사해서 Prompt Template 노드에 붙여 넣기 위한 참고 원본입니다. Langflow 실행 중 custom component가 로컬 `.md` 파일을 읽지 않습니다.
영문/한글 템플릿은 같은 input 변수만 사용하므로, 원하는 언어 버전 하나를 골라 붙여 넣으면 됩니다.

## Prompt Template Files

| Template node | English file | Korean file |
| --- | --- | --- |
| `01 Main Flow Filter Text Refinement Prompt Template` | `01_main_flow_filter_text_refinement_prompt_template.md` | `01_main_flow_filter_text_refinement_prompt_template_ko.md` |
| `03 Main Flow Filter Authoring Prompt Template` | `03_main_flow_filter_authoring_prompt_template.md` | `03_main_flow_filter_authoring_prompt_template_ko.md` |
| `06 Main Flow Filter Review Prompt Template` | `06_main_flow_filter_review_prompt_template.md` | `06_main_flow_filter_review_prompt_template_ko.md` |

## Nodes

| # | Node | Role |
| --- | --- | --- |
| 00 | `00 Main Flow Filter Authoring Request Loader` | 자연어 입력과 MongoDB 설정을 받아 기존 filter 요약을 로드 |
| 01 | `01 Main Flow Filter Text Refinement Variables Builder` | 정제 Prompt Template의 `{raw_text}` 값 생성 |
| PT | `01 Main Flow Filter Text Refinement Prompt Template` | 자연어 정제 프롬프트 본문 |
| LLM | Gemini/LLM refinement node | 정제된 설명과 부족 정보 반환 |
| 02 | `02 Main Flow Filter Text Refinement Normalizer` | 정제 결과를 payload에 반영 |
| 03 | `03 Main Flow Filter Authoring Variables Builder` | 작성 Prompt Template의 `{authoring_context}` 값 생성 |
| PT | `03 Main Flow Filter Authoring Prompt Template` | MongoDB 저장용 filter JSON 생성 프롬프트 본문 |
| LLM | Gemini/LLM authoring node | `filter_key/payload` item 생성 |
| 04 | `04 Main Flow Filter Authoring Result Normalizer` | authoring JSON을 저장 가능한 item으로 정규화 |
| 05 | `05 Main Flow Filter Similarity Checker` | 같은 filter_key, alias/column 겹침 경고 생성 |
| 06 | `06 Main Flow Filter Review Variables Builder` | 검수 Prompt Template의 `{review_input_json}` 값 생성 |
| PT | `06 Main Flow Filter Review Prompt Template` | 저장 전 검증 프롬프트 본문 |
| LLM | Gemini/LLM review node | 저장 가능 여부와 보강 요청 반환 |
| 07 | `07 Main Flow Filter Review Writer` | 검증 통과 시 MongoDB upsert |
| 08 | `08 Main Flow Filter Authoring Response Builder` | Playground/API 응답 생성 |

## Required Connections

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | `Chat Input` or `Text Input` | text | `00 Main Flow Filter Authoring Request Loader` | `raw_text` |
| 2 | Text input | MongoDB URI | `00 Main Flow Filter Authoring Request Loader` | `mongo_uri` |
| 3 | Text input | DB name | `00 Main Flow Filter Authoring Request Loader` | `mongo_database` |
| 4 | Text input | full collection name, e.g. `agent_v3_main_flow_filters` | `00 Main Flow Filter Authoring Request Loader` | `collection_name` |
| 5 | `00 Main Flow Filter Authoring Request Loader` | `payload_out` | `01 Main Flow Filter Text Refinement Variables Builder` | `payload` |
| 6 | `01 Main Flow Filter Text Refinement Variables Builder` | `raw_text` | `01 Main Flow Filter Text Refinement Prompt Template` | `raw_text` |
| 7 | `01 Main Flow Filter Text Refinement Prompt Template` | prompt/message output | Gemini/LLM refinement node | prompt/message input |
| 8 | `00 Main Flow Filter Authoring Request Loader` | `payload_out` | `02 Main Flow Filter Text Refinement Normalizer` | `payload` |
| 9 | Gemini/LLM refinement node | text/message output | `02 Main Flow Filter Text Refinement Normalizer` | `llm_response` |
| 10 | `02 Main Flow Filter Text Refinement Normalizer` | `payload_out` | `03 Main Flow Filter Authoring Variables Builder` | `payload` |
| 11 | `03 Main Flow Filter Authoring Variables Builder` | `authoring_context` | `03 Main Flow Filter Authoring Prompt Template` | `authoring_context` |
| 12 | `03 Main Flow Filter Authoring Prompt Template` | prompt/message output | Gemini/LLM authoring node | prompt/message input |
| 13 | `02 Main Flow Filter Text Refinement Normalizer` | `payload_out` | `04 Main Flow Filter Authoring Result Normalizer` | `payload` |
| 14 | Gemini/LLM authoring node | text/message output | `04 Main Flow Filter Authoring Result Normalizer` | `llm_response` |
| 15 | `04 Main Flow Filter Authoring Result Normalizer` | `payload_out` | `05 Main Flow Filter Similarity Checker` | `payload` |
| 16 | `05 Main Flow Filter Similarity Checker` | `payload_out` | `06 Main Flow Filter Review Variables Builder` | `payload` |
| 17 | `06 Main Flow Filter Review Variables Builder` | `review_input_json` | `06 Main Flow Filter Review Prompt Template` | `review_input_json` |
| 18 | `06 Main Flow Filter Review Prompt Template` | prompt/message output | Gemini/LLM review node | prompt/message input |
| 19 | `05 Main Flow Filter Similarity Checker` | `payload_out` | `07 Main Flow Filter Review Writer` | `payload` |
| 20 | Gemini/LLM review node | text/message output | `07 Main Flow Filter Review Writer` | `llm_response` |
| 21 | Optional Text input | MongoDB URI override | `07 Main Flow Filter Review Writer` | `mongo_uri` |
| 22 | `07 Main Flow Filter Review Writer` | `payload_out` | `08 Main Flow Filter Authoring Response Builder` | `payload` |
| 23 | `08 Main Flow Filter Authoring Response Builder` | `message` | `Chat Output` | `message` |

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
