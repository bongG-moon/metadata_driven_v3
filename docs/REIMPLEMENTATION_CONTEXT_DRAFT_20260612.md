# Agent Reimplementation Context Draft - 2026-06-12

이 문서는 새 개발자가 기존 구현 코드에 얽매이지 않고, Langflow 기반 low-code 데이터 조회/분석 Agent를 처음부터 다시 설계하고 구현할 수 있도록 작성한 요구사항 초안이다.

현재 MongoDB에 저장된 domain, table catalog, main flow filter 정보와 아래 검증 질문들은 참고하되, 기존 Python 코드 구조를 그대로 따를 필요는 없다. 목표는 특정 제조 공정 전용 Agent가 아니라, 데이터를 조회하는 어떤 조직이든 동일한 Langflow 구조를 재사용하고 domain metadata, table catalog main flow filter만 바꾸면 자기 조직의 용어와 데이터로 질의/분석할 수 있는 Agent를 만드는 것이다.

## 1. 다시 구현할 Agent의 기본 목표

사용자는 실제 업무에서 쓰는 자연어 용어로 질문한다. Agent는 사람이 생각하듯이 질문을 해석해서 필요한 데이터, 필터 조건, 분석 방식, 결과 grain을 결정하고, 실제 source data를 조회한 뒤 pandas 코드로 의도한 답변 데이터셋을 만든다. 마지막 답변은 그 분석 결과를 근거로 생성한다.

이 Agent가 담당해야 하는 일:

1. 사용자의 업무 용어를 domain metadata와 연결한다.
2. 질문에 필요한 dataset과 조회 조건을 table catalog 기준으로 결정한다.
3. 후속 질문에 필요한 주요 parameter와 필터 후보를 main flow filter 정보로 관리한다.
4. 여러 데이터 source에서 온 결과를 pandas DataFrame으로 통합한다.
5. group by, ranking, ratio, plan-vs-actual, 부족/저조 판단, 후속 재분석 같은 처리를 pandas 코드로 수행한다.
6. 최종 답변에 사용 dataset, 적용 조건, 계산 기준, 결과 데이터를 함께 보여준다.
7. domain metadata, table catalog main flow filter 정보는 mongodb에 저장한다.

### 1.1 Metadata 역할

| metadata | 역할 | 예시 |
| --- | --- | --- |
| Domain 정보 | 조직/업무에서 쓰는 용어, alias, 공정/제품 조건, 간단한 계산식, metric 의미를 정의한다. | `HBM`, `AUTO향`, `W/B공정`, `생산달성율`, `Lot 수량` |
| Table catalog | 어떤 dataset이 있고, 어떤 source에서 어떻게 조회하며, 어떤 컬럼/필수 parameter/쿼리 템플릿/수량 컬럼을 가지는지 정의한다. | Oracle query, Goodocs table, `DATE` mapping, `primary_quantity_column` |
| Main flow filter | 후속 분석이나 공통 필터 추출에 필요한 주요 parameter와 컬럼 후보를 정의한다. | `DATE`, `OPER_NAME`, `MCP_NO`, `LOT_ID`, `EQP_ID`, `RECIPE_ID` |

Domain 정보는 업무 의미를 설명하고, table catalog는 실제 데이터 접근 방식을 설명하며, main flow filter는 질문과 후속 질문에서 반복적으로 추출해야 하는 parameter의 표준 사전을 제공한다.

### 1.2 사람처럼 단계로 사고하는 Planner

이 Agent에서 가장 중요한 부분은 복잡한 질문을 한 번에 하나의 조회나 하나의 집계로 뭉개지 않고, 사람이 업무적으로 생각하는 순서처럼 단계를 나누어 실행 계획을 세우는 능력이다. 구현자는 기존 flow 구조에 매몰되기보다, LLM이 질문을 보고 "무엇을 먼저 구하고, 그 결과를 어디에 다시 써야 하는지"를 구조화된 실행 계획으로 만들 수 있게 설계해야 한다.

여기서 말하는 사고 과정은 숨겨진 chain-of-thought를 그대로 출력하라는 뜻이 아니다. Agent 내부에서 실행 가능한 `step_plan`을 만들고, 각 step의 입력, 출력, 의존 관계, 필요한 dataset, filter, group by, 계산 방식을 명확히 표현하라는 뜻이다.

복잡한 질문 예시:

`오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘`

사람이 기대하는 분석 흐름:

1. "오늘 DA공정 재공 상위 3개 제품"과 "오늘 WB공정 재공 상위 3개 제품"을 각각 구한다.
2. 이때 DA와 WB는 서로 다른 rank group이므로 섞어서 top 3를 뽑지 않는다.
3. 1단계 결과에서 제품 식별 key 목록을 만든다.
4. 해당 제품들에 대해 오늘 생산량 데이터를 조회하거나 이미 조회한 production source에서 같은 제품 key로 필터링한다.
5. 제품 key와 rank group 기준으로 WIP ranking 결과와 생산량 집계 결과를 join한다.
6. 최종 결과에는 `RANK_GROUP`, 제품 식별 컬럼, `WIP`, rank, `PRODUCTION`이 함께 남아야 한다.

이 질문의 실행 계획은 대략 아래처럼 표현될 수 있다.

```json
{
  "question_type": "multi_step_analysis",
  "steps": [
    {
      "step_id": "rank_wip_by_process_group",
      "purpose": "DA/WB 각각에서 재공 상위 3개 제품을 찾는다",
      "dataset": "wip_today",
      "filters": [
        {"group": "DA", "OPER_NAME": ["D/A1", "D/A2", "D/A3", "D/A4", "D/A5", "D/A6"]},
        {"group": "WB", "OPER_NAME": ["W/B1", "W/B2", "W/B3", "W/B4", "W/B5", "W/B6"]}
      ],
      "group_by": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
      "measure": {"column": "WIP", "aggregation": "sum"},
      "operation": "rank_top_n_per_filter_group",
      "top_n": 3,
      "output": "ranked_products"
    },
    {
      "step_id": "aggregate_production_for_ranked_products",
      "purpose": "상위 재공 제품들의 오늘 생산량을 구한다",
      "dataset": "production_today",
      "depends_on": "ranked_products",
      "filter_from_previous_step": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
      "measure": {"column": "PRODUCTION", "aggregation": "sum"},
      "output": "production_by_ranked_product"
    },
    {
      "step_id": "join_rank_and_production",
      "purpose": "재공 ranking 결과와 생산량 결과를 제품 기준으로 결합한다",
      "operation": "left_join",
      "left": "ranked_products",
      "right": "production_by_ranked_product",
      "join_keys": ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"],
      "output": "final_answer_data"
    }
  ]
}
```

Planner가 지켜야 할 원칙:

