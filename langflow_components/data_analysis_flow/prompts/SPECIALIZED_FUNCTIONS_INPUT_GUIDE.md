# Specialized Functions 입력 가이드

이 파일은 14 Pandas Prompt Builder와 15 Pandas Code Executor의 `Specialized Functions` 입력에 같은 내용으로 넣는다.

- 14번 입력은 pandas code LLM에게 어떤 helper를 호출해야 하는지 알려준다.
- 15번 입력은 실제 실행 시점에 helper 함수를 로드한다.
- 15번의 `Payload`는 13 Retrieval Payload Adapter의 `Payload`를 직접 연결한다.
- 15번 노드가 두 개 있으면 두 15번 노드 모두 같은 `Specialized Functions` text input을 연결한다.
- 선택된 function case의 함수 구현이 15번 입력 또는 metadata `function_code`에 없으면 pandas 분석은 진행하지 않는다.
- 14번은 이 입력 안의 자연어 설명과 Python 함수 예시를 LLM에게 그대로 보여주고, LLM은 이를 참고해서 최종 pandas code를 작성한다.
- 생성된 pandas code가 helper 함수를 inline으로 정의한 뒤 호출해도 되고, helper 호출만 남기는 경우에는 15번에도 같은 Specialized Functions 입력을 연결해 실행 환경에서 로드되게 한다.
- Lot/Hold 집계, 재공 상위 공정, 장비 대수 같은 분석 recipe는 여기에 helper 함수로 넣지 않는다. 그런 항목은 `raw_text_input_example.md`로 domain authoring flow를 태워 analysis_recipes로 저장한다.

작업자가 처음 작성할 때는 너무 엄격한 JSON이나 긴 스키마를 쓰지 말고, 아래처럼 자연어 설명과 Python helper 함수만 작성하면 된다.

## 실제 붙여넣을 값

아래 `text` 설명 블록과 `python` 코드블록을 함께 복사해서 `14 Pandas Prompt Builder > Specialized Functions`, 첫 번째 `15 Pandas Code Executor > Specialized Functions`, 두 번째 `15 Pandas Code Executor > Specialized Functions`에 같은 값으로 넣는다.

```text
제품 토큰으로 제품 리스트나 제품 조건 기반 metric을 찾는 질문에서는 match_product_tokens helper를 사용한다.
이 helper는 조회된 제품 데이터에서 TECH, DEN/DENSITY, MODE, PKG1/PKG_TYPE1, PKG2/PKG_TYPE2, LEAD, MCP_NO 값을 입력 토큰과 비교해서 일치하는 행을 반환한다.
제품 검색에서는 의미 있는 제품 속성 토큰이 모두 매칭되어야 한다. 예를 들어 `lpddr4 lc 64g`에서 `64g`만 DEN에 매칭되고 `lpddr4`, `lc`가 어떤 제품 컬럼에도 매칭되지 않으면 부분 매칭 결과를 반환하지 말고 빈 DataFrame을 반환한다.
helper는 비교 전에 DENSITY를 DEN으로, PKG1/PKG_TYP1을 PKG_TYPE1로, PKG2/PKG_TYP2를 PKG_TYPE2로 맞춘 표준 컬럼을 만든다.
따라서 helper output을 downstream join/filter에 쓸 때는 DEN, PKG_TYPE1, PKG_TYPE2 같은 표준 product key를 사용한다.
제품 리스트만 보여주는 질문이 아니라 생산량/재공/공정별 집계 같은 metric 질문이면 helper output은 product key만 남기지 말고 원본 source row의 OPER_NAME, PRODUCTION, WIP 같은 후속 집계 column을 보존해야 한다.
만약 생성 코드에서 helper output이 product key column만 가진 DataFrame이 되었다면, 그 output을 직접 groupby하지 말고 product key table로만 사용해서 원본 sources[source_alias]를 다시 filter/merge한 뒤 집계한다.
MCP_NO는 사용자가 L-269처럼 앞부분만 입력해도 실제 L-269P1Q 같은 값과 startswith로 매칭한다.
G-777제품처럼 제품 토큰 뒤에 한국어 명사/동사가 붙어도 G-777 token으로 정리해서 매칭한다.
어떤 입력 토큰이 어떤 컬럼 조건으로 해석됐는지 기록하기 위해 반환 DataFrame의 attrs["matched_conditions"]에 token, column, match_type, value를 남긴다.
matched_conditions에 match_type="unmatched"가 남은 의미 있는 제품 속성 토큰이 있으면 해당 제품 표현은 source data에 정확히 존재하지 않는 것으로 보고 빈 DataFrame을 반환한다.
pandas 생성 코드는 이 helper 예시 형태를 참고해서 작성하고, helper를 호출할 때는 match_product_tokens(input_text, sources[source_alias])처럼 positional argument를 사용한다.
```

