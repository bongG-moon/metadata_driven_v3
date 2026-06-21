# Langflow Implementation Guide

이 프로젝트는 metadata만 바꾸면 다른 업무에도 재사용할 수 있는 Langflow 기반 metadata-driven agent를 목표로 합니다. 특정 질문이나 특정 제조 조건을 Python 코드에 하드코딩하지 않고, domain/table/filter metadata와 LLM planning을 통해 동작하도록 구성합니다.

## Runtime Shape

현재 권장 runtime은 split flow 구조입니다.

```text
main router canvas
Chat Input
-> router_flow 00~05
-> 06 Selected Flow API Runner
-> Chat Output
```

각 하위 flow는 독립 실행 가능한 subflow입니다.

```text
subflow
Chat Input
-> 00 MongoDB Session State Loader
-> 00 Request Loader
-> subflow logic
-> Final API Response
-> 01 MongoDB Session State Writer

Final Message
-> Chat Output
```

main router는 어떤 flow를 실행할지 선택하고, 선택된 flow의 API 호출 정보만 만듭니다. state load/write, metadata QA 판단, data analysis 실행 준비는 각 subflow 안에서 처리합니다.

## Main Router Flow

| Node | Role |
| --- | --- |
| `00 Router Request Loader` | 질문을 route 판단 payload로 변환 |
| `01 Metadata Context Loader` | route 판단용 metadata 요약 로드 |
| `02 Route Candidate Builder` | rule 기반 route 후보와 LLM 필요 여부 생성 |
| `03A Route Prompt Context Builder` | 기본 Prompt Template용 route context 하나 생성 |
| Langflow Prompt Template | route/API catalog와 route classifier prompt 문장 관리 |
| Route Classifier LLM | 최종 route 판단 |
| `04 Route Classifier Normalizer` | route 결과 정규화 |
| `05 Orchestrator Response Builder` | `selected_flow`와 `subflow_call` 생성 |
| `06 Selected Flow API Runner` | 선택된 subflow 하나만 Langflow API로 호출 |

여러 native Run Flow output을 한 노드로 모으면 Langflow 실행기가 연결된 upstream을 모두 기다릴 수 있습니다. direct router canvas에서는 `05.Route Response -> 06.Selected Flow API Runner -> Chat Output`으로 연결합니다. `05.Route Response` 안에는 `subflow_call.api_url`, `subflow_call.input_value`, `subflow_call.session_id`가 들어가며, `06`은 이 값으로 선택된 subflow 하나만 호출합니다. Web backend는 router API 하나만 호출하며, 선택된 subflow API 호출은 router canvas 내부의 `06 Selected Flow API Runner`가 처리합니다.

## Data Analysis Flow

`data_analysis_flow`는 실제 데이터 조회, pandas 분석, result store 저장, 답변 생성을 담당합니다.

```text
00 Analysis Request Loader
-> 01 Metadata Context Loader
-> 02 Intent Prompt Builder
-> Intent LLM
-> 03 Intent Plan Normalizer
-> 04 Previous Result Restore Router
-> 05 MongoDB Data Loader, only when full restore is required
-> 06 Previous Result Restore Merger
-> 07~11 source retrievers
-> 12 Source Retrieval Merger
-> 13 Retrieval Payload Adapter
-> 14 Pandas Prompt Builder
-> Pandas Code LLM
-> 15 Pandas Code Executor
-> 16A/16B repair branch
-> second 15 Pandas Code Executor
-> 17 MongoDB Data Store
-> 18 Answer Prompt Builder
-> Answer LLM
-> 19 Answer Response Builder
-> 20 Answer Message Adapter
-> Chat Output
```

API/session state 저장 경로:

```text
19 Answer Response Builder.Payload
  -> 21 API Response Builder.Payload

21 API Response Builder.API Response
  -> 01 MongoDB Session State Writer.Response Payload
```

## Source Retrieval

검증 단계에서는 dummy retriever만 연결해도 됩니다.

```text
06 Previous Result Restore Merger.Payload
  -> 07 Dummy Data Retriever.Payload

07 Dummy Data Retriever.Retrieval Payload
  -> 12 Source Retrieval Merger.Dummy Retrieval
```

운영에서는 source type별 retriever를 병렬로 연결합니다. 각 retriever는 자기 source type에 맞는 retrieval job이 없으면 `skipped=true`를 반환하고, merger는 skipped payload를 무시합니다.

## LLM Placement

| Purpose | Connection |
| --- | --- |
| Route classification | `03A Route Prompt Context Builder -> Langflow Prompt Template -> Route Classifier LLM -> 04 Route Classifier Normalizer` |
| Intent planning | `02 Intent Prompt Builder -> Intent LLM -> 03 Intent Plan Normalizer` |
| Pandas code generation | `14 Pandas Prompt Builder -> Pandas Code LLM -> 15 Pandas Code Executor` |
| Pandas repair | `16B Pandas Repair Prompt Builder -> Pandas Repair LLM -> second 15 Pandas Code Executor` |
| Final answer writing | `18 Answer Prompt Builder -> Answer LLM -> 19 Answer Response Builder` |

LLM 출력은 그대로 신뢰하지 않습니다. route, intent JSON, pandas code는 normalizer/executor에서 metadata와 safety rule을 통과해야 합니다.

## Hardcoding Policy

- DA/WB/HBM 같은 업무 용어는 code에 직접 박지 않고 metadata alias/condition을 통해 해석합니다.
- 특정 질문 하나를 고치기 위해 executor에 후처리 예외를 넣지 않습니다.
- 제품 grain, rank group, filter column, output column은 질문 의도와 metadata를 기준으로 LLM plan/pandas prompt에서 결정하게 합니다.
- fallback은 flow가 멈추지 않기 위한 최소 보정만 수행합니다. 업무별 분석 로직을 새로 만들어내는 위치가 아닙니다.

## Payload Contract

중간 payload는 필요한 compact 정보만 담습니다.

| Field | Meaning |
| --- | --- |
| `request` | session id, question, timezone/date |
| `state` | chat history, context, current_data |
| `metadata` | domain, table catalog, main flow filters |
| `metadata_route` | router가 정규화한 route 결정 |
| `intent_plan` | normalized intent, analysis kind, step plan |
| `retrieval_jobs` | dataset별 조회 요청 |
| `runtime_sources` | 현재 turn pandas 실행에 쓰는 source rows |
| `runtime_source_refs` | compact state에서 복원 가능한 source refs |
| `source_results` | compact retrieval trace |
| `analysis` | pandas 실행 결과 |
| `data` | 최종 사용자 표시 데이터 |
| `applied_scope` | 적용 dataset/filter/params/metadata refs |
| `answer_message` | 최종 답변 |

## Standalone Component Rules

- 각 numbered custom component는 하나의 파일만 Langflow에 붙여도 동작해야 합니다.
- sibling/project helper import를 사용하지 않습니다.
- input 이름과 output 이름이 같은 component 안에서 겹치지 않게 합니다.
- process-specific rule은 Python code보다 metadata 또는 prompt contract로 둡니다.

## Validation

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v3
python -m compileall langflow_components tests tools
python -m pytest -q
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