- 질문 안에 "해당 제품", "그 제품", "이때", "각각", "비교해서", "상위 N개를 뽑고 그 대상의 ..." 같은 표현이 있으면 step 간 의존 관계를 먼저 의심한다.
- 여러 조건이 같은 dataset에 걸리는지, 서로 다른 dataset에 독립적으로 걸리는지 구분한다.
- "각각"이라는 표현은 filter group별 결과를 분리하라는 신호일 수 있다.
- "해당 제품들의 생산량"처럼 앞 단계 결과를 다음 단계 조회/분석의 filter로 써야 하는 경우, 단순 multi-retrieval이 아니라 intermediate result를 재사용하는 multi-step plan으로 만든다.
- 최종 답변에 필요한 result schema를 먼저 정하고, pandas 분석이 그 schema를 만들도록 한다.
- 한 번에 거대한 pandas 코드를 만들기보다, step별 DataFrame을 만들고 검증 가능한 이름으로 이어 붙이는 방식이 좋다.

Pandas 코드 생성도 이 step plan을 반영해야 한다. 예시 질문의 pandas 코드는 `wip_today`와 `production_today`를 단순 concat한 뒤 합계를 내는 방식이 아니라, 먼저 DA/WB group별 WIP top 3를 만들고, 그 결과의 제품 key로 production을 집계한 뒤 join해야 한다. 중간 DataFrame 이름도 `ranked_products`, `production_by_ranked_product`, `final_result`처럼 의도와 대응되게 만드는 편이 검증과 디버깅에 유리하다.

### 1.3 Pandas 분석을 사용하는 이유

이 Agent는 Text-to-SQL만으로 답을 만들지 않는다. 실제 업무 질문은 여러 source의 데이터를 함께 봐야 하는 경우가 많고, source가 Oracle, Goodocs, Datalake, API, 파일 등으로 나뉘면 단일 SQL로 통합 분석하기 어렵다. 또한 Text-to-SQL은 SQL dialect, join 조건, 권한, 쿼리 오류에 취약하다.

따라서 권장 방식은 다음과 같다.

1. 각 source는 table catalog에 정의된 방식대로 안전하게 조회한다.
2. 조회 결과를 pandas DataFrame으로 표준화한다.
3. LLM은 질문 의도에 맞는 pandas 분석 계획과 코드를 생성한다.
4. executor는 허용된 pandas 연산으로 필터, 집계, join, ranking, ratio 계산을 수행한다.
5. 분석 결과 DataFrame을 최종 답변의 근거 데이터로 사용한다.

### 1.4 Langflow 구현 제약

실제 운영 환경에서는 Langflow custom component가 standalone 방식으로 구현되어야 한다. 즉, 한 custom component 파일 안에 필요한 helper 함수가 함께 있어야 하며, 다른 custom component 파일이나 별도 공용 Python module에 작성한 함수를 import해서 재사용하는 방식은 사용할 수 없다.

구현 원칙:

- 각 numbered custom component는 독립 실행 가능한 파일이어야 한다.
- sibling file import, shared utility module import에 의존하지 않는다.
- 중복이 조금 생기더라도 Langflow에 붙여 넣었을 때 그 component 하나만으로 동작해야 한다.
- Langflow 캔버스에서 실제로 연결할 input/output 타입과 개수를 먼저 고려해 component interface를 설계한다.
- 기능 구현에 필요하지 않은 input/output port를 만들지 않는다. 연결점이 많아질수록 flow 이해와 유지보수가 어려워진다.
- 다음 node에 필요한 payload만 전달한다. 같은 내용이 여러 key에 중복 저장되어 payload가 불필요하게 복잡해지지 않게 한다.
- payload는 compact하지만 충분해야 한다. 예를 들어 원본 row 전체, 요약 row, filter scope, applied params, data ref가 모두 필요할 수 있지만, 같은 정보를 이름만 바꿔 반복 전달하면 안 된다.
- 공정/제품/metric 같은 업무별 규칙은 코드가 아니라 metadata와 prompt contract로 이동한다.
- 코드에는 generic planning, routing, retrieval wrapping, pandas execution, state handling, final answer assembly만 남긴다.

### 1.5 권장 전체 Flow 구성

Flow 복잡도는 기존 구현과 비슷한 정도를 목표로 한다. 너무 단순화해서 후속 분석과 multi-source 분석을 잃으면 안 되고, 반대로 모든 업무 규칙을 Python 노드에 하드코딩해서도 안 된다. 다만 아래 내용은 노드 이름이나 개수를 강제하는 설계도가 아니라, 구현자가 반드시 책임져야 하는 큰 역할을 설명한 것이다.

권장 구현 방향:

1. 대화 상태와 이전 분석 결과를 읽어 후속 질문인지 신규 질문인지 판단한다.
2. domain, table catalog, main flow filter metadata를 함께 읽어 질문 해석의 기준으로 사용한다.
3. LLM이 사용자 질문을 보고 필요한 dataset, 필수 parameter, 필터, group by, metric, 후처리 방식, step 간 의존 관계를 구조화된 plan으로 만든다.
4. plan을 정규화하면서 metadata와 충돌하는 부분을 보정하고, dataset별 retrieval job으로 나눈다.
5. 각 retrieval job은 독립적인 날짜, 필터, source alias를 유지한다.
6. 조회 결과가 단순 표시 수준이면 바로 답변 데이터로 만들고, 비교/집계/계산/랭킹/후속 재분석이 필요하면 pandas 분석 단계로 보낸다.
7. pandas 단계는 LLM이 생성한 step plan과 코드를 사용하되, 실행 전후로 컬럼 존재 여부, 숫자 변환, 중간 결과, 최종 result shape, metric 컬럼 누락 여부를 검증한다.
8. 최종 답변은 분석 결과를 근거로 만들고, 사용 dataset과 적용 조건, 계산 기준을 사용자가 확인할 수 있게 보여준다.
9. 다음 질문에서 재사용할 수 있도록 compact state와 source data reference를 저장한다.

구현자가 자유롭게 결정해도 되는 부분:

- Langflow node를 몇 개로 나눌지
- retrieval을 별도 subflow로 둘지 main flow 안에 둘지
- direct answer와 pandas analysis 분기를 어떤 router로 표현할지
- final answer LLM 호출 전후에 어떤 normalization node를 둘지
- metadata loader를 MongoDB 전용으로 둘지 JSON fallback을 함께 둘지

반드시 유지해야 하는 책임:

- metadata-driven intent planning
- 사람처럼 단계를 나누는 multi-step planning
- dataset별 retrieval scope 분리
- pandas 기반 multi-source 후처리
- 후속 질문을 위한 state/source reference 보존
- Langflow 연결에 맞는 간결한 input/output interface와 중복 없는 payload 전달
- 최종 답변의 적용 조건과 계산 근거 표시

중요 원칙:

- 공정, 제품 조건, metric, dataset 선택 규칙은 가능한 한 metadata로 표현한다.
- custom component는 독립 파일로 동작해야 하며 sibling module import에 의존하지 않는다.
- pandas code generation 실패를 조용히 숨기면 안 된다. fallback을 쓰더라도 어떤 metric/shape를 충족했는지 검증 가능해야 한다.
- 숫자 정답은 source 상태에 따라 달라질 수 있으므로, 검증의 핵심은 dataset 선택, filter, group_by, metric 계산 방식, 결과 컬럼, applied scope이다.

## 2. 현재 사용된 도메인 정보 요약

### 2.1 공정 그룹

주요 process group은 `mongodb_domain_items_example.json` 기준 23개다.

