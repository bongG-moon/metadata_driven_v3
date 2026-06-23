# Table Catalog Authoring Flow Connection Guide

이 flow는 사용자가 자연어로 데이터셋의 조회 방식, source, column, filter mapping을 등록할 수 있게 해줍니다.

긴 프롬프트 본문은 커스텀 컴포넌트가 아니라 Langflow 기본 `Prompt Template` 노드에서 관리합니다. `01/03/06 ... Variables Builder`는 Prompt Template에 넣을 값만 준비합니다.
아래 `.md` 파일들은 복사해서 Prompt Template 노드에 붙여 넣기 위한 참고 원본입니다. Langflow 실행 중 custom component가 로컬 `.md` 파일을 읽지 않습니다.
영문/한글 템플릿은 같은 input 변수만 사용하므로, 원하는 언어 버전 하나를 골라 붙여 넣으면 됩니다.

## Prompt Template Files

| Template node | English file | Korean file |
| --- | --- | --- |
| `01 Table Catalog Text Refinement Prompt Template` | `01_table_catalog_text_refinement_prompt_template.md` | `01_table_catalog_text_refinement_prompt_template_ko.md` |
| `03 Table Catalog Authoring Prompt Template` | `03_table_catalog_authoring_prompt_template.md` | `03_table_catalog_authoring_prompt_template_ko.md` |
| `06 Table Catalog Review Prompt Template` | `06_table_catalog_review_prompt_template.md` | `06_table_catalog_review_prompt_template_ko.md` |

## Nodes

| # | Node | Role |
| --- | --- | --- |
| 00 | `00 Table Catalog Authoring Request Loader` | 자연어 입력과 MongoDB 설정을 받아 기존 dataset 요약을 로드 |
| 01 | `01 Table Catalog Text Refinement Variables Builder` | 정제 Prompt Template의 `{raw_text}` 값 생성 |
| PT | `01 Table Catalog Text Refinement Prompt Template` | 자연어 정제 프롬프트 본문 |
| LLM | Gemini/LLM refinement node | 정제된 설명과 부족 정보 반환 |
| 02 | `02 Table Catalog Text Refinement Normalizer` | 정제 결과를 payload에 반영 |
| 03 | `03 Table Catalog Authoring Variables Builder` | 작성 Prompt Template의 `{authoring_context}` 값 생성 |
| PT | `03 Table Catalog Authoring Prompt Template` | MongoDB 저장용 table catalog JSON 생성 프롬프트 본문 |
| LLM | Gemini/LLM authoring node | `dataset_key/payload` item 생성 |
| 04 | `04 Table Catalog Authoring Result Normalizer` | authoring JSON을 저장 가능한 item으로 정규화 |
| 05 | `05 Table Catalog Similarity Checker` | 같은 dataset_key, 유사 source 역할, column 겹침 경고 생성 |
| 06 | `06 Table Catalog Review Variables Builder` | 검수 Prompt Template의 `{review_input_json}` 값 생성 |
| PT | `06 Table Catalog Review Prompt Template` | 저장 전 검증 프롬프트 본문 |
| LLM | Gemini/LLM review node | 저장 가능 여부와 보강 요청 반환 |
| 07 | `07 Table Catalog Review Writer` | 검증 통과 시 MongoDB upsert |
| 08 | `08 Table Catalog Authoring Response Builder` | Playground/API 응답 생성 |

## Required Connections

| # | From node | From output | To node | To input |
| --- | --- | --- | --- | --- |
| 1 | `Chat Input` or `Text Input` | text | `00 Table Catalog Authoring Request Loader` | `raw_text` |
| 2 | Text input | MongoDB URI | `00 Table Catalog Authoring Request Loader` | `mongo_uri` |
| 3 | Text input | DB name | `00 Table Catalog Authoring Request Loader` | `mongo_database` |
| 4 | Text input | full collection name, e.g. `agent_v3_table_catalog_items` | `00 Table Catalog Authoring Request Loader` | `collection_name` |
| 5 | `00 Table Catalog Authoring Request Loader` | `payload_out` | `01 Table Catalog Text Refinement Variables Builder` | `payload` |
| 6 | `01 Table Catalog Text Refinement Variables Builder` | `raw_text` | `01 Table Catalog Text Refinement Prompt Template` | `raw_text` |
| 7 | `01 Table Catalog Text Refinement Prompt Template` | prompt/message output | Gemini/LLM refinement node | prompt/message input |
| 8 | `00 Table Catalog Authoring Request Loader` | `payload_out` | `02 Table Catalog Text Refinement Normalizer` | `payload` |
| 9 | Gemini/LLM refinement node | text/message output | `02 Table Catalog Text Refinement Normalizer` | `llm_response` |
| 10 | `02 Table Catalog Text Refinement Normalizer` | `payload_out` | `03 Table Catalog Authoring Variables Builder` | `payload` |
| 11 | `03 Table Catalog Authoring Variables Builder` | `authoring_context` | `03 Table Catalog Authoring Prompt Template` | `authoring_context` |
| 12 | `03 Table Catalog Authoring Prompt Template` | prompt/message output | Gemini/LLM authoring node | prompt/message input |
| 13 | `02 Table Catalog Text Refinement Normalizer` | `payload_out` | `04 Table Catalog Authoring Result Normalizer` | `payload` |
| 14 | Gemini/LLM authoring node | text/message output | `04 Table Catalog Authoring Result Normalizer` | `llm_response` |
| 15 | `04 Table Catalog Authoring Result Normalizer` | `payload_out` | `05 Table Catalog Similarity Checker` | `payload` |
| 16 | `05 Table Catalog Similarity Checker` | `payload_out` | `06 Table Catalog Review Variables Builder` | `payload` |
| 17 | `06 Table Catalog Review Variables Builder` | `review_input_json` | `06 Table Catalog Review Prompt Template` | `review_input_json` |
| 18 | `06 Table Catalog Review Prompt Template` | prompt/message output | Gemini/LLM review node | prompt/message input |
| 19 | `05 Table Catalog Similarity Checker` | `payload_out` | `07 Table Catalog Review Writer` | `payload` |
| 20 | Gemini/LLM review node | text/message output | `07 Table Catalog Review Writer` | `llm_response` |
| 21 | Optional Text input | MongoDB URI override | `07 Table Catalog Review Writer` | `mongo_uri` |
| 22 | `07 Table Catalog Review Writer` | `payload_out` | `08 Table Catalog Authoring Response Builder` | `payload` |
| 23 | `08 Table Catalog Authoring Response Builder` | `message` | `Chat Output` | `message` |

## Required Dataset Information

`source_type`별 최소 정보는 아래와 같습니다.

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

`required_params`의 `DATE`는 위 예시 dataset의 query_template에 `{DATE}` 같은 실행 placeholder가 있을 때만 들어가는 값입니다.
필수 실행 변수가 없는 dataset이면 `required_params`는 `[]`이고, DATE가 단순 optional filter이면 `filter_mappings`에만 남깁니다.
