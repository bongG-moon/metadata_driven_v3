# Operations Diagnosis E2E Example Questions

이 파일의 질문들은 `operations_diagnosis_flow`가 단독 E2E 업무 flow로 선택되어야 하는 예시입니다. 후속 분석을 뜻하는 "방금 결과 기준" 질문이 아니라, 사용자가 처음부터 진단 목적과 범위를 요청하는 형태를 기준으로 합니다.

## Copy/Paste Questions

```text
오늘 DA공정 병목 원인을 진단해줘

오늘 WB공정에서 재공이 많이 쌓인 원인 후보를 진단해줘

오늘 목표 대비 생산량이 저조한 제품들의 원인 후보를 진단해줘

오늘 HBM 제품군 생산 저조 원인을 장비, 재공, HOLD LOT 관점으로 진단해줘

오늘 DA공정에서 재공 상위 공정의 HOLD LOT 수와 평균 IN TAT를 보고 병목 여부를 진단해줘
```

## Expected Flow Intent

```text
사용자 질문
-> 진단 목적/범위 판단
-> 필요한 증거 데이터 결정
-> 병목/저조/이상 후보 판단
-> 원인 후보와 권장 확인 순서 응답
```

나중에 state 기반 후속 진단도 추가할 수 있지만, 현재 예시 기준은 신규 E2E 진단 요청입니다.
