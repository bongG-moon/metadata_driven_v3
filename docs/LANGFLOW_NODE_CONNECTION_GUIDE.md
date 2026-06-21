# Langflow Node Connection Guide Index

현재 권장 운영 구조는 `router_flow`가 앞에서 질문 유형을 분류하고, backend orchestrator가 목적별 하위 flow를 호출하는 방식입니다.

## Recommended Runtime Flows

전체 router + Run Flow + session state 저장 연결은 `docs/ROUTED_RUN_FLOW_SESSION_WIRING_GUIDE.md`를 먼저 봅니다.

| Flow | Role | Detailed guide |
| --- | --- | --- |
| Router | 질문 유형 분류와 하위 flow 선택 | `langflow_components/router_flow/CONNECTION_GUIDE.md` |
| Metadata QA | 데이터 카탈로그, query template, 활용 예시, domain 정보 답변 | `langflow_components/metadata_qa_flow/CONNECTION_GUIDE.md` |
| Data Analysis | 실제 데이터 조회, pandas 분석, result store 저장, 최종 답변 | `langflow_components/data_analysis_flow/CONNECTION_GUIDE.md` |
| Report Generation | 리포트 생성 요청 확장 flow | `langflow_components/report_generation_flow/CONNECTION_GUIDE.md` |
| Operations Diagnosis | 운영 이상/병목 진단 요청 확장 flow | `langflow_components/operations_diagnosis_flow/CONNECTION_GUIDE.md` |

## Authoring Flows

| Flow | Detailed guide |
| --- | --- |
| Domain metadata authoring | `langflow_components/domain_authoring_flow/CONNECTION_GUIDE.md` |
| Table catalog authoring | `langflow_components/table_catalog_authoring_flow/CONNECTION_GUIDE.md` |
| Main flow filter authoring | `langflow_components/main_flow_filters_authoring_flow/CONNECTION_GUIDE.md` |

## Common Rules

- 실제 reasoning과 JSON 생성은 Langflow의 Gemini/LLM 노드가 담당합니다.
- Custom component는 prompt 생성, LLM 응답 정규화, payload 병합, 검증, 저장, 응답 정리를 담당합니다.
- Numbered custom component는 standalone이어야 하며 sibling helper module을 import하지 않습니다.
- 같은 component 안에서 input 이름과 output 이름이 겹치지 않게 합니다.
- Payload에는 다음 단계에 필요한 compact 정보만 담고, prompt 전문이나 중복 row를 계속 복사하지 않습니다.
