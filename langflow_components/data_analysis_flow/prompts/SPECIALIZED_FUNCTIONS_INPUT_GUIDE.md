# Specialized Functions 입력 가이드

이 파일은 14 Pandas Prompt Builder와 15 Pandas Code Executor의 `Specialized Functions` 입력에 같은 내용으로 넣는다.

- 14번 입력은 pandas code LLM에게 어떤 helper를 호출해야 하는지 알려준다.
- 15번 입력은 실제 실행 시점에 helper 함수를 로드한다.
- 15번의 `Payload`는 13 Retrieval Payload Adapter의 `Payload`를 직접 연결한다.
- 선택된 function case의 함수 구현이 15번 입력 또는 metadata `function_code`에 없으면 pandas 분석은 진행하지 않는다.
- 14번은 이 입력 안의 자연어 설명과 Python 함수 예시를 LLM에게 그대로 보여주고, LLM은 이를 참고해서 최종 pandas code를 작성한다.
- 생성된 pandas code가 helper 함수를 inline으로 정의한 뒤 호출해도 되고, helper 호출만 남기는 경우에는 15번에도 같은 Specialized Functions 입력을 연결해 실행 환경에서 로드되게 한다.

작업자가 처음 작성할 때는 너무 엄격한 JSON이나 긴 스키마를 쓰지 말고, 아래처럼 자연어 설명과 Python helper 함수만 작성하면 된다.

```text
제품 토큰으로 제품 리스트나 제품 조건 기반 metric을 찾는 질문에서는 match_product_tokens helper를 사용한다.
이 helper는 조회된 제품 데이터에서 TECH, DEN/DENSITY, MODE, PKG1/PKG_TYPE1, PKG2/PKG_TYPE2, LEAD, MCP_NO 값을 입력 토큰과 비교해서 일치하는 행을 반환한다.
MCP_NO는 사용자가 L-269처럼 앞부분만 입력해도 실제 L-269P1Q 같은 값과 startswith로 매칭한다.
G-777제품처럼 제품 토큰 뒤에 한국어 명사/동사가 붙어도 G-777 token으로 정리해서 매칭한다.
pandas 생성 코드는 이 함수를 재정의하지 말고 match_product_tokens(input_text, sources[source_alias])처럼 positional argument로 호출한다.
```

아래 Python 코드블록은 실행 환경에 로드되는 helper 정의다. 이 코드블록은 14번, 첫 번째 15번, 두 번째 15번의 `Specialized Functions` 입력에 같은 내용으로 넣는다.

