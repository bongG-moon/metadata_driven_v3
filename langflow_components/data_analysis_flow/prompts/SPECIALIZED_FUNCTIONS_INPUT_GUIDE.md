이 파일의 함수 코드를 14 Pandas Prompt Builder의 `Specialized Functions` 입력에 넣고, 14 Pandas Prompt Builder의 `Prompt Payload`를 15 Pandas Code Executor의 `Payload`로 연결해. 선택된 function case의 함수 구현이 이 입력 또는 metadata `function_code`에 없으면 pandas 분석은 진행하지 않는다.

제품 토큰으로 제품 리스트를 찾는 질문이면, 아래 참고 함수 형태를 기준으로 pandas 코드를 작성해. 조회된 제품 데이터에서 TECH, DEN/DENSITY, MODE, PKG1/PKG_TYPE1, PKG2/PKG_TYPE2, LEAD, MCP_NO 컬럼 값을 입력 토큰과 비교해서 일치하는 제품 행을 반환해. MCP_NO는 사용자가 `L-269`처럼 앞부분만 입력해도 실제 `L-269P1Q` 같은 값과 startswith로 매칭한다. 아래 코드는 참고 예시이므로, 실제 sources alias와 존재하는 컬럼에 맞게 조정해서 result_df를 만들어.

```python
def match_product_tokens(input_text, products_df):
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

    matched_conditions = []
    for token in str(input_text or "").split():
        normalized_token = normalize_token(token)
        if not normalized_token:
            continue
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
    if selected_columns:
        result = result[selected_columns]
    return result.drop_duplicates().reset_index(drop=True)

source_alias = list(sources.keys())[0]
result_df = match_product_tokens("64G L-269", sources[source_alias])
```

---

Lot Hold 또는 Lot 상태를 복합 조건으로 찾는 질문이면, 아래 참고 함수 형태를 기준으로 pandas 코드를 작성해. 사용자가 "작업대기 Hold 사유 ABN IN_TAT 24시간 이상 Lot 보여줘"처럼 상태, 사유, 공정, Lot ID, TAT 조건을 섞어서 입력하면 조회된 Lot/Hold 데이터의 실제 컬럼 값과 매칭해서 일치하는 row를 반환해. 아래 코드는 참고 예시이므로, 실제 sources alias와 존재하는 컬럼에 맞게 조정해서 result_df를 만들어.

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
