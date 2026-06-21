from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "validate_llm_in_loop.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_llm_in_loop", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extract_json_object_from_fenced_response():
    module = _load_module()
    parsed = module.extract_json_object('```json\n{"status":"ok","items":[1]}\n```')
    assert parsed == {"status": "ok", "items": [1]}


def test_generated_code_safety_rejects_imports_and_file_access():
    module = _load_module()
    errors = module.check_code_safety("import os\nresult_df = pd.DataFrame([])")
    assert any("Imports are not allowed" in item for item in errors)

    errors = module.check_code_safety("result_df = pd.DataFrame([{'x': open('a').read()}])")
    assert any("Forbidden call: open" in item for item in errors)


def test_generated_code_safety_accepts_basic_pandas_code():
    module = _load_module()
    code = """
df = sources["wip"].copy()
result_df = df.groupby(["MODE"], dropna=False, as_index=False)["WIP"].sum()
"""
    assert module.check_code_safety(code) == []


def test_generated_pandas_result_columns_are_normalized_for_rank_join():
    module = _load_module()
    plan = {
        "analysis_kind": "rank_wip_then_join_production",
        "product_grain": ["MODE"],
    }
    pandas_plan = {
        "code": """
result_df = pd.DataFrame([
    {"RANK_GROUP": "DA", "MODE": "LPDDR5", "WIP": 10, "rank": 1, "PRODUCTION_sum": 7}
])
"""
    }

    result = module.execute_generated_pandas_code(pandas_plan, plan, {}, {})

    assert result["status"] == "ok"
    assert result["columns"] == ["RANK_GROUP", "WIP_RANK", "MODE", "WIP", "PRODUCTION"]
    assert "PRODUCTION_sum" not in result["columns"]
    assert "rank" not in result["columns"]


def test_generated_pandas_korean_measure_labels_are_normalized():
    module = _load_module()
    frame = module.pd.DataFrame(
        [
            {"MODE": "LPDDR5", "생산량": 10, "재공 수량": 3},
        ]
    )

    normalized = module.normalize_result_columns(frame, {"analysis_kind": "aggregate_join", "product_grain": ["MODE"]})

    assert list(normalized.columns) == ["MODE", "PRODUCTION", "WIP"]
