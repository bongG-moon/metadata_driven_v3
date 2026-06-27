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


def test_specialized_product_helper_uses_mcp_prefix_and_ignores_org() -> None:
    guide = (PROMPT_DIR / "SPECIALIZED_FUNCTIONS_INPUT_GUIDE.md").read_text(encoding="utf-8")
    product_code = guide.split("```python", 1)[1].split("```", 1)[0]
    function_code = "\n".join(
        line for line in product_code.splitlines() if not line.startswith(("source_alias =", "result_df ="))
    )
    namespace: dict[str, object] = {}
    exec(function_code, namespace)

    products = pd.DataFrame(
        [
            {"TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "LFBGA", "MCP_NO": "L-269P1Q", "ORG": "ASSY", "PRODUCTION": 10},
            {"TECH": "FC", "DEN": "64G", "MODE": "LPDDR5", "PKG_TYPE1": "UFBGA", "MCP_NO": "L-55XM2Q", "ORG": "TEST", "PRODUCTION": 20},
        ]
    )

    result = namespace["match_product_tokens"]("64G L-269제품 ASSY", source_df=products)
    org_only = namespace["match_product_tokens"]("ASSY", products)

    assert result["MCP_NO"].tolist() == ["L-269P1Q"]
    assert result["PRODUCTION"].tolist() == [10]
    assert "ORG" not in result.columns
    assert org_only.empty


def test_component_token_product_lookup_metadata_is_selection_hint_only() -> None:
    metadata = json.loads((ROOT / "metadata" / "domain_items.json").read_text(encoding="utf-8"))
    case = metadata["pandas_function_cases"]["component_token_product_lookup"]

    assert case["function_name"] == "match_product_tokens"
    assert "function_code" not in case
    assert "token_columns" not in case
    assert "output_order" not in case
    assert "output_columns" not in case


def _load_validation_script():
    spec = importlib.util.spec_from_file_location("validate_prompt_language_guides", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module
