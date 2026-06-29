# Specialized Functions 입력 가이드

이 파일은 14 Pandas Prompt Builder, 15 Pandas Code Executor, 17 Pandas Repair Code Executor의 `Specialized Functions` 입력에 같은 내용으로 넣는다.

- 14번 입력은 pandas code LLM에게 선택된 helper의 의도와 사용 형태를 알려준다.
- 15번 입력은 실제 실행 시점에 helper 함수를 로드한다.
- 15번의 `Payload`는 13 Retrieval Payload Adapter의 `Payload`를 직접 연결한다.
- repair branch를 사용할 때는 15번과 17번 노드 모두 같은 `Specialized Functions` text input을 연결한다.
- 선택된 function case의 함수 구현이 15번 입력 또는 metadata `function_code`에 없으면 pandas 분석은 진행하지 않는다.
- Lot/Hold 집계, 재공 상위 공정, 장비 대수 같은 분석 recipe는 여기에 helper 함수로 넣지 않는다. 그런 항목은 `raw_text_input_example.md`로 domain authoring flow를 태워 analysis_recipes로 저장한다.

## 작성 원칙

여러 helper를 한 입력에 넣을 때는 반드시 함수별 block으로 나눈다.

````text
## function_name: 함수명

이 block은 pandas_function_case.function_name이 함수명일 때만 사용한다.
이 helper의 용도와 input_text 규칙을 짧게 적는다.

```text
def 함수명(input_text, source_df):
    ...
```
````

- 설명은 전역 공통 설명으로 쓰지 말고 해당 `function_name` block 안에만 쓴다.
- 한 helper의 token/column 규칙을 다른 helper block에 섞지 않는다.
- 14번은 선택된 `function_name`과 같은 block만 참고하도록 구성되어 있다.
- 15번은 필요한 함수 정의만 로드하므로, 같은 입력에 helper가 여러 개 있어도 선택된 함수만 실행된다.

## 실제 붙여넣을 값

아래 전체를 복사해서 `14 Pandas Prompt Builder > Specialized Functions`, `15 Pandas Code Executor > Specialized Functions`, `17 Pandas Repair Code Executor > Specialized Functions`에 같은 값으로 넣는다.

````text
## function_name: match_product_tokens

이 block은 pandas_function_case.function_name이 match_product_tokens일 때만 사용한다.
제품 토큰으로 제품 리스트나 제품 조건 기반 metric을 찾는 질문에서 사용한다.
input_text에는 질문에 있는 제품 속성 token 전체를 넣는다. 예를 들어 `오늘 da에서 UFBGA qdp제품 생산량`은 `UFBGA qdp`를 넣고, `qdp` 하나만 넣지 않는다.
input_text에는 날짜/시점, 공정 scope, metric/동사 표현은 넣지 않는다. 예를 들어 오늘, 어제, da에서, 생산량, 재공, 알려줘는 제외한다.
TECH, DEN/DENSITY, MODE, PKG1/PKG_TYPE1, PKG2/PKG_TYPE2, LEAD, MCP_NO 값을 입력 token과 비교해서 일치하는 행을 반환한다.
제품 검색에서는 의미 있는 제품 속성 토큰이 모두 매칭되어야 한다. 일부 token만 매칭되면 부분 매칭 결과를 반환하지 말고 빈 DataFrame을 반환한다.
MCP_NO는 사용자가 L-269처럼 앞부분만 입력해도 실제 L-269P1Q 같은 값과 startswith로 매칭한다.
어떤 입력 token이 어떤 컬럼 조건으로 해석됐는지 반환 DataFrame의 attrs["matched_conditions"]에 token, column, match_type, value를 남긴다.
제품 metric/공정별 집계 질문에서는 helper output에 원본 source row의 OPER_NAME, PRODUCTION, WIP 같은 후속 집계 column을 보존한다.
만약 helper output이 product key column만 가진 DataFrame이면, 그 output을 직접 groupby하지 말고 product key table로만 사용해서 원본 sources[source_alias]를 다시 filter/merge한 뒤 집계한다.

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
        result = result[[*selected_columns, *extra_columns]]
    result = result.drop_duplicates().reset_index(drop=True)
    result.attrs["matched_conditions"] = matched_conditions
    return result
```
````