| key | 의미 |
| --- | --- |
| `DP`, `D/P` | `WET1`, `WET2`, `L/T1`, `L/T2`, `B/G1`, `B/G2`, `H/S1`, `H/S2`, `W/S1`, `W/S2`, `WSD1`, `WSD2`, `WEC1`, `WEC2`, `WLS1`, `WLS2`, `WVI`, `UV`, `C/C1` |
| `DA`, `D/A` | `D/A1`부터 `D/A6` |
| `WB`, `W/B` | `W/B1`부터 `W/B6` |
| `BG`, `B/G` | `B/G1`, `B/G2` |
| `WSD` | `WSD1`, `WSD2` |
| `DS`, `D/S` | `D/S1`. 기본적으로 `PKG_TYPE1=FCBGA` 조건을 자동 추가하지 않는다. |
| `FCB` | `FCB1`, `FCB2`, `FCB/H` |
| `FCBH` | `FCB/H`만 의미 |
| `BM`, `B/M`, `비엠` | `B/M` |

세부 공정 직접 언급 규칙:

- `W/B1`, `D/A1`처럼 숫자가 붙은 실제 세부 공정명이 직접 언급되면 해당 공정 하나만 의미한다.
- `W/B`, `D/A`처럼 그룹명이 언급되면 그룹 전체로 확장한다.
- `D/A랑 D/S`처럼 여러 공정 그룹이 같이 나오면 OR 조건으로 처리한다.

### 2.2 제품/자재 조건

| 용어 | 기대 해석 |
| --- | --- |
| HBM, 3DS, TSV | `TSV_DIE_TYP` 값이 존재하고 null/빈칸이 아닌 제품. `FAMILY=HBM`이나 `PKG_TYPE1=HBM` 조건을 자동 추가하지 않는다. |
| AUTO향, 오토모티브향 | `MCP_NO`가 존재하고 null/빈칸이 아니며 마지막 문자가 `I/O/N/P/Q/V` 중 하나 |
| MOBILE | `MODE`가 `LP`로 시작하고 `PKG_TYPE1`이 `LFBGA/TFBGA/UFBGA/VFBGA/WFBGA` 중 하나이며 `MCP_NO`가 비어 있음 |
| POP | `MODE`가 `LP`로 시작하고 `PKG_TYPE1`이 모바일 package 목록 중 하나이며 `MCP_NO`가 존재 |
| 2Hi, 4Hi, 8Hi | `TSV_DIE_TYP` 값으로 판단 |
| 제품/자재 기본 grain | `TECH`, `DEN`, `MODE`, `PKG_TYPE1`, `PKG_TYPE2`, `LEAD`, `MCP_NO` |
| 디바이스별, DEVICE CODE별 | 이 경우에만 `DEVICE`, `DEVICE_DESC` group_by 허용 |
| 차수별 | `OPER_NAME` group_by |

### 2.3 수량/metric 용어

| 용어 | 기대 dataset/계산 |
| --- | --- |
| 생산량, 실적 | `production_today` 또는 `production_history/production`의 `PRODUCTION` |
| 재공, WIP, 공정 물량 | `wip_today` 또는 `wip`의 `WIP` |
| 전체 재공 | 공정 필터 없이 `wip` 또는 `wip_today`의 `WIP`. 같은 질문 안의 PKG OUT 공정 조건을 전파하지 않는다. |
| INPUT 실적, 투입량 | `production` 계열에서 `OPER_NAME=INPUT`인 `PRODUCTION` |
| INPUT계획, 투입계획 | `target.INPUT계획` 우선. 구형 target에서만 `OPER_NAME=INPUT`의 `TARGET` |
| PKG OUT 실적 | 별도 공정이 없으면 `production.OPER_NAME=SHIP PKT`의 `PRODUCTION` |
| 생산 달성률 | `sum(PRODUCTION) / sum(OUT계획 or TARGET) * 100`, 먼저 group별 집계 후 계산 |
| 목표 미달 수량 | `max(sum(목표량) - sum(PRODUCTION), 0)` |
| 동적TAT | `sum(WIP) / sum(PRODUCTION)` |
| 저조제품 | 질문에 `저조`가 있을 때만 90% threshold와 오늘 기준 시간 보정 적용 |
| INPUT 대비 저조 | INPUT baseline과 선택 공정 actual을 같은 제품 grain에서 비교, 공정 그룹은 member별로 따로 비교 |
| Lot 수량 | `LOT_ID` distinct count, pandas aggregation은 `nunique`, output은 `LOT_COUNT` |
| 작업대기 Lot | `lot_status.LOT_STAT_CD=WAITING`, `LOT_ID` distinct count |
| 작업중 Lot | `lot_status.LOT_STAT_CD=RUNNING`, `LOT_ID` distinct count |
| Hold Lot | 현재 상태는 `lot_status.LOT_HOLD_STAT_CD=OnHold` 또는 `HOLD`, 이력은 `hold_history` |

### 2.4 현재 table catalog dataset

| dataset | source | 날짜 scope | required params | 주요 수량/컬럼 |
| --- | --- | --- | --- | --- |
| `production_today` | Oracle | current day | `DATE` | `WORK_DT`, `OPER_NAME`, `PRODUCTION`, 제품 grain 컬럼 |
| `production` / `production_history` | Oracle | history until yesterday | `DATE` | `WORK_DT`, `OPER_NAME`, `PRODUCTION`, 제품 grain 컬럼 |
| `wip_today` | Oracle | current day | `DATE` | `WORK_DT`, `OPER_NAME`, `WIP`, 제품 grain 컬럼 |
| `wip` | Oracle | history until yesterday | `DATE` | `WORK_DT`, `OPER_NAME`, `WIP`, 제품 grain 컬럼 |
| `target` | Goodocs | 전체 조회 후 날짜 필터 | 없음 | `DATE`, `Mode`, `DEN`, `TECH`, `PKG1`, `PKG2`, `MCP NO`, `INPUT계획`, `OUT계획` |
| `equipment_status` | Oracle | 현재/상태성 | 없음 | `EQPID`, `EQP_MODEL`, `PRESS_CNT`, `MODE`, `DEN`, `TECH`, `DEVICE`, `DEVICE_DESC`, `LOT_ID`, `RECIPE_ID` |
| `capacity` | Oracle | UPH/capacity | 없음 | `OPER_DESC`, `EQP_MODEL_CD`, `PROD_TYP`, `TECH_NM`, `DEN_TYP`, `PKG_TYP`, `MCP_SALE_CD`, `RECIPE_ID`, `AVG_UPH_VAL`, `BASE_DT` |
| `lot_status` | Oracle | 현재 LOT 상태 | 없음 또는 `DATE` 후처리 | `LOT_ID`, `OPER_SHORT_DESC`, `LOT_STAT_CD`, `LOT_HOLD_STAT_CD`, `SUB_PROD_QTY`, `WF_QTY`, `IN_TAT`, `CUM_TAT`, `HOT_LOT_YN` |
| `hold_history` | Oracle | LOT별 HOLD 이력 | `LOT_ID` | `LOT_ID`, `HOLD_TM`, `RELEASE_DUE_DATE`, `HOLD_CD`, `HOLD_USER_ID`, `HOLD_DESC`, `EVENT_CD` |

주의:

- 2026-06-10 MongoDB 검증 당시 `hold_history`가 실제 Mongo table catalog에 없어서 잘못 라우팅된 적이 있다. 현재 재구현에서는 반드시 `hold_history`를 등록하고 `LOT_ID`를 required param으로 둔다.
- target은 required param 없이 전체 조회 후 `DATE` 필터를 적용할 수 있으므로 `date_format: YYYY-MM-DD` 같은 metadata가 중요하다.
- production 과거 dataset 이름은 환경에 따라 `production` 또는 `production_history`로 나타났으므로, 재구현 시 alias/family를 명확히 맞춘다.

## 3. 기존 문제 유형

### 3.1 pandas code generation 안정성

반복 문제:

- 없는 컬럼을 참조한다.
- `dataset_key`, `source_alias`, `job_key`, `tool_name` 같은 source metadata 컬럼을 DataFrame 컬럼처럼 참조한다.
- `import`, `pd.inf`, `np.inf` 같은 실행 제한 위반 코드가 생성된다.
- LLM이 metric 결과 컬럼을 빠뜨리고 fallback이 조용히 다른 결과를 만든다.
- 문자열 숫자 컬럼을 숫자로 변환하지 않아 threshold/ranking이 깨진다.

기대:

- 숫자 컬럼은 pandas 분석 전에 `pd.to_numeric(..., errors="coerce")`로 변환한다.
- `PRODUCTION`, `WIP`, `TARGET`, `INPUT계획`, `OUT계획`, `SUB_PROD_QTY`, `WF_QTY`, `IN_TAT`, `CUM_TAT` 같은 수량 컬럼은 문자열로 들어와도 비교/합계 가능해야 한다.
- 실패하면 최종 답변에 실패 이유가 드러나야 하고, 임의의 단순 합계로 성공처럼 보이면 안 된다.

### 3.2 filter propagation과 scope 오염

반복 문제:

- HBM 질문에서 `TSV_DIE_TYP exists/not empty` 대신 `FAMILY=HBM` 같은 잘못된 조건을 붙인다.
- `W/B1` 같은 세부 공정 질문을 `W/B1~W/B6` 전체로 확장한다.
- 같은 질문 안의 production 공정 조건이 wip 전체 재공에 잘못 전파된다.
- 이전 질문의 `wip_today`, `W/B`, `LPDDR5` scope가 새 production metric 질문에 남는다.

기대:

- dataset별로 filter scope를 분리한다.
- `전체 재공`은 공정 필터를 reset한다.
- 후속 질문은 상속과 reset을 명시적으로 구분한다.

### 3.3 metric 해석

반복 문제:

- 생산 달성률을 row-level rate 평균으로 계산한다.
- `INPUT계획` baseline을 `production.PRODUCTION`의 INPUT 실적으로 계산한다.
- 저조제품 질문에서 공정 그룹 전체 합계로 한 번 비교한다.
- 오늘 기준인데 시간 보정을 누락하거나, 과거일인데 시간 보정을 적용한다.

기대:

- metric은 aggregate-first 후 계산한다.
- `INPUT계획 대비`와 `INPUT 실적 대비`를 구분한다.
- `B/G` 같은 공정 그룹은 `B/G1`, `B/G2`를 개별 비교한다.
- 오늘 기준 계획/캡파 저조 판단은 `elapsed_hours_since_07`을 사용한다.

### 3.4 multi-dataset, multi-date, multi-scope

반복 문제:

- 같은 dataset을 다른 날짜/공정 scope로 두 번 조회해야 하는데 한 job으로 섞인다.
- `어제 PKG OUT`과 `오늘 전체 재공`이 같은 공정 필터를 공유한다.
- `production_today`와 `wip_today` 중 한쪽 dataset만 선택한다.
- 결과 grain이 제품별이어야 하는데 단일 합계로 뭉개진다.

기대:

- retrieval job은 dataset, 날짜, source alias, filter scope를 분리한다.
- `dataset_required_params` 또는 job별 params를 보존한다.
- 같은 dataset 두 번 조회도 source alias로 구분한다.

### 3.5 LOT/HOLD 처리

반복 문제:

- Lot 수량을 `SUB_PROD_QTY`, `WF_QTY`, `IN_TAT`, `CUM_TAT` 합계로 처리한다.
- 현재 HOLD 상태와 HOLD 이력을 섞는다.
- `T1234567GEN1 LOT의 HOLD이력`에서 `hold_history`가 아니라 `lot_status`로 간다.
- detail list 질문을 자동 집계해 버린다.

기대:

- Lot count는 `LOT_ID` distinct count다.
- wafer/die/TAT는 별도 measure다.
- `hold_history`는 `LOT_ID`가 required param이고 상세 컬럼을 보존한다.
- `hold lot list`는 `detail_rows`로 응답한다.

### 3.6 후속 질문

반복 문제:

- 두 번째 질문이 이전 metric/requested_measures를 잃고 단독 조회가 된다.
- 이전 final result row만 보고 재분석하고, source row를 재사용하지 않는다.
- scope reset 요청을 무시한다.
- "이 제품에 할당된 장비"처럼 직전 결과의 제품 grain을 equipment dataset filter로 연결하지 못한다.

기대:

- 후속 분석은 우선 `followup_source_results` 또는 `data_ref`로 원본 source를 재사용한다.
- 필요한 경우 이전 결과에서 제품 식별 조건을 추출해 새 dataset 조회에 사용한다.
- `조건 초기화`가 있으면 이전 scope를 버린다.

## 4. 기대 답변 형식

최종 답변은 사람이 읽기 쉬워야 하지만, 검증 가능한 구조를 유지해야 한다.

필수 표시 항목:

- 사용 dataset
- dataset별 기준 파라미터
- dataset별/통합 filter
- group_by 또는 ranking 기준
- metric 계산식 또는 수량 기준
- 결과 데이터
- 참고한 도메인 정보
- 후속 질문이면 상속/초기화 여부

예시 skeleton:

```text
요청하신 [dataset] 기준일은 [date]입니다.

[핵심 결론 한 문장]

### 적용 조건
- 사용 데이터셋: production_today, wip_today
- 데이터셋별 기준 파라미터: production_today: DATE=20260612; wip_today: DATE=20260612
- 필터: production_today.OPER_NAME=W/B1~W/B6, MODE=LPDDR5; wip_today.OPER_NAME=W/B1~W/B6, MODE=LPDDR5
- 그룹 기준: TECH, DEN, MODE, PKG_TYPE1, PKG_TYPE2, LEAD, MCP_NO

### 참고한 도메인 정보
- W/B 공정: W/B1~W/B6
- 수량 기준: production_today.PRODUCTION, wip_today.WIP

### 최종 데이터
[표]
```

## 5. 실제 문제 질문 목록

아래 목록은 세션 `019e8dcd...`에서 정리된 실제 질문을 원문 중심으로 보존한 것이다. 중복되거나 표현이 유사한 질문도 의도 차이가 있을 수 있어 남겨 둔다.

### 5.1 공정/자재 필터와 기본 집계

