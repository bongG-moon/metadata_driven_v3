# Langflow Implementation Guide

이 문서는 metadata-driven manufacturing agent를 Langflow 기반으로 구현할 때 지켜야 할 구현 방향을 정리한다.

## Goal

이 agent는 특정 제조 조직에만 묶이지 않아야 한다. 같은 Langflow flow 구조에서 `domain`, `table_catalog`, `main_flow_filters` metadata만 바꾸면 각 조직이 사용하는 업무 용어와 데이터 기준으로 조회와 분석이 가능해야 한다.

구현의 중심은 다음이다.

- 사용자의 실제 업무 용어를 metadata와 연결한다.
- 질문을 사람이 사고하듯 순서가 있는 실행 단계로 나눈다.
- 데이터 조회는 별도 retrieval flow가 담당한다.
- dummy data도 main flow shortcut이 아니라 `09 Dummy Data Retriever`를 통해 조회한다.
- 통합 분석과 계산은 pandas code로 수행한다.
- Gemini/LLM node는 Langflow 기본 LLM node를 사용한다.
- custom component는 standalone으로 작성하고, sibling helper import에 의존하지 않는다.

## Main Flow Order

실제 Langflow canvas에 붙일 권장 component 순서는 아래와 같다.

1. `00_request_state_loader.py`
2. optional first `01_mongodb_data_loader.py` only when previous state needs preview restore
3. `02_metadata_context_loader.py`
4. `03_route_candidate_builder.py`
5. `04_route_classifier_prompt_builder.py`
6. optional small route-classifier LLM node for ambiguous routes
7. `05_route_classifier_normalizer.py`
8. `06_metadata_qa_response_builder.py`
9. `07_intent_prompt_builder.py`
10. Gemini/LLM intent JSON node
11. `08_intent_plan_normalizer.py`
12. previous-result restore loader branch when full previous rows are required
13. `09`~`14` main flow source retriever nodes
14. `15_retrieval_payload_adapter.py`
15. `16_pandas_prompt_builder.py`
16. Gemini/LLM pandas code JSON node
17. `17_pandas_code_executor.py`
18. `18_mongodb_data_store.py`
19. `19_answer_prompt_builder.py`
20. Gemini/LLM final answer node
21. `20_answer_response_builder.py`
22. `21_answer_message_adapter.py`

LLM 없이 동작하는 deterministic 예시는 `langflow_components/demo_flow/`에 따로 둔다. 운영 권장 구조는 `router_flow/`가 질문 유형을 분류한 뒤 `metadata_qa_flow/`, `data_analysis_flow/`, `report_generation_flow/`, `operations_diagnosis_flow/` 중 필요한 flow를 backend orchestrator가 호출하는 split flow 방식이다.

## Retrieval Flow Choices

retrieval은 두 방식 중 하나를 쓴다.

### Dummy

```text
08 Intent Plan Normalizer.payload_out -> 09 Dummy Data Retriever.payload
08 Intent Plan Normalizer.payload_out -> 15 Retrieval Payload Adapter.main_payload
09 Dummy Data Retriever.retrieval_payload -> 15 Retrieval Payload Adapter.retrieval_payload
15 Retrieval Payload Adapter.payload -> 16 Pandas Prompt Builder.payload
15 Retrieval Payload Adapter.payload -> 17 Pandas Code Executor.payload
```

### Four Sources

```text
08 Intent Plan Normalizer.payload_out -> 10 Oracle Query Retriever.payload
08 Intent Plan Normalizer.payload_out -> 11 H-API Retriever.payload
08 Intent Plan Normalizer.payload_out -> 12 Datalake Retriever.payload
08 Intent Plan Normalizer.payload_out -> 13 Goodocs Retriever.payload
08 Intent Plan Normalizer.payload_out -> 15 Retrieval Payload Adapter.main_payload

10 Oracle Query Retriever.retrieval_payload -> 14 Source Retrieval Merger.oracle_retrieval
11 H-API Retriever.retrieval_payload -> 14 Source Retrieval Merger.h_api_retrieval
12 Datalake Retriever.retrieval_payload -> 14 Source Retrieval Merger.datalake_retrieval
13 Goodocs Retriever.retrieval_payload -> 14 Source Retrieval Merger.goodocs_retrieval

14 Source Retrieval Merger.retrieval_payload -> 15 Retrieval Payload Adapter.retrieval_payload
15 Retrieval Payload Adapter.payload -> 16 Pandas Prompt Builder.payload
15 Retrieval Payload Adapter.payload -> 17 Pandas Code Executor.payload
```

## LLM Placement

Langflow의 Gemini/LLM node는 세 위치에 둔다.

- Intent planning: `07 Intent Prompt Builder -> Gemini/LLM -> 08 Intent Plan Normalizer`
- Pandas code generation: `14 Pandas Prompt Builder -> Gemini/LLM -> 15 Pandas Code Executor`
- Pandas repair: `16A Pandas Repair Payload Builder -> 16B Pandas Repair Prompt Builder -> Gemini/LLM -> second 15 Pandas Code Executor`
- Final answer writing: `18 Answer Prompt Builder -> Gemini/LLM -> 19 Answer Response Builder`

