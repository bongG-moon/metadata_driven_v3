# 02 Specialized Prompt 입력 가이드

이 문서는 `02 Intent Prompt Builder`의 `Specialized Prompt` 입력칸에 넣을 문장을 관리하기 위한 파일이다.

`Specialized Prompt`는 의도 분석 단계에서만 사용한다. pandas helper 함수나 실제 pandas 코드는 여기에 넣지 않는다. pandas helper 예시는 `14 Pandas Prompt Builder`의 `Specialized Functions` 입력칸에 넣는다.

## 붙여넣을 문장

`02_SPECIALIZED_INTENT_PROMPT.md`의 코드블록 안의 문장만 `02 Intent Prompt Builder > Specialized Prompt` 입력칸에 붙여넣는다.

## 관리 기준

- 02번 노드 기본 prompt에는 JSON schema, retrieval_jobs, step_plan, source_alias, date format 같은 공통 계약만 둔다.
- `02_SPECIALIZED_INTENT_PROMPT.md`에는 공정명, 공정 그룹, 제품 token, Lot/Hold, 장비, source별 scope 분리처럼 이 프로젝트/도메인에서만 중요한 규칙을 둔다.
- helper 함수 이름, pandas 코드, DataFrame 처리 로직은 이 파일에 넣지 않는다.
- 복잡한 pandas 절차가 필요하면 `pandas_function_cases` metadata에는 선택 힌트만 저장하고, 실제 helper 예시는 14번 노드의 `Specialized Functions` 입력에서 관리한다.
- 새 domain metadata를 추가하거나 바꿀 때는 `metadata/domain_items.json`을 직접 수정하지 않는다. `langflow_components/domain_authoring_flow/raw_text_input_example.md`에 자연어 입력 예시를 추가한 뒤 Domain Authoring Flow 또는 `tools/register_domain_from_raw_text_examples.py`로 저장하고, 저장 결과를 MongoDB에서 검증한다.
