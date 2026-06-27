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
