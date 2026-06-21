# V2 Delivery Validation Report

검증 시각: 2026-06-13 KST

대상 폴더: `C:\Users\qkekt\Desktop\metadata_driven_v3`

## 구현 범위

- `docs/METADATA_AUTHORING_FLOW_GUIDE.md`와 `docs/DATA_RETRIEVAL_SOURCES.md`의 계약을 기준으로 독립 실행형 구현본을 구성했다.
- 원본 workspace의 `.env`를 복사했고, 민감값은 문서에 기록하지 않았다.
- Router/data analysis/metadata QA split flow, source retriever nodes, domain/table/filter authoring flow component를 포함했다.
- 각 numbered Langflow custom component는 standalone 파일로 유지한다.
- `README.md`, `pyproject.toml`, 일부 실행 guide의 로컬 경로, `LLM_IN_LOOP_VALIDATION_GUIDE.md`의 현재 검증 상태를 v2 기준으로 정리했다.

## 검증 결과

| Gate | Command | Result |
| --- | --- | --- |
| Python compile | `python -m compileall -q reference_runtime langflow_components tools tests` | PASS |
| Unit/contract tests | `python -m pytest tests -q` | PASS, 30 passed |
| Deterministic regression | `python tools\validate_regression.py` | PASS, 16/16 |
| MongoDB dry-run | `python tools\upload_json_to_mongodb.py --dry-run` | PASS |
| Environment check | `python tools\validate_env.py` | PASS |
| Gemini connection | `python tools\validate_gemini_connection.py` | PASS, `gemini-2.5-flash` |
| LLM smoke | `python tools\validate_llm_in_loop.py --limit 1` | PASS, 1/1 |
| Full LLM-in-the-loop | `python tools\validate_llm_in_loop.py` | PASS, 16/16 |

## Evidence

- Deterministic regression report: `validation_runs\20260613_000155\REPORT.md`
- LLM smoke report: `validation_runs\20260613_000324_llm\REPORT.md`
- Full LLM-in-the-loop report: `validation_runs\20260613_000738_llm\REPORT.md`

## MongoDB Dry-Run Summary

Dry-run target database: `datagov`

- `agent_v3_domain_items`: 21 docs
- `agent_v3_table_catalog_items`: 9 docs
- `agent_v3_main_flow_filters`: 18 docs

MongoDB metadata collection은 prefix 조합 대신 full name 3개(`agent_v3_domain_items`, `agent_v3_table_catalog_items`, `agent_v3_main_flow_filters`)를 직접 입력하는 계약을 따른다.

## 주요 회귀 질문 범위

`metadata/regression_questions.json`의 16개 질문을 deterministic runtime과 실제 Gemini LLM-in-the-loop 양쪽에서 검증했다.

- DA/WB 공정별 WIP rank 및 production join
- LOT hold history detail
- 현재 hold lot list
- DA WIP top product
- follow-up 장비 현황
- LPDDR5 W/B production and WIP
- DA WIP/production/target/achievement rate
- 목표/INPUT 계획 대비 저조 제품
- waiting lot count by process
- DA lot/wafer/die summary
- DA WIP은 `wip_today` 사용
- follow-up 이후 전체 WIP scope reset
- total production/WIP/target
- yesterday production vs today plan gap
- HBM equipment by model

## 남은 운영 확인 사항

현재 검증은 `RUN_LIVE_SOURCE_RETRIEVAL=false` 상태에서 dummy retrieval fallback과 실제 Gemini LLM 호출을 결합한 검증이다. Oracle, H-API, Datalake, Goodocs의 운영 endpoint와 credential을 붙이는 live source integration은 별도 환경에서 `RUN_LIVE_SOURCE_RETRIEVAL=true`로 확인해야 한다.