| 질문 | 기대 동작 |
| --- | --- |
| 오늘 HBM자재의 생산량이 가장 많은 공정을 알려줘 | `production_today`, HBM은 `TSV_DIE_TYP` exists/not empty, `OPER_NAME`별 `PRODUCTION` 합계 top 1 |
| 오늘 DP공정에서 생산량이랑 WB공정에서 재공 알려줘 | `production_today` DP scope와 `wip_today` WB scope를 별도 job으로 조회 |
| 제품별로 현재 DA공정 재공수량이랑 WB공정 재공 수량 비교해줘 | `wip_today`를 DA/WB scope로 분리, 제품 grain 기준 비교 |
| 현재 B/G공정 실적 대비 INPUT공정 생산량이 저조한 제품 알려줘 | `production_today`, INPUT baseline과 B/G member별 actual 비교 |
| W/B1공정 현재 생산량과 재공 알려줘 | 세부 공정 `W/B1`만 사용, `production_today`와 `wip_today` |
| W/B공정 현재 생산량과 재공 알려줘 | `W/B1~W/B6` 그룹 확장, 생산/재공 모두 적용 |
| W/B1, D/A1 공정 현재 생산량과 재공을 각각 알려줘 | 두 세부 공정을 OR scope로 유지하고 각 공정별 결과 분리 |
| D/P공정에서 현재 가장 많이 WIP에 보유하고 있는 제품 알려줘 | `wip_today`, DP group filter, 제품 grain top 1 |

### 5.2 계획 대비 실적, 달성율, 저조 제품

| 질문 | 기대 동작 |
| --- | --- |
| 오늘 input계획 대비 실적이 저조한 제품 알려줘 | baseline은 `target.INPUT계획`, compare는 production actual, 오늘이면 시간 보정 |
| 오늘 input계획 대비해서 실적이 80%이상을 만족하고 있는 제품 알려줘, 수량도 같이 | `target.INPUT계획` 대비 actual ratio, threshold 80%, 수량 컬럼 포함 |
| 오늘 input계획 대비해서 input 실적이 80%이상을 만족하고 있는 제품 알려줘, 수량도 같이 | baseline `target.INPUT계획`, compare `production_today.OPER_NAME=INPUT` |
| 현재 시간 기준으로 POP제품 일별 계획 대비 PKG OUT 실적 미달한 제품과 차이수량(Bal) 알려줘 | POP 조건, target 계획과 `SHIP PKT` actual 비교, Bal = max(plan - actual, 0) |
| 금일 PKG OUT계획 대비 전체 공정 기준으로 재공 수량이 부족한 제품 알려줘 | PKG OUT 계획과 전체 WIP scope 분리, 전체 WIP에는 `SHIP PKT` 필터 전파 금지 |
| 오늘 DA공정에서 DDR5제품의 생산 달성율과 생산 포화율을 알려줘 | DA + DDR5 filter, production/target/capacity 또는 관련 metric을 aggregate-first 계산 |
| 오늘 DA공정에서 DDR5제품의 생산 달성율 | `PRODUCTION / OUT계획 or TARGET * 100`, group 요청이 없으면 적절한 scope 합계 |
| 오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 보여줘 | `wip_today`, `production_today`, `target` 모두 필요, 재공/생산/목표/달성율 누락 금지 |
| 오늘 INPUT 실적 대비 B/G공정 생산 저조한 제품 알려줘 | INPUT actual baseline과 B/G1/B/G2 actual을 개별 비교, 결과에 baseline/compare/rate/flag 포함 |

### 5.3 여러 공정/조건 비교

| 질문 | 기대 동작 |
| --- | --- |
| 현재 FCB1, D/A1 공정에서 재공 없는 제품중 B/G공정에서 WIP 재공 있는 제품 및 재공수량 알려줘 | `wip_today`에서 FCB1/D/A1 absence와 B/G presence를 제품 grain으로 비교 |
| 오늘 INPUT공정과 B/G1, B/G2공정 각각의 실적을 제품별로 보여줘 | 같은 dataset 내 `INPUT`, `B/G1`, `B/G2`를 각각 별도 컬럼 또는 row로 유지 |
| 어제 DA공정 생산량과 오늘 WB공정 생산량을 알려줘 | 같은 production family라도 어제/오늘 job과 DA/WB scope 분리 |

### 5.4 제품 조건과 공정 조건 복합 필터

| 질문 | 기대 동작 |
| --- | --- |
| 현재 MODE값이 LPDDR5인 제품의 W/B공정에서 생산량과 재공 수량 알려줘 | `production_today`, `wip_today`, W/B filter와 MODE=LPDDR5를 양쪽에 적용 |
| 각 차수별로 값을 알려줄래? | 이전 질문 scope를 유지하고 `OPER_NAME` group_by만 추가 |
| L-269 제품 오늘 W/B 공정에서 차수별 생산량과 어제 재공 수량 알려줘 | MCP_NO prefix 또는 제품 조건, 오늘 production과 어제 wip 분리, 차수별 `OPER_NAME` |
| 오늘 TECH가 RG인 DDR4제품 W/B공정 생산량과 재공 현황을 알려줘 | TECH=RG, MODE=DDR4, W/B filter를 production/wip 양쪽에 적용 |

### 5.5 후속 질문과 이전 데이터 재사용

| 이전/현재 질문 | 기대 동작 |
| --- | --- |
| 오늘 DA공정에서 MODE/TECH별 생산량알려줘 | 첫 질문은 DA + production source를 state에 보존 |
| 이날 LPDDR5제품 투입량은 어땠어? | 이전 날짜/DA 또는 필요한 scope를 해석하고 LPDDR5 + INPUT actual 조회 |
| 오늘 AUTO향 제품 생산량과 재공, 생산달성율을 MODE/TECH/LEAD별로 알려줘 | AUTO 조건, production/wip/target, group_by 유지 |
| 이때 목표값 상위 5개의 MODE/TECH조합을 알려줘 | 이전 AUTO/date scope와 target source를 재사용해 top 5 |

### 5.6 서로 다른 날짜/공정/dataset 조합

| 질문 | 기대 동작 |
| --- | --- |
| 어제 AUTO향 제품 PKG OUT 실적과 오늘 아침 전체 재공을 제품별로 정리해줘 | production은 어제 `SHIP PKT`, wip은 오늘 전체 재공, AUTO 제품 조건만 공통 |
| 어제 WB공정에서 생산달성율 상위 5개 제품을 알려주고, 해당 제품들의 오늘 DA공정 재공 수량을 알려줘 | 어제 WB production/target ranking 후 제품 set을 오늘 DA wip에 적용 |
| 어제 WB공정에서 생산달성율 상위 5개 제품을 알려주고, 해당 제품들의 오늘 WB공정 재공 수량을 알려줘 | 첫 단계와 후속 재공 scope가 모두 WB지만 날짜/dataset 분리 |

### 5.7 단순 조회와 multi-dataset 조회

| 질문 | 기대 동작 |
| --- | --- |
| 오늘 생산량/재공/목표 값을 보여줘 | `production_today`, `wip_today`, `target`, 각각 합계와 적용 scope 표시 |
| 오늘 DA공정 생산량 알려줘 | `production_today`, DA filter, 단순 합계 |
| 오늘 DA공정 생산량을 상세 공정별로 알려줘 | `production_today`, DA group filter, `OPER_NAME` group_by |

## 6. 현재 repo의 회귀/검증 질문 세트

