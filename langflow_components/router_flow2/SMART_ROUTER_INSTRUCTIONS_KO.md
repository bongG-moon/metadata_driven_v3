# Smart Router Instructions

아래 4개 route label 중 하나만 선택하세요. label은 반드시 그대로 반환합니다.

## metadata_qa

metadata, table catalog, domain, main flow filter, 등록된 데이터셋 목록, 컬럼 설명, 도메인 정보, 사용 예시, 도움말, 인사말처럼 실제 제조 데이터를 조회하지 않아도 답할 수 있는 질문입니다.

예시:
- 현재 조회 가능한 DATA LIST 알려줘
- production_today 데이터셋 컬럼 알려줘
- 공정 그룹관련해서 등록된 도메인정보들 알려줘
- 제품 관련 도메인 정보 뭐가 있어?

## data_analysis

생산량, 재공, 목표, 달성율, Lot, Hold, 장비 현황처럼 실제 데이터 조회와 pandas 분석이 필요한 질문입니다.

예시:
- 오늘 DA 공정 생산량 알려줘
- 512G G-777 제품의 어제 생산량과 재공을 세부 공정별로 알려줘
- 현재 hold된 lot 중 IN_TAT 24시간 이상인 Lot을 공정별로 집계해서 보여줘
- 2026-06-12 생산달성율을 제품별로 보여줘

## report_generation

조회/분석 결과를 바탕으로 요약 리포트, 일일 리포트, 현황 보고서, 표/차트 포함 보고서를 만들어 달라는 요청입니다.

예시:
- 오늘 WB공정 기준으로 생산량, 재공, 목표 달성률을 포함한 요약 리포트 만들어줘
- 방금 결과로 리포트 만들어줘
- 생산 현황 보고서 형태로 정리해줘

## operations_diagnosis

생산 저조, 병목, 이상 원인, Hold/장비/재공 관점 진단처럼 원인 분석이나 운영 진단을 요청하는 질문입니다.

예시:
- 오늘 HBM 제품군 생산 저조 원인을 장비, 재공, HOLD LOT 관점으로 진단해줘
- DA 공정 병목 원인 분석해줘
- 왜 생산량이 목표보다 낮은지 진단해줘

## 우선순위

1. 사용자가 metadata/catalog/domain/filter 등록 정보 자체를 묻는다면 `metadata_qa`입니다.
2. 실제 생산/재공/목표/Lot/장비 데이터를 조회하거나 계산해야 하면 `data_analysis`입니다.
3. 결과를 문서/리포트 형태로 만들어 달라는 요청이면 `report_generation`입니다.
4. 원인 분석, 병목 분석, 운영 진단이면 `operations_diagnosis`입니다.
5. 애매하면 `data_analysis`를 선택합니다.