아래 Python 코드블록은 실행 환경에 로드되는 helper 정의다. 이 코드블록은 14번, 첫 번째 15번, 두 번째 15번의 `Specialized Functions` 입력에 같은 내용으로 넣는다.

```python
def match_product_tokens(input_text, source_df):
    token_columns = ["TECH", "DEN", "MODE", "PKG_TYPE1", "PKG_TYPE2", "LEAD", "MCP_NO"]
    product_key_columns = ["TECH", "DEN", "PKG_TYPE1", "LEAD", "PKG_TYPE2", "MODE", "MCP_NO"]
    if source_df is None:
        return pd.DataFrame()

    result = source_df.copy()
    alias_candidates = {
        "DEN": ["DENSITY", "DEN_TYP"],
        "PKG_TYPE1": ["PKG1", "PKG_TYP1", "PKG_TYP"],
        "PKG_TYPE2": ["PKG2", "PKG_TYP2", "PKG_TYP_2"],
        "MODE": ["PROD_TYP"],
        "LEAD": ["LEAD_CNT"],
        "MCP_NO": ["PROD_GRP_ID", "MCP_SALE_CD"],
        "TECH": ["TECH_NM"],
    }
    for standard_column, candidates in alias_candidates.items():
        if standard_column in result.columns:
            continue
        for candidate in candidates:
            if candidate in result.columns:
                result[standard_column] = result[candidate]
                break

    def normalize_token(value):
        return str(value or "").strip().upper()

    def clean_input_token(token):
        token = normalize_token(token)
        for suffix in ["제품의", "제품", "생산량", "수량", "실적", "리스트", "목록", "조회", "찾아줘", "보여줘", "알려줘", "찾아", "보여", "알려"]:
            normalized_suffix = normalize_token(suffix)
            if token.endswith(normalized_suffix):
                token = token[: -len(normalized_suffix)]
        return token

    ignored_tokens = {
        "오늘",
        "현재",
        "어제",
        "금일",
        "전일",
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
    }
    ignored_tokens = {normalize_token(token) for token in ignored_tokens}

    matched_conditions = []
    cleaned_text = str(input_text or "").replace(",", " ")
    for raw_token in cleaned_text.split():
        normalized_token = clean_input_token(raw_token)
        if not normalized_token:
            continue
        if normalized_token in ignored_tokens:
            continue
        matched = False
        for column in token_columns:
            if column not in result.columns:
                continue
            column_values = result[column].dropna().map(normalize_token)
            if column == "MCP_NO" and "-" in normalized_token:
                if column_values.str.startswith(normalized_token, na=False).any():
                    matched_conditions.append({"token": raw_token, "column": column, "match_type": "startswith", "value": normalized_token})
                    matched = True
                    break
            elif normalized_token in set(column_values):
                matched_conditions.append({"token": raw_token, "column": column, "match_type": "eq", "value": normalized_token})
                matched = True
                break
        if not matched:
            matched_conditions.append({"token": raw_token, "column": "", "match_type": "unmatched", "value": normalized_token})

    filter_conditions = [condition for condition in matched_conditions if condition["column"]]
    unmatched_conditions = [condition for condition in matched_conditions if condition["match_type"] == "unmatched"]
    if unmatched_conditions:
        empty_result = source_df.head(0).copy()
        empty_result.attrs["matched_conditions"] = matched_conditions
        return empty_result

    for condition in filter_conditions:
        column = condition["column"]
        normalized_token = condition["value"]
        match_type = condition["match_type"]
        values = result[column].map(normalize_token)
        if match_type == "startswith":
            result = result[values.str.startswith(normalized_token, na=False)]
        else:
            result = result[values == normalized_token]

    if not filter_conditions:
        empty_result = source_df.head(0).copy()
        empty_result.attrs["matched_conditions"] = matched_conditions
        return empty_result

    selected_columns = [column for column in product_key_columns if column in result.columns]
    extra_columns = [column for column in source_df.columns if column not in selected_columns and column != "ORG"]
    if selected_columns:
        # 제품 metric/공정별 집계에서 OPER_NAME, PRODUCTION, WIP 같은 원본 컬럼이 필요하므로
        # product key만 남기지 말고 원본 source의 나머지 컬럼도 보존한다.
        result = result[[*selected_columns, *extra_columns]]
    result = result.drop_duplicates().reset_index(drop=True)
    result.attrs["matched_conditions"] = matched_conditions
    return result
```