```python
def match_product_tokens(input_text, products_df=None, source_df=None, frame=None):
    products_df = products_df if products_df is not None else source_df
    products_df = products_df if products_df is not None else frame
    if products_df is None:
        return pd.DataFrame()

    token_columns = [
        "TECH",
        "DEN",
        "DENSITY",
        "MODE",
        "PKG_TYPE1",
        "PKG1",
        "PKG_TYPE2",
        "PKG2",
        "LEAD",
        "MCP_NO",
    ]
    output_columns = [
        "TECH",
        "DEN",
        "DENSITY",
        "PKG_TYPE1",
        "PKG1",
        "LEAD",
        "PKG_TYPE2",
        "PKG2",
        "MODE",
        "MCP_NO",
    ]

    result = products_df.copy()

    def normalize_token(value):
        return str(value or "").strip().upper()

    def looks_like_mcp_prefix(value):
        if "-" not in value:
            return False
        left, right = value.split("-", 1)
        digit_prefix = ""
        for character in right:
            if not character.isdigit():
                break
            digit_prefix += character
        return bool(left.isalpha() and len(digit_prefix) >= 2)

    def input_tokens(text):
        cleaned = str(text or "")
        for separator in [",", "\n", "\t", "(", ")", "[", "]", "{", "}", ":", ";"]:
            cleaned = cleaned.replace(separator, " ")
        suffixes = [
            "제품의",
            "제품",
            "생산량",
            "수량",
            "실적",
            "리스트",
            "목록",
            "조회",
            "찾아줘",
            "보여줘",
            "알려줘",
            "찾아",
            "보여",
            "알려",
        ]
        normalized_suffixes = [normalize_token(suffix) for suffix in suffixes]
        for raw_token in cleaned.split():
            token = normalize_token(raw_token)
            changed = True
            while token and changed:
                changed = False
                for suffix in normalized_suffixes:
                    if token == suffix:
                        token = ""
                        changed = True
                        break
                    if token.endswith(suffix):
                        token = token[: -len(suffix)].strip()
                        changed = True
                        break
            if token:
                yield token

    matched_conditions = []
    for normalized_token in input_tokens(input_text):
        for column in token_columns:
            if column not in result.columns:
                continue
            column_values = result[column].dropna().map(normalize_token)
            if column == "MCP_NO" and looks_like_mcp_prefix(normalized_token):
                if column_values.str.startswith(normalized_token, na=False).any():
                    matched_conditions.append((column, normalized_token, "startswith"))
                    break
            elif normalized_token in set(column_values):
                matched_conditions.append((column, normalized_token, "eq"))
                break

    for column, normalized_token, match_type in matched_conditions:
        values = result[column].map(normalize_token)
        if match_type == "startswith":
            result = result[values.str.startswith(normalized_token, na=False)]
        else:
            result = result[values == normalized_token]

    if not matched_conditions:
        return products_df.head(0).copy()

    selected_columns = [column for column in output_columns if column in result.columns]
    extra_columns = [column for column in products_df.columns if column not in selected_columns and column != "ORG"]
    if selected_columns:
        result = result[[*selected_columns, *extra_columns]]
    return result.drop_duplicates().reset_index(drop=True)
```

---

## Lot Hold 복합 조건 helper 예시

작업자가 처음 작성할 때는 아래 정도의 자연어 설명이면 충분하다.

```text
Lot Hold 또는 Lot 상태를 복합 조건으로 찾는 질문에서는 match_lot_hold_conditions helper를 사용한다.
사용자가 작업대기, Hold 사유, 공정명, Lot ID, IN_TAT/HOLD_TM 조건을 섞어서 입력하면 조회된 Lot/Hold 데이터의 실제 컬럼 값과 매칭해서 일치하는 row를 반환한다.
상태/사유/공정/Lot token은 가능한 컬럼에서 찾고, 24시간 이상처럼 숫자와 이상/이하 표현이 있으면 TAT 계열 컬럼에 조건을 적용한다.
pandas 생성 코드는 이 함수를 재정의하지 말고 match_lot_hold_conditions(input_text, sources[source_alias])처럼 호출한다.
```

아래 Python 코드블록은 실행 환경에 로드되는 helper 정의다.