### 6.1 Dummy flow smoke set

권장 기준일은 `20260531`, 어제는 `20260530`이다.

| ID | 질문 | 기대 dataset | 핵심 기대 |
| --- | --- | --- | --- |
| S-01 | 오늘 DA공정에서 생산량/재공 알려줘 | `production`, `wip` | DA 단순 합계, 상위 제품 해석 금지 |
| S-02 | 오늘 DA공정 생산량을 MODE/TECH별로 알려줘 | `production` | DA 확장, `MODE`, `TECH` group_by |
| S-03 | 오늘 DA공정 생산량 상위 5개 제품 알려줘 | `production` | 제품 grain top 5 |
| S-04 | 오늘 INPUT 실적 대비 B/G공정 생산 저조한 제품 알려줘 | `production` | target 없이 production actual 안에서 INPUT vs B/G1/B/G2 비교 |
| S-05 | 오늘 WB공정 생산달성률 상위 5개 제품 알려줘 | `production`, `target` | aggregate-first 후 achievement rate top 5 |
| S-06 | 어제 WB공정에서 생산달성율 상위 5개 제품을 알려주고, 해당 제품들의 오늘 DA공정 재공 수량을 알려줘 | `production`, `target`, `wip` | 어제 WB ranking, 오늘 DA wip 결합 |
| S-07 | 어제 DA공정 생산량과 오늘 WB공정 생산량 알려줘 | `production` 2 jobs | 같은 dataset family를 source alias로 분리 |
| S-08 | 오늘 HBM제품 생산량과 재공을 MODE/TECH별로 보여줘 | `production`, `wip` | HBM 조건과 product 축 비교 |
| S-09 | 오늘 HBM 장비 보유 현황을 EQP_MODEL별로 알려줘 | `equipment_status` | 장비 보유 dataset, `EQP_MODEL`, `PRESS_CNT` |
| S-10 | 오늘 WB공정 장비/레시피별 UPH 상위 5개 알려줘 | `capacity` | `OPER_DESC=W/B*`, `RECIPE_ID`, `AVG_UPH_VAL` |

연속 질문:

| ID | 질문 흐름 | 기대 |
| --- | --- | --- |
| F-01 | 오늘 DA공정 생산량을 MODE/TECH별로 알려줘 -> 그중 생산량 상위 3개만 보여줘 | 이전 source/data scope 재사용, top 3 |
| F-02 | 오늘 AUTO향 제품 생산량을 MODE별로 알려줘 -> 같은 조건으로 재공도 보여줘 | AUTO 조건 유지, 두 번째는 `wip` |
| F-03 | 어제 WB공정 생산달성률 상위 5개 제품 알려줘 -> 그 제품들의 오늘 DA공정 재공 수량도 같이 알려줘 | 제품 set 유지, 날짜와 dataset 변경 |
| F-04 | 오늘 DA공정 생산량 알려줘 -> 조건 초기화하고 오늘 전체 재공을 제품별로 알려줘 | DA filter reset, 전체 wip |
| F-05 | 오늘 HBM 장비 보유 현황을 EQP_MODEL별로 알려줘 -> 해당 HBM 제품들의 레시피별 UPH도 보여줘 | `equipment_status`에서 `capacity`로 전환 |

### 6.2 Domain feature validation 질문

공정 그룹:

| ID | 질문 | 기대 |
| --- | --- | --- |
| PG-01 | 2026년 5월 2일 DP공정 생산량 알려줘 | DP process list로 확장 |
| PG-02 | 2026년 5월 2일 D/P 공정 생산량을 MODE별로 보여줘 | D/P alias = DP, `MODE` group_by |
| PG-03 | 2026년 5월 2일 DS공정 생산량 알려줘 | `OPER_NAME=D/S1`, FCBGA 조건 자동 추가 금지 |
| PG-04 | 2026년 5월 2일 비엠 공정 재공 알려줘 | `B/M` alias |
| PG-05 | 2026년 5월 2일 WB공정 생산량을 TECH별로 알려줘 | W/B1~W/B6, `TECH` group_by |

제품/용어 조건:

| ID | 질문 | 기대 |
| --- | --- | --- |
| TERM-01 | 2026년 5월 2일 AUTO향 제품 실적 알려줘 | MCP_NO last_char 조건 |
| TERM-02 | 2026년 5월 2일 오토모티브향 제품 실적을 MODE별로 알려줘 | AUTO alias, `MODE` group_by |
| TERM-03 | 2026년 5월 2일 MOBILE제품 생산량을 MODE/TECH별로 알려줘 | MOBILE 조건 |
| TERM-04 | 2026년 5월 2일 POP제품 생산량 알려줘 | POP 조건 |
| TERM-05 | 2026년 5월 2일 HBM제품 생산량 알려줘 | `TSV_DIE_TYP` exists/not empty |
| TERM-06 | 2026년 5월 2일 8Hi 제품 재공 알려줘 | `TSV_DIE_TYP=8Hi` |
| TERM-07 | 2026년 5월 2일 투입량 알려줘 | `OPER_NAME=PKG INPUT` 또는 `INPUT`, `PRODUCTION` |

Metric:

| ID | 질문 | 기대 |
| --- | --- | --- |
| MET-01 | 2026년 5월 2일 생산달성율 알려줘 | production + target, aggregate-first |
| MET-02 | 2026년 5월 2일 DP공정 생산달성률을 MODE/TECH별로 알려줘 | DP filter, `MODE/TECH`, aggregate-first |
| MET-03 | 2026년 5월 2일 목표 미달 수량이 큰 제품 상위 5개 알려줘 | `max(TARGET-PRODUCTION,0)`, top 5 |
| MET-04 | 2026년 5월 2일 HBM제품 동적TAT 알려줘 | `WIP / PRODUCTION` |
| MET-05 | 2026년 5월 2일 저조제품 알려줘 | production/capacity or configured low output metric |

후속 질문:

| ID | 이전 질문 | 후속 질문 | 기대 |
| --- | --- | --- | --- |
| FU-01 | 오늘 DA공정 생산량 알려줘 | 이때 생산량이 가장 많은 MODE/TECH 조합을 상위 5개 알려줘 | 이전 DA/date source 재사용 |
| FU-02 | 오늘 AUTO향 제품 실적을 MODE별로 알려줘 | 그 결과를 TECH별 비율로 보여줘 | 최종 row가 아니라 source data 기반 재집계 |
| FU-03 | 오늘 DP공정 MOBILE제품 생산량을 MODE/TECH별로 알려줘 | 이날 MOBILE제품 생산달성율은 어땠어? | target 추가 조회 |
| FU-04 | 2026년 5월 2일 WB공정 생산량 알려줘 | 공정 조건은 유지하고 HBM제품만 보여줘 | WB/date 상속, HBM 추가 |
| FU-05 | 오늘 생산달성률 알려줘 | MODE별로 다시 보여줘 | metric/date 상속, group_by 변경 |
| FU-06 | 오늘 DA공정 생산량 알려줘 | 조건 초기화하고 오늘 WB공정 생산량 알려줘 | scope reset |

### 6.3 Complex regression questions

