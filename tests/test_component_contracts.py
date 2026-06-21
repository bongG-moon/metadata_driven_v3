from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_FILES = sorted((ROOT / "langflow_components").glob("*/*.py"))


def test_numbered_components_are_standalone_imports():
    forbidden_modules = {"reference_runtime", "langflow_components", "utils", "helpers"}
    for path in COMPONENT_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.level == 0, f"{path.name} uses relative import"
                if node.module:
                    assert node.module.split(".")[0] not in forbidden_modules, path.name
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_modules, path.name


def test_numbered_components_can_load_one_file_at_a_time():
    for path in COMPONENT_FILES:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)


def test_final_payload_keeps_rows_in_data_only():
    from reference_runtime import run_agent

    payload = run_agent(
        "오늘 DA, WB공정에서 각각 재공 상위 3개 제품을 뽑아주고 해당 제품들의 오늘 생산량도 보여줘",
        root=str(ROOT),
    )

    assert payload["data"]["rows"]
    assert all("rows" not in result for result in payload["source_results"])
    assert all("preview_rows" in result for result in payload["source_results"])
