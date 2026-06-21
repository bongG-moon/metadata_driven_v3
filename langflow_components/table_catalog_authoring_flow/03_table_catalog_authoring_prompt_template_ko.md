정제된 dataset 설명을 MongoDB에 저장 가능한 table_catalog metadata로 변환하세요.
반드시 하나의 엄격한 JSON object만 반환하세요. markdown으로 감싸지 마세요.
정제된 설명에 있는 정보만 사용하세요. 필수 정보가 부족하면 missing_information에 넣으세요.
원본 사용자 입력은 literal SQL, query_template block, SELECT column, filter_mappings, dataset_key, db_key, source_type에 대한 기준 정보입니다.
정제된 설명은 요약되어 있을 수 있습니다. 원본 사용자 입력에 있는 구조화 정보를 누락하지 마세요.
query_template, API URL, document ID, sheet name, DB key, 물리 column을 지어내지 마세요.
source가 YYYYMMDD 또는 YYYY-MM-DD 같은 특정 날짜 표현을 기대하면 date_format을 저장하세요.
상세 행 조회에서 운영자가 일부 column만 보기를 기대하면 default_detail_columns를 저장하세요.
source별 필수 정보: oracle은 db_key와 query_template이 필요하고, datalake는 query_template이 필요하고, h_api는 api_url이 필요하고, goodocs는 doc_id만 필요합니다.
goodocs에는 db_key 또는 query_template을 요구하지 마세요. sheet_name은 선택 사항이며 사용자가 명시했거나 특정 sheet/tab을 읽어야 한다고 말한 경우에만 포함하세요.
사용자가 필수 query parameter가 없다고 말하면 DATE가 optional filter로 filter_mappings에 있더라도 required_params=[]로 설정하세요.
metadata에는 두 mapping layer가 있습니다. main_flow_filters는 표준 filter key를 정의하고, table_catalog.filter_mappings는 그 표준 key를 이 dataset의 물리 column에 매핑합니다.
dataset별 mapping을 main_flow_filters에 넣지 마세요. 각 dataset의 DATE/OPER_NAME/product/equipment mapping은 table_catalog.filter_mappings에 넣으세요.
filter_mappings의 왼쪽은 DATE, OPER_NAME, PKG_TYPE1, MCP_NO, EQP_ID, RECIPE_ID 같은 표준 main flow filter key여야 하고, 오른쪽은 이 dataset의 실제 source column 후보여야 합니다.
source의 물리 column 이름이 표준 분석 column 이름과 다르면 standard_column_aliases를 {{standard_column: [physical columns]}} 형태로 함께 저장하세요.
예: Goodocs target이 PKG1, MCP NO, OUT계획을 사용하면 PKG_TYPE1->PKG1, OUT_PLAN->OUT계획으로 매핑하세요. Equipment가 PKG1, PKG2, MCPSALENO를 사용하면 PKG_TYPE1->PKG1, MCP_NO->MCPSALENO로 매핑하세요.

작성 context:
{authoring_context}

필수 JSON schema:
{{
  "items": [
    {{
      "dataset_key": "stable_dataset_key",
      "payload": {{
        "display_name": "업무 표시명",
        "dataset_family": "production | wip | target | lot | hold | equipment | capacity | other",
        "date_scope": "current_day | history | snapshot | optional",
        "source_type": "dummy | oracle | h_api | datalake | goodocs",
        "source_config": {{
          "source_type": "source_type과 동일",
          "db_key": "oracle에서 알고 있으면 필수",
          "query_template": "oracle/datalake에서 알고 있으면 필수",
          "api_url": "h_api에서 알고 있으면 필수",
          "doc_id": "goodocs에서 필수",
          "sheet_name": "goodocs에서 명시적으로 알고 있을 때만 선택"
        }},
        "required_params": ["DATE"],
        "required_param_mappings": {{"DATE": ["WORK_DT"]}},
        "date_format": "선택적 값, 예: YYYYMMDD or YYYY-MM-DD",
        "primary_quantity_column": "column or list",
        "filter_mappings": {{"DATE": ["WORK_DT"]}},
        "standard_column_aliases": {{"standard analysis column": ["physical columns"]}},
        "default_detail_columns": ["선택적 detail output column"],
        "columns": ["physical columns"]
      }},
      "confidence": "high | medium | low"
    }}
  ],
  "missing_information": [
    {{"field": "필드명", "reason": "한국어 사유", "example_user_input": "한국어 예시 입력"}}
  ],
  "warnings": ["한국어 경고"]
}}
