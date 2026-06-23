# Environment Setup

이 프로젝트는 실제 MongoDB/Gemini 검증으로 확장할 수 있도록 `.env` 파일을 사용한다.

## Files

- `.env.example`: 공유 가능한 템플릿
- `.env`: 로컬에서 실제 값을 채우는 파일

`.env`에는 비밀값이 들어갈 수 있으므로 `.gitignore`에 포함되어 있다.

## Required For MongoDB Validation

```dotenv
MONGODB_URI=mongodb://user:password@host:27017
MONGODB_DATABASE=metadata_driven_agent_v3
MONGODB_DOMAIN_COLLECTION=agent_v3_domain_items
MONGODB_TABLE_CATALOG_COLLECTION=agent_v3_table_catalog_items
MONGODB_MAIN_FLOW_FILTER_COLLECTION=agent_v3_main_flow_filters
MONGODB_RESULT_COLLECTION=agent_v3_result_store
RUN_MONGODB_VALIDATION=true
```

## Required For Gemini LLM Validation

```dotenv
LLM_PROVIDER=gemini
LLM_API_KEY=...
LLM_MODEL_NAME=...
LLM_TEMPERATURE=0
RUN_LLM_VALIDATION=true
```

이전 rebuild 폴더와 동일하게 Python 검증은 `langchain_google_genai.ChatGoogleGenerativeAI`를 사용한다.
`LLM_MODEL_NAME`은 운영자가 실제 사용 가능한 Gemini 모델 이름으로 채운다.
로컬 도구가 Google 표준 이름을 요구하면 `GOOGLE_API_KEY` 또는 `GEMINI_API_KEY`에도 같은 값을 넣을 수 있다.

## Required For Langflow Desktop/Web API Validation

Langflow Desktop에서 각 flow를 만든 뒤, flow 우측 상단의 API/Share/Run API 화면에서 flow id를 확인한다.
full URL이 `http://127.0.0.1:7860/api/v1/run/3023...` 형태라면 `LANGFLOW_BASE_URL`에는 `http://127.0.0.1:7860`만 넣고, 각 `*_FLOW_ID`에는 마지막 UUID만 넣으면 된다.
full URL을 그대로 쓰고 싶으면 대응되는 `*_API_URL`에 전체 주소를 넣어도 된다.
Streamlit web app은 repo 루트 또는 현재 실행 폴더의 `.env`를 자동으로 읽는다. 이미 OS 환경변수로 설정된 값은 `.env`가 덮어쓰지 않는다.

```dotenv
LANGFLOW_BASE_URL=http://127.0.0.1:7860
LANGFLOW_API_KEY=
LANGFLOW_INPUT_TYPE=chat
LANGFLOW_OUTPUT_TYPE=chat
LANGFLOW_TIMEOUT_SECONDS=180

LANGFLOW_ROUTER_FLOW_ID=
LANGFLOW_METADATA_QA_FLOW_ID=
LANGFLOW_DATA_ANALYSIS_FLOW_ID=
LANGFLOW_REPORT_GENERATION_FLOW_ID=
LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID=

LANGFLOW_DOMAIN_AUTHORING_FLOW_ID=
LANGFLOW_TABLE_CATALOG_AUTHORING_FLOW_ID=
LANGFLOW_MAIN_FILTER_AUTHORING_FLOW_ID=

RUN_LANGFLOW_API_VALIDATION=true
```

검증 기준은 다음과 같다.

- router flow: web app의 첫 진입점이다.
- metadata/data/report/diagnosis flow: router flow 내부의 `06 Selected Flow API Runner`가 선택적으로 호출하는 query subflow다. Desktop/Web 검증용 `LANGFLOW_ROUTER_FLOW_ID`는 `00~06`까지 연결된 router flow를 가리켜야 한다.
- authoring flow: web metadata 관리 화면에서 신규 metadata를 등록할 때 사용한다.
- `LANGFLOW_INPUT_TYPE`은 현재 컴포넌트들이 `MessageTextInput` 기반이면 `chat`을 기본으로 둔다. 실제 Langflow API 화면에서 `input_type`을 `text`로 안내하면 `.env`에서 `text`로 바꾸면 된다.

## Optional Source Retrieval Settings

기본 검증은 실제 Oracle/H-API/Datalake/Goodocs를 호출하지 않고 deterministic dummy data를 사용한다.
이때도 `table_catalog.json`의 `source_type` 경계는 유지되므로 Langflow 연결과 pandas 분석 scope를 검증할 수 있다.

```dotenv
RUN_LIVE_SOURCE_RETRIEVAL=false
ORACLE_CONFIG_JSON=
H_API_TOKEN=
LAKEHOUSE_USER_ID=
LAKEHOUSE_TOKEN=
LAKEHOUSE_S3_ACCESS_KEY=
LAKEHOUSE_S3_SECRET_KEY=
GOODOCS_USER_ID=
GOODOCS_TOKEN_SOURCE=
GOODOCS_TOKEN_KEY=
GOODOCS_MODULE_NAME=
SOURCE_FETCH_LIMIT=5000
```

실제 source connector를 시도하려면 `RUN_LIVE_SOURCE_RETRIEVAL=true`로 바꾸고 위 credential/config 값을 채운다.
자세한 source별 역할은 `docs/DATA_RETRIEVAL_SOURCES.md`를 참고하면 된다.

## Check Environment

```powershell
cd C:\Users\qkekt\Desktop\metadata_driven_v3
python tools\validate_env.py
```

Gemini API 호출까지 확인하려면:

```powershell
python tools\validate_gemini_connection.py
```

## Upload JSON Seed To MongoDB

```powershell
python tools\upload_json_to_mongodb.py --dry-run
python tools\upload_json_to_mongodb.py
```

부분 업로드가 필요하면 `--metadata-kind`를 사용합니다.

```powershell
python tools\upload_json_to_mongodb.py --dry-run --metadata-kind domain
python tools\upload_json_to_mongodb.py --metadata-kind table-catalog
python tools\upload_json_to_mongodb.py --metadata-kind main-flow-filter
python tools\upload_json_to_mongodb.py --metadata-kind table-catalog,main-flow-filter
```

`tools/upload_json_to_mongodb.py`는 실행 시 `.env`를 자동으로 읽는다. CLI 옵션이 `.env`보다 우선한다.
