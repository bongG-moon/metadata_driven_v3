# MongoDB JSON Upload Guide

`tools/upload_json_to_mongodb.py`는 운영에 필요한 core metadata JSON 3종을 MongoDB seed collection으로 올리는 스크립트입니다.
질의 중 생성되는 source/result row는 이 스크립트가 아니라 main flow의 `18 MongoDB Data Store`가 별도 result collection에 저장합니다.

## Default Upload

기본 업로드 대상은 아래 3개 metadata collection입니다.

- `agent_v3_domain_items`
- `agent_v3_table_catalog_items`
- `agent_v3_main_flow_filters`

먼저 실제 접속 없이 대상 collection과 document count를 확인합니다.

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v3
python tools\upload_json_to_mongodb.py --dry-run
```

실제 업로드:

```powershell
python tools\upload_json_to_mongodb.py
```

## Stored Document Shape

v3 upload 문서는 기존 loader 호환 필드를 유지하면서 공통 envelope를 함께 저장한다.

공통 envelope:

```json
{
  "_id": "domain:process_groups:DA",
  "schema_version": "metadata-doc.v1",
  "agent_version": "metadata_driven_v3",
  "metadata_type": "domain",
  "namespace": "core",
  "identity": {"type": "domain", "section": "process_groups", "key": "DA"},
  "source": {"kind": "local_json", "path": ".../metadata/domain_items.json", "name": "domain_items.json"},
  "status": "active",
  "payload_hash": "..."
}
```

기존 main/data-analysis loader가 읽는 필드는 그대로 남긴다.

- Domain: `section`, `key`, `payload`
- Table catalog: `dataset_key`, `key`, `payload`
- Main flow filter: `filter_key`, `key`, `payload`

즉 MongoDB에서 문서를 봤을 때는 metadata 종류와 출처를 바로 알 수 있고, flow 실행 로직은 기존처럼 범용 loader가 metadata payload만 읽어 동작한다.

## Upload Options

metadata collection은 prefix 조합이 아니라 full collection name을 직접 입력합니다.

```powershell
$env:MONGODB_URI="mongodb://user:password@host:27017"
python tools\upload_json_to_mongodb.py --database datagov `
  --domain-collection agent_v3_domain_items `
  --table-catalog-collection agent_v3_table_catalog_items `
  --main-flow-filter-collection agent_v3_main_flow_filters
```

`--mode upsert`가 기본값이며 deterministic `_id` 기준으로 같은 문서를 갱신합니다.
전체 target collection을 비우고 다시 넣고 싶을 때만 `--mode replace`를 사용합니다.

```powershell
python tools\upload_json_to_mongodb.py --database datagov `
  --domain-collection agent_v3_domain_items `
  --table-catalog-collection agent_v3_table_catalog_items `
  --main-flow-filter-collection agent_v3_main_flow_filters `
  --mode replace
```

## Optional Uploads

regression 질문까지 같이 올릴 때:

```powershell
python tools\upload_json_to_mongodb.py --dry-run --include-regression
python tools\upload_json_to_mongodb.py --include-regression
```

sample data까지 같이 올릴 때:

```powershell
python tools\upload_json_to_mongodb.py --dry-run --include-regression --include-sample-data
python tools\upload_json_to_mongodb.py --include-regression --include-sample-data
```

## If Extra Collections Were Already Uploaded

sample/regression collection을 지우고 싶다면 MongoDB에서 아래 collection을 drop합니다. 삭제 전 대상 DB를 반드시 확인하세요.

```javascript
db.agent_v3_regression_questions.drop()
db.agent_v3_sample_capacity.drop()
db.agent_v3_sample_equipment_status.drop()
db.agent_v3_sample_hold_history.drop()
db.agent_v3_sample_lot_status.drop()
db.agent_v3_sample_production.drop()
db.agent_v3_sample_production_today.drop()
db.agent_v3_sample_target.drop()
db.agent_v3_sample_wip.drop()
db.agent_v3_sample_wip_today.drop()
```

## Main Flow Result Store

metadata collection 3개와 result store collection은 목적이 다릅니다.

| Collection type | 기본 full collection name | 저장 내용 |
| --- | --- | --- |
| Domain metadata | `agent_v3_domain_items` | 업무 용어, 공정/제품/수량 기준 |
| Table catalog metadata | `agent_v3_table_catalog_items` | dataset, source type, column/param/filter 매핑 |
| Main flow filter metadata | `agent_v3_main_flow_filters` | DATE, LOT_ID 같은 필터/파라미터 정의 |
| Main flow result store | `agent_v3_result_store` | source rows, pandas result rows, compact state refs |

운영 flow에서는 MongoDB Data Store가 pandas 직후 source/result rows를 저장하고, Answer Response Builder가 저장된 `analysis.data_ref`를 final payload/state에 이어받습니다. 다음 turn 시작 시에는 compact state를 그대로 사용하는 것이 기본이며, 이전 결과 전체 rows가 필요한 후속 분석만 data analysis flow의 “이전 결과 복원” 브랜치에서 MongoDB loader를 실행합니다.

- 환경변수: `MONGODB_RESULT_COLLECTION`
- Langflow 입력명: `result_collection_name`
- 저장 대상: source `runtime_sources`, pandas `analysis.rows`
- payload에는 preview rows와 MongoDB `data_ref`만 남깁니다.
- 후속 계획에는 `state.current_data.product_key_values`와 preview rows를 우선 사용하고, 전체 rows는 “이전 결과 복원” 브랜치가 필요하다고 판단한 경우에만 복원합니다.

즉 `upload_json_to_mongodb.py`는 metadata seed용이고, 실제 질의 결과 payload 절감은 `data_analysis_flow` 안의 MongoDB result store 노드가 담당합니다.


