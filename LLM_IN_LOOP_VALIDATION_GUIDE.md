# LLM In The Loop Validation Guide

이 검증은 Langflow에서 의도한 실행 순서를 로컬 Python으로 동일하게 재현하기 위한 것이다.

실행 흐름:

1. 사용자 질문을 Gemini intent JSON으로 변환한다.
2. intent normalizer를 통과시켜 retrieval job을 확정한다.
3. dummy/MongoDB/API/파일 기반 retrieval executor로 데이터를 가져온다.
4. retrieval 결과를 Gemini pandas code JSON 생성 프롬프트에 전달한다.
5. 생성된 pandas 코드를 AST 기반 safety check로 검사한다.
6. 안전한 코드만 in-memory DataFrame에 대해 실행한다.
7. pandas 결과로 최종 answer payload와 다음 state를 만든다.

## 실행 파일

- `tools/validate_llm_in_loop.py`
- 보조 테스트: `tests/test_llm_validation_script.py`

## 필요한 환경변수

`.env` 또는 OS 환경변수에 아래 값이 필요하다.

- `LLM_API_KEY` 또는 `GOOGLE_API_KEY` 또는 `GEMINI_API_KEY`
- `LLM_MODEL_NAME`
- `LLM_TEMPERATURE`
- `AGENT_DEFAULT_DATE`
- `VALIDATION_LIMIT`

`VALIDATION_LIMIT=0` 또는 빈 값은 전체 케이스 실행을 의미한다.

## 주요 실행 명령

전체 회귀 질문 실행:

```powershell
python tools\validate_llm_in_loop.py
```

처음 1개만 smoke test:

```powershell
python tools\validate_llm_in_loop.py --limit 1 --fail-fast
```

특정 케이스만 실행:

```powershell
python tools\validate_llm_in_loop.py --case multi_step_rank_wip_with_production --fail-fast
```

여러 케이스 실행:

```powershell
python tools\validate_llm_in_loop.py --case today_da_wip_production_target_rate --case input_plan_vs_da_low_output --fail-fast
```

임의 질문 실행:

```powershell
python tools\validate_llm_in_loop.py --question "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘"
```

## 결과 위치

매 실행마다 아래 폴더가 생성된다.

```text
validation_runs\YYYYMMDD_HHMMSS_llm\
```

주요 파일:

- `REPORT.md`: 사람이 읽는 검증 요약
- `results.json`: intent JSON, normalized plan, generated pandas code, payload, check 결과

## 현재 확인된 상태

- safety/parser 단위 테스트: 통과
- deterministic regression 테스트: 통과
- LLM smoke 재검증: `validation_runs\20260613_000324_llm\REPORT.md` 기준 1/1 통과
- 전체 16개 LLM-in-the-loop 실행: `validation_runs\20260613_000738_llm\REPORT.md` 기준 16/16 통과

한도 오류도 이제 traceback으로 끝나지 않고 `REPORT.md`에 실패 사유로 저장된다.