| No | 질문 | 기대 |
| --- | --- | --- |
| 1 | 오늘 DA공정에서 재공, 생산량과 목표값 그리고 생산달성율을 제품별/공정별로 보여줘 | `production`, `wip`, `target` 모두 필요 |
| 2 | 오늘 INPUT공정과 B/G1, B/G2공정 각각의 실적을 제품별로 보여줘 | INPUT/BG1/BG2 분리 |
| 3 | 오늘 TECH가 RG인 DDR4제품 W/B공정 생산량과 재공 현황을 알려줘 | TECH, MODE, W/B 모두 적용 |
| 4 | 어제 AUTO향 제품 PKG OUT 실적과 오늘 아침 전체 재공을 제품별로 정리해줘 | production과 wip scope 분리 |
| 5 | 오늘 DA공정에서 목표값 대비해서 생산량이 저조한 제품을 알려줘 | D/A1~D/A6 member별 비교 |
| 6 | 오늘 D/A1공정에서 목표값 대비해서 생산량이 저조한 제품을 알려줘 | 5번 중 D/A1과 논리 일관 |
| 7 | 오늘 INPUT계획대비 D/A공정에서 생산량이 저조한 제품을 알려줘 | baseline은 `target.INPUT계획`, compare는 DA production |
| 8 | 어제 INPUT계획대비 D/A공정에서 생산량이 저조한 제품을 알려줘 | 과거일은 시간 보정 없음 |
| 9 | 오늘 생산량과 목표값을 제품별로 보여줘 | 기본 제품 grain, DEVICE 끼어들지 않음 |
| 10 | 오늘 DEVICE CODE별 생산량을 보여줘 | DEVICE/DEVICE_DESC group_by 허용 |
| 11 | 오늘 FCB공정 생산량과 재공을 제품별로 알려줘 | production/wip 모두 FCB filter |
| 12 | 오늘 생산량, 재공, 목표값을 제품별로 보여주고 달성율도 같이 계산해줘 | 모든 measure 유지, 달성율은 aggregate-first |
| 13 | 오늘 전체 재공을 제품별로 알려줘 | wip 전체, 공정 filter 없음 |
| 14 | 오늘 PKG OUT 실적과 전체 재공을 제품별로 비교해서 보여줘 | production `SHIP PKT`, wip 전체 |
| 15 | 오늘 목표값 대비 생산달성율이 낮은 제품을 공정별로 알려줘 | target과 production 모두 `OPER_NAME` 보존 |

### 6.4 추가 dataset 검증 질문

LOT status:

| ID | 질문 | 기대 |
| --- | --- | --- |
| LOT-01 | 현재 작업대기 Lot 수량을 공정별로 알려줘 | `lot_status`, `LOT_STAT_CD=WAITING`, `LOT_ID nunique` |
| LOT-02 | 현재 작업중 Lot 수량을 제품별로 알려줘 | `LOT_STAT_CD=RUNNING`, 제품 grain |
| LOT-03 | 현재 Hold Lot 수량을 제품별로 보여줘 | `LOT_HOLD_STAT_CD=OnHold/HOLD`, 제품 grain |
| LOT-04 | 현재 W/B공정 Hold Lot 수량을 공정 차수별로 알려줘 | W/B + Hold, `OPER_SHORT_DESC/OPER_NAME` group_by |
| LOT-05 | 현재 HOT LOT 수량을 제품별로 알려줘 | `HOT_LOT_YN=Y` |
| LOT-06 | 현재 CUM TAT가 가장 긴 Lot 상위 5개 알려줘 | `CUM_TAT` ranking, `LOT_ID` 보존 |
| LOT-07 | 현재 IN TAT가 24시간보다 큰 Lot을 공정별로 알려줘 | numeric `IN_TAT > 24` |

HOLD history:

| ID | 질문 | 기대 |
| --- | --- | --- |
| HOLD-01 | LOT-00001-1의 HOLD 이력과 발생 사유 알려줘 | `hold_history`, required `LOT_ID`, `HOLD_TM`, `HOLD_CD`, `HOLD_DESC` |
| HOLD-02 | LOT-00001-1의 HOLD 코드별 발생 건수와 HOLD 시간을 알려줘 | `HOLD_CD` group_by |
| HOLD-03 | LOT-00001-1의 RELEASE_DUE_DATE 지난 HOLD 건 알려줘 | `RELEASE_DUE_DATE` 비교 |
| HOLD-04 | LOT-00001-1의 HOLD 담당자별 HOLD 건수 알려줘 | `HOLD_USER_ID` group_by |

LOT status와 기존 dataset 조합:

| ID | 질문 | 기대 |
| --- | --- | --- |
| MIX-01 | 현재 W/B공정 재공 수량과 작업대기 Lot 수량을 제품별로 비교해줘 | `wip_today` + `lot_status`, product grain |
| MIX-02 | 현재 Hold Lot이 있는 제품의 오늘 INPUT 실적 알려줘 | Hold 제품 set -> `production_today.OPER_NAME=INPUT` |
| MIX-03 | 현재 장비 할당이 가장 많은 제품의 작업중 Lot 수량 알려줘 | `equipment_status` ranking 후 `lot_status` 결합 |
| MIX-04 | 오늘 DA공정 생산량과 현재 DA공정 작업대기 Lot 수량을 제품별로 비교해줘 | production + lot_status 공정 매핑 |
| MIX-05 | 현재 HOLD Lot이 많은 제품의 오늘 생산달성율 알려줘 | `lot_status` + `production_today` + `target` |

날짜/source 분리:

| ID | 질문 | 기대 |
| --- | --- | --- |
| DATE-01 | 오늘 생산량과 생산계획을 제품별로 보여줘 | `production_today`, `target` |
| DATE-02 | 오늘 생산계획에서 OUT계획이 가장 큰 제품 상위 5개 알려줘 | `target`, `OUT계획` ranking |
| DATE-03 | 어제 생산량과 오늘 생산계획의 차이수량을 제품별로 알려줘 | `production_history`, `target`, 날짜 분리 |
| DATE-04 | 어제 W/B공정 생산량과 현재 W/B공정 재공을 제품별로 비교해줘 | history production + current wip |

### 6.5 2026-06-11 issue regression

| 질문 | 기대 |
| --- | --- |
| 현재 hold상태인 lot list를 알려줘 | `lot_status`, `detail_rows`, 상세 컬럼 유지 |
| hold 이력과 발생 사유를 LOT_ID L-TEST-001 기준으로 알려줘 | `hold_history`, `LOT_ID` 조건, HOLD 상세 컬럼 |
| 현재 DA공정에서 재공 lot이 몇개인지, wafer가 몇개인지, die수량은 몇개인지 알려줘 | `lot_status`, LOT count는 distinct, wafer/die는 sum |
| 현재 DA공정 재공 수량 알려줘 | `wip_today.WIP` 합계, lot_status로 해석 금지 |
| 현재 B/G공정에서 재공이 100보다 큰 제품을 제품별로 보여줘 | `WIP` 숫자 비교, threshold는 집계 후 적용 |
| 오늘 생산량과 생산 계획을 알려줘 | 문자열 숫자 컬럼도 집계 가능 |
| 현재 input실적 대비해서 b/g1공정 생산실적이 제품별로 어떤지 정리해서 알려줘 -> 상세 device별로 알려줄래? | 후속 질문은 metric/requested_measures 유지, grouping만 device로 변경 |
| 현재 WSD공정에 재공이 있는 제품중에 B/G공정에 재공이 없는 제품 알려줘 | WSD/BG scope 분리, product grain left join |
| 오늘 DA공정에서 실적은 있는데 현재 기준 WB공정에 재공 없는 제품 알려줘 | production exists + wip absent, 제품 grain 유지 |
| 오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아줘 | `wip_today`, `RANK_GROUP=DA/WB`, 그룹별 top 3 |
| 오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘 | WIP top 3 후 같은 제품 grain에서 production join |
| T1234567GEN1 LOT의 HOLD이력 알려줘 | `hold_history`만 사용, `LOT_ID` 유지 |
| LOT_ID가 필수 param이 아닌 dataset에서 LOT_ID 조건이 params로 들어온 조회 | `filter_mappings`가 있으면 pandas filter로 승격 |