LLM 출력은 그대로 신뢰하지 않는다. intent JSON은 normalizer에서 dataset key, source alias, params, filter scope를 metadata와 대조하고, pandas code JSON은 safety check를 통과한 뒤 in-memory DataFrame에만 실행한다.

## Intent Fallback Policy

`08 Intent Plan Normalizer`의 fallback은 LLM 출력이 일부 비어 있을 때 flow가 완전히 끊기지 않도록 하는 최소 보정 장치다. 특정 공정, 제품, 지표 계산식을 코드에 심어두는 용도가 아니다.

- `retrieval_jobs`가 비어 있으면 `analysis_kind`별 기본 dataset을 만들지 않는다. LLM이 JSON에 명시한 `datasets`만 사용해 metadata 기반 job shell을 만든다.
- `step_plan`이 비어 있으면 `rank_top_n`, `rank_bottom_n`, `detail_rows`처럼 어느 도메인에서도 공통으로 해석 가능한 최소 step만 만든다.
- `production_wip_target_rate`, `low_output_vs_target`, `overall_production_wip_target`, `date_split_production_plan_gap` 같은 지표 계산/조인 방식은 fallback 코드가 새로 만들지 않는다. 이런 로직은 domain/table/filter metadata와 LLM intent plan/pandas plan을 통해 전달되어야 한다.
- 질문에서 process/status/product 조건을 추정해야 할 때도 DA/WB/HBM 같은 값을 코드에 직접 고정하지 않고, `domain_items`의 alias/condition과 `main_flow_filters`에 등록된 filter key만 사용한다.

## Payload Contract

중간 payload는 compact하게 유지한다.

- `request`: session id, question, timezone
- `state`: `chat_history`, `context`, `current_data`
- `metadata`: domain, table catalog, main flow filters
- `intent_plan`: normalized intent, analysis kind, step plan
- `retrieval_jobs`: dataset별 조회 요청
- `runtime_sources`: `15 Retrieval Payload Adapter`가 만든 source rows. 같은 turn의 pandas 실행에 직접 전달한다.
- `runtime_source_refs`: 이전 turn에서 compact 저장된 source rows를 참조할 때만 사용한다.
- `source_results`: compact retrieval trace
- `analysis`: pandas 실행 결과
- `data`: 최종 사용자 표시 데이터
- `applied_scope`: 적용 dataset, filter, params, metadata refs
- `answer_message`: 최종 답변

`18 MongoDB Data Store`가 pandas 직후 `runtime_sources`와 `analysis.rows`를 MongoDB result collection의 `data_ref`로 compact한다. 그 다음 `20 Answer Response Builder`가 `runtime_sources`를 제거하고, `analysis.data_ref`를 최종 `data.data_ref`와 `state.current_data.data_ref`로 이어받는다. 운영 입력은 `result_collection_name`에 `agent_v3_result_store` 같은 full collection name을 직접 넣는다.

Langflow Playground에서 매번 각 노드의 result를 열어보지 않아도 되도록, `21_answer_message_adapter.py`는 최종 payload를 Chat Output용 Markdown으로 표시한다. 표시 내용은 payload를 새로 중복 저장하지 않고 기존 `answer_message`, `data`, `intent_plan`, `applied_scope`, `analysis`를 읽어서 만든다.

- 답변 내용
- 결과 테이블과 row count
- intent route, analysis kind, step plan, retrieval job
- pandas 실행 상태, reasoning step, LLM 생성 pandas code

## Standalone Component Rules

- 각 numbered custom component는 하나의 파일만 Langflow에 붙여도 동작해야 한다.
- `from reference_runtime import ...`, `from .utils import ...`, `from langflow_components... import ...` 같은 sibling/project import를 사용하지 않는다.
- 파일 최상위에 `class Something(Component)`가 있어야 한다.
- input 이름과 output 이름을 같은 component 안에서 겹치게 만들지 않는다.
- process-specific rule은 Python code보다 domain/table catalog/main flow filter metadata 또는 prompt contract에 둔다.

## Validation

기본 검증:

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v3
python -m pytest tests -q
python -m compileall -q reference_runtime langflow_components tools tests
```

Langflow Desktop component parser 검증:

```powershell
$py='C:\Users\qkekt\AppData\Local\com.LangflowDesktop\.langflow-venv\Scripts\python.exe'
$script=@'
from pathlib import Path
from lfx.custom.eval import eval_custom_component_code
root = Path(r'C:\Users\qkekt\Desktop\metadata_driven_v3\langflow_components')
for path in sorted(root.rglob('*.py')):
    code = path.read_text(encoding='utf-8')
    cls = eval_custom_component_code(code)
    instance = cls(_code=code)
print('init_ok')
'@
$script | & $py -
```

대표 smoke 질문은 `docs/LANGFLOW_NODE_CONNECTION_GUIDE.md`를 따른다.