```python
def match_lot_hold_conditions(input_text, lot_df, current_date=None):
    status_columns = ["LOT_HOLD_STAT_CD", "LOT_STAT_CD", "HOLD_STATUS"]
    reason_columns = ["REASON_CD", "HOLD_CD", "HOLD_REASON", "HOLD_DESC", "EVENT_DESC"]
    lot_columns = ["LOT_ID", "SUB_LOT_ID", "PROD_ID"]
    process_columns = ["OPER_ID", "OPER_NAME", "OPER_SHORT_DESC", "OPER_GRP_VAL_1"]
    tat_columns = ["IN_TAT", "CUM_TAT", "HOLD_TM"]
    output_columns = [
        "LOT_ID",
        "SUB_LOT_ID",
        "PROD_ID",
        "OPER_ID",
        "OPER_NAME",
        "OPER_SHORT_DESC",
        "LOT_HOLD_STAT_CD",
        "LOT_STAT_CD",
        "REASON_CD",
        "HOLD_CD",
        "HOLD_DESC",
        "IN_TAT",
        "CUM_TAT",
        "HOLD_TM",
        "RELEASE_DUE_DATE",
    ]

    result = lot_df.copy()

    def normalize(value):
        return str(value or "").strip().upper()

    def existing(columns):
        return [column for column in columns if column in result.columns]

    text = str(input_text or "")
    normalized_text = normalize(text)

    status_groups = {
        "WAIT": ["작업대기", "대기", "WAIT", "WAITING", "QUEUE"],
        "HOLD": ["HOLD", "홀드", "보류", "작업보류"],
        "RUN": ["작업중", "RUN", "RUNNING", "PROCESSING"],
    }
    matched_status_values = []
    for status_value, aliases in status_groups.items():
        if any(normalize(alias) in normalized_text for alias in aliases):
            matched_status_values.append(status_value)
    if matched_status_values:
        masks = []
        for column in existing(status_columns):
            masks.append(result[column].map(normalize).isin(matched_status_values))
        if masks:
            status_mask = masks[0]
            for mask in masks[1:]:
                status_mask = status_mask | mask
            result = result[status_mask]

    tokens = [token for token in text.replace(",", " ").split() if token.strip()]
    for token in tokens:
        normalized_token = normalize(token)
        if not normalized_token:
            continue

        matched = False
        for column_group in [lot_columns, reason_columns, process_columns]:
            for column in existing(column_group):
                column_values = result[column].dropna().map(normalize)
                if normalized_token in set(column_values):
                    result = result[result[column].map(normalize) == normalized_token]
                    matched = True
                    break
                if len(normalized_token) >= 3:
                    contains_mask = result[column].map(normalize).str.contains(normalized_token, regex=False, na=False)
                    if contains_mask.any():
                        result = result[contains_mask]
                        matched = True
                        break
            if matched:
                break

    tat_match = None
    for raw_token in tokens:
        clean = raw_token.replace("시간", "").replace("H", "").replace("h", "")
        if clean.isdigit():
            tat_match = float(clean)
            break
    if tat_match is not None and any(word in text for word in ["이상", "초과", "over", "greater"]):
        for column in existing(tat_columns):
            values = pd.to_numeric(result[column], errors="coerce")
            if values.notna().any():
                result = result[values >= tat_match]
                break
    elif tat_match is not None and any(word in text for word in ["이하", "미만", "under", "less"]):
        for column in existing(tat_columns):
            values = pd.to_numeric(result[column], errors="coerce")
            if values.notna().any():
                result = result[values <= tat_match]
                break

    if any(word in text for word in ["기한초과", "납기초과", "overdue", "due passed"]) and "RELEASE_DUE_DATE" in result.columns:
        due_values = pd.to_datetime(result["RELEASE_DUE_DATE"], errors="coerce")
        base_date = pd.to_datetime(current_date, errors="coerce") if current_date else pd.Timestamp.today().normalize()
        result = result[due_values.notna() & (due_values < base_date)]

    selected_columns = [column for column in output_columns if column in result.columns]
    if selected_columns:
        result = result[selected_columns]
    return result.drop_duplicates().reset_index(drop=True)

source_alias = list(sources.keys())[0]
result_df = match_lot_hold_conditions("작업대기 Hold 사유 ABN IN_TAT 24시간 이상 Lot 보여줘", sources[source_alias])
```

MongoDB/domain_items에 저장할 pandas_function_cases JSON 예시는 아래처럼 짧게 작성해. 이 JSON에는 실제 `function_code`를 넣지 말고, 어떤 질문에서 어떤 helper 이름을 쓸지에 대한 선택 힌트만 넣어.

```json
{
  "section": "pandas_function_cases",
  "key": "lot_hold_complex_lookup",
  "payload": {
    "display_name": "Lot hold complex lookup",
    "aliases": ["Lot Hold 복합 조회", "Hold 사유 조회", "Lot 상태 찾기"],
    "function_name": "match_lot_hold_conditions",
    "use_when": "사용자가 Lot ID, Hold 상태/사유, 공정명, IN_TAT/HOLD_TM 조건을 섞어서 Lot/Hold 목록을 찾을 때 사용한다.",
    "input_text": "user question",
    "example": {
      "input_text": "작업대기 Hold 사유 ABN IN_TAT 24시간 이상 Lot 보여줘"
    }
  },
  "confidence": "high"
}
```
