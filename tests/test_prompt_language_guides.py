from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROMPT_DIR = ROOT / "langflow_components" / "data_analysis_flow" / "prompts"
SCRIPT = ROOT / "tools" / "validate_prompt_language_guides.py"


def test_prompt_language_guides_exist_for_three_primary_llm_prompts() -> None:
    expected = {
        "02_intent_prompt_en.md",
        "02_intent_prompt_ko.md",
        "14_pandas_prompt_en.md",
        "14_pandas_prompt_ko.md",
        "18_answer_prompt_en.md",
        "18_answer_prompt_ko.md",
        "02_SPECIALIZED_INTENT_PROMPT.md",
        "02_SPECIALIZED_PROMPT_INPUT_GUIDE.md",
        "SPECIALIZED_FUNCTIONS_INPUT_GUIDE.md",
        "PROMPT_LANGUAGE_VALIDATION_MATRIX.md",
    }

    assert expected.issubset({path.name for path in PROMPT_DIR.iterdir()})


def test_korean_prompt_guides_preserve_machine_contract_tokens() -> None:
    tokens_by_file = {
        "02_intent_prompt_ko.md": [
            "intent_type",
            "analysis_kind",
            "retrieval_jobs",
            "step_plan",
            "apply_pandas_function_case",
        ],
        "02_SPECIALIZED_INTENT_PROMPT.md": [
            "component_token_product_lookup",
            "match_product_tokens",
            "analysis_recipes",
            "source_scope.date_scope",
            "product_terms",
            "equipment_status",
            "lot_status",
        ],
        "14_pandas_prompt_ko.md": [
            "result_df",
            "sources",
            "plan",
            "state",
            "step_outputs",
            "input_step_id",
        ],
        "18_answer_prompt_ko.md": ["answer_message", "data.rows", "column_standardization"],
    }

    for filename, tokens in tokens_by_file.items():
        text = (PROMPT_DIR / filename).read_text(encoding="utf-8")
        for token in tokens:
            assert token in text


def test_prompt_language_validation_matrix_covers_ten_representative_questions() -> None:
    module = _load_validation_script()
    matrix = (PROMPT_DIR / "PROMPT_LANGUAGE_VALIDATION_MATRIX.md").read_text(encoding="utf-8")

    assert len(module.VALIDATION_QUESTIONS) == 10
    for question in module.VALIDATION_QUESTIONS:
        assert question in matrix


def test_prompt_language_validation_script_passes() -> None:
    module = _load_validation_script()
    assert module.main() == 0


def test_specialized_intent_prompt_keeps_source_local_date_scope() -> None:
    prompt = (PROMPT_DIR / "02_SPECIALIZED_INTENT_PROMPT.md").read_text(encoding="utf-8")

    assert "생산량 상위 제품을 먼저 뽑고 같은 제품의 현재 재공/WIP" in prompt
    assert "analysis_kind를 rank_wip_then_join_production으로 설정하지 않는다" in prompt
    assert "source_scope.date_scope=yesterday" in prompt
    assert "source_scope.date_scope=current/today" in prompt


def test_specialized_product_helper_uses_mcp_prefix_and_ignores_org() -> None:
    guide = (PROMPT_DIR / "SPECIALIZED_FUNCTIONS_INPUT_GUIDE.md").read_text(encoding="utf-8")
    assert "의미 있는 제품 속성 토큰이 모두 매칭되어야 한다" in guide
    assert "부분 매칭 결과를 반환하지 말고 빈 DataFrame" in guide
    assert "원본 source row의 OPER_NAME, PRODUCTION, WIP 같은 후속 집계 column을 보존" in guide
    assert "그 output을 직접 groupby하지 말고 product key table로만 사용" in guide
    product_code = guide.split("```python", 1)[1].split("```", 1)[0]
    function_code = "\n".join(
        line for line in product_code.splitlines() if not line.startswith(("source_alias =", "result_df ="))
    )
    namespace: dict[str, object] = {}
    exec(function_code, namespace)

    products = pd.DataFrame(
        [
            {"TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "MCP_NO": "L-269P1Q", "ORG": "ASSY", "OPER_NAME": "D/A1", "PRODUCTION": 10},
            {"TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "MCP_NO": "L-55XM2Q", "ORG": "TEST", "OPER_NAME": "D/A2", "PRODUCTION": 20},
        ]
    )

    result = namespace["match_product_tokens"]("64G L-269제품 ASSY", products)
    org_only = namespace["match_product_tokens"]("ASSY", products)
    partial_match = namespace["match_product_tokens"]("LPDDR4 LC 64G", products)
    exact_match = namespace["match_product_tokens"]("64G L-269제품", products)

    assert result.empty
    assert result.attrs["matched_conditions"] == [
        {"token": "64G", "column": "DEN", "match_type": "eq", "value": "64G"},
        {"token": "L-269제품", "column": "MCP_NO", "match_type": "startswith", "value": "L-269"},
        {"token": "ASSY", "column": "", "match_type": "unmatched", "value": "ASSY"},
    ]
    assert org_only.empty
    assert org_only.attrs["matched_conditions"] == [
        {"token": "ASSY", "column": "", "match_type": "unmatched", "value": "ASSY"}
    ]
    assert partial_match.empty
    assert partial_match.attrs["matched_conditions"] == [
        {"token": "LPDDR4", "column": "", "match_type": "unmatched", "value": "LPDDR4"},
        {"token": "LC", "column": "", "match_type": "unmatched", "value": "LC"},
        {"token": "64G", "column": "DEN", "match_type": "eq", "value": "64G"},
    ]
    assert exact_match["MCP_NO"].tolist() == ["L-269P1Q"]
    assert exact_match["OPER_NAME"].tolist() == ["D/A1"]
    assert exact_match["PRODUCTION"].tolist() == [10]
    assert "ORG" not in exact_match.columns


def test_component_token_product_lookup_metadata_is_selection_hint_only() -> None:
    metadata = json.loads((ROOT / "metadata" / "domain_items.json").read_text(encoding="utf-8"))
    case = metadata["pandas_function_cases"]["component_token_product_lookup"]

    assert case["function_name"] == "match_product_tokens"
    assert "function_code" not in case
    assert "MCP_NO" in case.get("token_columns", [])
    assert "output_order" not in case
    assert "output_columns" not in case


def _load_validation_script():
    spec = importlib.util.spec_from_file_location("validate_prompt_language_guides", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module