### 6.6 2026-06-12 v2 validation

최신 v2 full smoke 결과는 6건 모두 PASS로 기록되어 있다. 이 질문들은 새 구현의 최소 end-to-end smoke로 쓸 만하다.

| ID | 질문 | 기대 dataset | 기대 step |
| --- | --- | --- | --- |
| v2_live_01 | 오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘 | `wip_today`, `production_today` | rank, aggregate, join |
| v2_live_02 | T1234567GEN1 LOT의 HOLD이력 알려줘 | `hold_history` | detail_rows |
| v2_live_03 | 현재 hold된 lot list 알려줘 | `lot_status` | detail_rows |
| v2_live_04 | 현재 da에서 재공이 가장 많은 제품 알려줘 | `wip_today` | rank |
| v2_live_05 | 이 제품에 할당된 장비 현황 알려줘 | `equipment_status` | follow-up product filter, detail_rows |
| v2_live_06 | 현재 MODE값이 LPDDR5인 제품의 W/B공정에서 생산량과 재공 수량 알려줘 | `production_today`, `wip_today` | aggregate, aggregate, join |

## 7. 검증 결과에서 확인된 과거 실패

| 날짜/리포트 | 결과 | 의미 |
| --- | --- | --- |
| 2026-06-04 question set | PASS 10, WARN 1, FAIL 1 | `INPUT 실적 대비 B/G 저조`는 LLM metric column 누락으로 WARN, `LPDDR5 W/B 생산+재공`은 dataset 누락/중복 문제 |
| 2026-06-09 complex validation | pytest 6 passed | complex 질문을 단위 검증으로 일부 고정 |
| 2026-06-10 MongoDB dataset validation | lot_status 일부 실패, hold_history 미등록 | metadata 등록/재등록 필요 확인 |
| 2026-06-10 quantity term validation | waiting/running/lot count PASS | `LOT_ID count_distinct -> nunique -> LOT_COUNT` 계약 확인 |
| 2026-06-11 today issue recheck | PASS 3, FAIL 7 | rank per filter group, hold detail, WSD/BG absence, DA actual/WB no wip, input vs DA low output에서 실패 |
| 2026-06-12 v2 full smoke | PASS 6 | v2 executor 쪽에서는 핵심 smoke가 통과 |

## 8. 재구현 요청서에 넣을 요구사항 초안

아래 문장은 사용자가 모범답안을 튜닝해서 지침서에 넣기 좋은 형태로 정리한 것이다.

1. 질문의 최종 답변보다 먼저, 내부적으로 `intent_plan`, `retrieval_jobs`, `filter_plan`, `requested_measures`, `group_by`, `metric_keys`, `analysis_output_shape`가 올바른지 검증 가능해야 한다.
2. 모든 dataset 조회는 dataset별 params와 filter scope를 독립적으로 가져야 한다. 한 질문 안에서 같은 dataset을 여러 날짜나 여러 공정으로 조회하면 source alias를 분리한다.
3. 제품/자재 기본 grain은 `TECH`, `DEN`, `MODE`, `PKG_TYPE1`, `PKG_TYPE2`, `LEAD`, `MCP_NO`이다. `DEVICE`, `DEVICE_DESC`는 사용자가 디바이스/DEVICE CODE를 명시할 때만 group_by에 들어간다.
4. HBM/3DS/TSV는 `TSV_DIE_TYP` exists/not empty로 판단한다.
5. `전체 재공`은 공정 필터를 상속하지 않는다.
6. `W/B1`, `D/A1` 같은 세부 공정은 그룹 전체로 확장하지 않는다.
7. `W/B`, `D/A` 같은 공정 그룹은 등록된 세부 공정 목록으로 확장한다.
8. 생산 달성률, 목표 미달, 동적TAT, 저조제품 metric은 row별 계산 후 평균이 아니라 group별 aggregate-first 후 계산한다.
9. `INPUT계획`은 target 계획이고, `INPUT 실적`은 production actual이다.
10. `INPUT 실적 대비 B/G 저조`는 `B/G1`, `B/G2`를 각각 INPUT과 비교한다.
11. 오늘 기준 저조/계획/CAPA 비교는 07시 이후 경과 시간을 반영하고, 과거일은 하루 전체 기준으로 계산한다.
12. Lot 수량은 `LOT_ID` distinct count이고 `SUB_PROD_QTY`, `WF_QTY`, `IN_TAT`, `CUM_TAT` 합계가 아니다.
13. HOLD 이력 질문은 `hold_history`만 사용하고 `LOT_ID`를 required param으로 보존한다.
14. detail list 질문은 자동 합계로 바꾸지 않고 `detail_rows` 결과를 보존한다.
15. 후속 질문은 이전 최종 표만이 아니라 source rows 또는 data_ref를 우선 재사용한다.
16. `조건 초기화`가 있으면 이전 scope를 버린다.
17. 최종 답변에는 적용 조건과 참고 도메인 정보를 항상 표시한다.
18. pandas 코드가 실패하거나 metric 결과 컬럼을 만들지 못하면 실패를 드러낸다. 조용히 다른 단순 집계로 대체하지 않는다.

## 9. 사용자가 튜닝하면 좋을 모범답안 영역

아래 케이스는 실제 숫자 모범답안을 사용자가 더 정확히 채우면 지침서 품질이 좋아진다.

| 케이스 | 현재 초안의 기대 | 사용자가 채우면 좋은 것 |
| --- | --- | --- |
| 생산량/재공/목표/달성율 | dataset과 계산식 중심 | 실제 운영 기준에서 보여줄 컬럼 순서와 수치 포맷 |
| 저조제품 | baseline/compare/rate/flag 컬럼 | `저조`, `부족`, `미달` 표현별 업무상 threshold |
| Lot count | `LOT_ID nunique` | 작업대기/작업중/Hold 상태 코드의 실제 운영값 |
| Hold history | 상세 컬럼 보존 | 이력 답변에서 꼭 보여야 하는 컬럼 우선순위 |
| 전체 재공 vs 공정 재공 | filter reset 여부 | "오늘 아침" 같은 표현의 기준 시각 |
| 후속 장비 조회 | 이전 제품 grain으로 equipment lookup | 장비 현황에서 집계와 상세 중 기본 응답 방식 |
