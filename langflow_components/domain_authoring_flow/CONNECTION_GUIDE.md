# Domain Authoring Flow Connection Guide

이 flow는 사용자가 자연어로 입력한 공정 그룹, 제품 용어, 수량/지표 용어, 상태 용어, 제품 key column 같은 domain metadata를 MongoDB에 등록합니다.

긴 프롬프트 본문은 커스텀 컴포넌트가 아니라 Langflow 기본 `Prompt Template` 노드에서 관리합니다. `01/03/06 ... Variables Builder`는 Prompt Template에 넣을 값만 준비합니다.
아래 `.md` 파일들은 복사해서 Prompt Template 노드에 붙여 넣기 위한 참고 원본입니다. Langflow 실행 중 custom component가 로컬 `.md` 파일을 읽지 않습니다.
영문/한글 템플릿은 같은 input 변수만 사용하므로, 원하는 언어 버전 하나를 골라 붙여 넣으면 됩니다.

## Prompt Template Files

| Template node | English file | Korean file |
| --- | --- | --- |
| `01 Domain Text Refinement Prompt Template` | `01_domain_text_refinement_prompt_template.md` | `01_domain_text_refinement_prompt_template_ko.md` |
| `03 Domain Authoring Prompt Template` | `03_domain_authoring_prompt_template.md` | `03_domain_authoring_prompt_template_ko.md` |
| `06 Domain Review Prompt Template` | `06_domain_review_prompt_template.md` | `06_domain_review_prompt_template_ko.md` |

## Nodes

| # | Node | Role |
| --- | --- | --- |
| 00 | `00 Domain Authoring Request Loader` | 자연어 입력과 MongoDB 설정을 받아 기존 domain item 요약을 로드 |
| 01 | `01 Domain Text Refinement Variables Builder` | 정제 Prompt Template의 `{raw_text}` 값 생성 |
| PT | `01 Domain Text Refinement Prompt Template` | 자연어 정제 프롬프트 본문 |
| LLM | Gemini/LLM refinement node | 정제된 설명과 부족 정보 반환 |
| 02 | `02 Domain Text Refinement Normalizer` | 정제 결과를 payload에 반영 |
| 03 | `03 Domain Authoring Variables Builder` | 작성 Prompt Template의 `{authoring_context}` 값 생성 |
| PT | `03 Domain Authoring Prompt Template` | MongoDB 저장용 domain JSON 생성 프롬프트 본문 |
| LLM | Gemini/LLM authoring node | `section/key/payload` item 생성 |
| 04 | `04 Domain Authoring Result Normalizer` | authoring JSON을 저장 가능한 item으로 정규화 |
| 05 | `05 Domain Similarity Checker` | 같은 key, alias 겹침, process 겹침 경고 생성 |
| 06 | `06 Domain Review Variables Builder` | 검수 Prompt Template의 `{review_input_json}` 값 생성 |
| PT | `06 Domain Review Prompt Template` | 저장 전 검증 프롬프트 본문 |
| LLM | Gemini/LLM review node | 저장 가능 여부와 보강 요청 반환 |
| 07 | `07 Domain Review Writer` | 검증 통과 시 MongoDB upsert |
| 08 | `08 Domain Authoring Response Builder` | Playground/API 응답 생성 |

## Required Connections

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | `Chat Input` or `Text Input` | text | `00 Domain Authoring Request Loader` | `raw_text` |
| 2 | Text input | MongoDB URI | `00 Domain Authoring Request Loader` | `mongo_uri` |
| 3 | Text input | DB name | `00 Domain Authoring Request Loader` | `mongo_database` |
| 4 | Text input | full collection name, e.g. `agent_v3_domain_items` | `00 Domain Authoring Request Loader` | `collection_name` |
| 5 | `00 Domain Authoring Request Loader` | `payload_out` | `01 Domain Text Refinement Variables Builder` | `payload` |
| 6 | `01 Domain Text Refinement Variables Builder` | `raw_text` | `01 Domain Text Refinement Prompt Template` | `raw_text` |
| 7 | `01 Domain Text Refinement Prompt Template` | prompt/message output | Gemini/LLM refinement node | prompt/message input |
| 8 | `00 Domain Authoring Request Loader` | `payload_out` | `02 Domain Text Refinement Normalizer` | `payload` |
| 9 | Gemini/LLM refinement node | text/message output | `02 Domain Text Refinement Normalizer` | `llm_response` |
| 10 | `02 Domain Text Refinement Normalizer` | `payload_out` | `03 Domain Authoring Variables Builder` | `payload` |
| 11 | `03 Domain Authoring Variables Builder` | `authoring_context` | `03 Domain Authoring Prompt Template` | `authoring_context` |
| 12 | `03 Domain Authoring Prompt Template` | prompt/message output | Gemini/LLM authoring node | prompt/message input |
| 13 | `02 Domain Text Refinement Normalizer` | `payload_out` | `04 Domain Authoring Result Normalizer` | `payload` |
| 14 | Gemini/LLM authoring node | text/message output | `04 Domain Authoring Result Normalizer` | `llm_response` |
| 15 | `04 Domain Authoring Result Normalizer` | `payload_out` | `05 Domain Similarity Checker` | `payload` |
| 16 | `05 Domain Similarity Checker` | `payload_out` | `06 Domain Review Variables Builder` | `payload` |
| 17 | `06 Domain Review Variables Builder` | `review_input_json` | `06 Domain Review Prompt Template` | `review_input_json` |
| 18 | `06 Domain Review Prompt Template` | prompt/message output | Gemini/LLM review node | prompt/message input |
| 19 | `05 Domain Similarity Checker` | `payload_out` | `07 Domain Review Writer` | `payload` |
| 20 | Gemini/LLM review node | text/message output | `07 Domain Review Writer` | `llm_response` |
| 21 | Optional Text input | MongoDB URI override | `07 Domain Review Writer` | `mongo_uri` |
| 22 | `07 Domain Review Writer` | `payload_out` | `08 Domain Authoring Response Builder` | `payload` |
| 23 | `08 Domain Authoring Response Builder` | `message` | `Chat Output` | `message` |

## Duplicate Handling

- 기본값은 `ask`입니다.
- `00`의 `duplicate_action`은 사용자가 처음부터 처리 방식을 지정할 때 사용합니다.
- `05`의 `duplicate_action`은 기존 payload 결정을 그대로 쓸지, 이번 실행에서만 강제로 `merge`, `replace`, `skip`, `create_new`를 쓸지 정합니다.
- `07`은 별도 duplicate option을 받지 않고 `05`가 만든 `duplicate_decision.action`만 실행합니다.
- 같은 `section/key`가 있고 action이 `ask`이면 저장하지 않고 사용자에게 선택을 요청합니다.

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
