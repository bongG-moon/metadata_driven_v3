# API Test

Langflow Run API 호출을 빠르게 확인하기 위한 테스트 도구입니다.

## Langflow Component

`00_langflow_api_test_component.py`를 Langflow custom component로 추가한 뒤 아래 값만 넣으면 됩니다.

- `API URL`: `http://127.0.0.1:7860/api/v1/run/<flow-id>`
- `Langflow Key`: Langflow API key. key가 필요 없는 로컬 Desktop이면 비워도 됩니다.

`Test Input`, `input_type`, `output_type`, `session_id`, `timeout_seconds`는 advanced input입니다.

## Local VS Code Test

```powershell
python api_test\local_api_test.py --api-url "http://127.0.0.1:7860/api/v1/run/<flow-id>" --langflow-key "<key>"
```

입력값을 바꾸고 싶으면:

```powershell
python api_test\local_api_test.py --api-url "http://127.0.0.1:7860/api/v1/run/<flow-id>" --langflow-key "<key>" --input "현재 조회 가능한 데이터 알려줘"
```

`.env`에 아래처럼 넣어도 됩니다.

```env
LANGFLOW_TEST_API_URL=http://127.0.0.1:7860/api/v1/run/<flow-id>
LANGFLOW_API_KEY=<key>
LANGFLOW_TEST_INPUT_VALUE=현재 조회 가능한 데이터 알려줘
```
