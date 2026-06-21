from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_langflow_components_define_top_level_component_subclass() -> None:
    component_files = sorted((PROJECT_ROOT / "langflow_components").rglob("*.py"))
    assert component_files

    for path in component_files:
        code = path.read_text(encoding="utf-8")
        module = ast.parse(code)
        class_names = []
        for node in module.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                if isinstance(base, ast.Name) and "Component" in base.id:
                    class_names.append(node.name)

        assert class_names, f"{path} must define a top-level Component subclass"
        assert "LANGFLOW_AVAILABLE" not in code, f"{path} must not hide the class behind an availability guard"


def test_langflow_components_do_not_reuse_input_names_as_output_names() -> None:
    component_files = sorted((PROJECT_ROOT / "langflow_components").rglob("*.py"))

    for path in component_files:
        module_name = f"component_shape_{path.stem}".replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        component_classes = []
        for value in module.__dict__.values():
            if isinstance(value, type):
                for base in value.__bases__:
                    if base.__name__ == "_Component" or "Component" in base.__name__:
                        component_classes.append(value)

        assert component_classes, f"{path} must define a Component subclass"
        for component_class in component_classes:
            input_names = {getattr(item, "name", None) for item in getattr(component_class, "inputs", [])}
            output_names = {getattr(item, "name", None) for item in getattr(component_class, "outputs", [])}
            input_names.discard(None)
            output_names.discard(None)
            overlap = input_names.intersection(output_names)
            assert not overlap, f"{path} has overlapping input/output names: {sorted(overlap)}"


def test_data_analysis_flow_files_use_clean_sequential_numbering() -> None:
    expected_files = [
        "00_analysis_request_loader.py",
        "01_metadata_context_loader.py",
        "02_intent_prompt_builder.py",
        "03_intent_plan_normalizer.py",
        "04_previous_result_restore_router.py",
        "05_mongodb_data_loader.py",
        "06_previous_result_restore_merger.py",
        "07_dummy_data_retriever.py",
        "08_oracle_query_retriever.py",
        "09_h_api_retriever.py",
        "10_datalake_retriever.py",
        "11_goodocs_retriever.py",
        "12_source_retrieval_merger.py",
        "13_retrieval_payload_adapter.py",
        "14_pandas_prompt_builder.py",
        "15_pandas_code_executor.py",
        "16a_pandas_repair_payload_builder.py",
        "16b_pandas_repair_prompt_builder.py",
        "17_mongodb_data_store.py",
        "18_answer_prompt_builder.py",
        "19_answer_response_builder.py",
        "20_answer_message_adapter.py",
        "21_api_response_builder.py",
    ]
    actual_files = [path.name for path in sorted((PROJECT_ROOT / "langflow_components" / "data_analysis_flow").glob("*.py"))]
    assert actual_files == expected_files

    for path in sorted((PROJECT_ROOT / "langflow_components" / "data_analysis_flow").glob("*.py")):
        module_name = f"data_analysis_flow_order_{path.stem}".replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        display_names = [
            getattr(value, "display_name", "")
            for value in module.__dict__.values()
            if isinstance(value, type) and any("Component" in base.__name__ for base in value.__bases__)
        ]
        expected_prefix = path.stem.split("_", 1)[0].upper()
        assert display_names, f"{path} must define a display_name"
        assert display_names[0].startswith(f"{expected_prefix} "), f"{path.name} display_name should start with {expected_prefix}"


def test_mongodb_metadata_components_expose_full_collection_names() -> None:
    expected_inputs_by_file = {
        "data_analysis_flow/01_metadata_context_loader.py": {
            "domain_collection_name",
            "table_catalog_collection_name",
            "main_flow_filter_collection_name",
        },
        "router_flow/01_metadata_context_loader.py": {
            "domain_collection_name",
            "table_catalog_collection_name",
            "main_flow_filter_collection_name",
        },
        "metadata_qa_flow/01_metadata_context_loader.py": {
            "domain_collection_name",
            "table_catalog_collection_name",
            "main_flow_filter_collection_name",
        },
        "domain_authoring_flow/00_domain_authoring_request_loader.py": {"collection_name"},
        "domain_authoring_flow/07_domain_review_writer.py": {"collection_name"},
        "table_catalog_authoring_flow/00_table_catalog_authoring_request_loader.py": {"collection_name"},
        "table_catalog_authoring_flow/07_table_catalog_review_writer.py": {"collection_name"},
        "main_flow_filters_authoring_flow/00_main_flow_filter_authoring_request_loader.py": {"collection_name"},
        "main_flow_filters_authoring_flow/07_main_flow_filter_review_writer.py": {"collection_name"},
    }

    for relative_path, expected_inputs in expected_inputs_by_file.items():
        path = PROJECT_ROOT / "langflow_components" / relative_path
        module_name = f"collection_contract_{path.stem}".replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        component_classes = [
            value
            for value in module.__dict__.values()
            if isinstance(value, type) and any("Component" in base.__name__ for base in value.__bases__)
        ]
        assert component_classes, f"{path} must define a Component subclass"
        input_names = {getattr(item, "name", None) for item in getattr(component_classes[0], "inputs", [])}

        assert expected_inputs.issubset(input_names)
        assert "collection_prefix" not in input_names
        assert "metadata_source" not in input_names
        assert "metadata_dir" not in input_names


def test_metadata_authoring_duplicate_action_inputs_are_dropdowns() -> None:
    request_loader_files = [
        "domain_authoring_flow/00_domain_authoring_request_loader.py",
        "table_catalog_authoring_flow/00_table_catalog_authoring_request_loader.py",
        "main_flow_filters_authoring_flow/00_main_flow_filter_authoring_request_loader.py",
    ]
    override_files = [
        "domain_authoring_flow/05_domain_similarity_checker.py",
        "table_catalog_authoring_flow/05_table_catalog_similarity_checker.py",
        "main_flow_filters_authoring_flow/05_main_flow_filter_similarity_checker.py",
    ]

    for relative_path in request_loader_files:
        duplicate_input = _component_input(relative_path, "duplicate_action")
        assert duplicate_input.__class__.__name__ == "_DropdownField"
        assert duplicate_input.value == "ask"
        assert duplicate_input.options == ["ask", "merge", "replace", "skip", "create_new"]

    for relative_path in override_files:
        duplicate_input = _component_input(relative_path, "duplicate_action")
        assert duplicate_input.__class__.__name__ == "_DropdownField"
        assert duplicate_input.value == "use_payload"
        assert duplicate_input.options == ["use_payload", "ask", "merge", "replace", "skip", "create_new"]

    writer_files = [
        "domain_authoring_flow/07_domain_review_writer.py",
        "table_catalog_authoring_flow/07_table_catalog_review_writer.py",
        "main_flow_filters_authoring_flow/07_main_flow_filter_review_writer.py",
    ]
    for relative_path in writer_files:
        writer_inputs = {getattr(item, "name", None) for item in _component_class(relative_path).inputs}
        assert "duplicate_action" not in writer_inputs


def test_fixed_choice_inputs_are_dropdowns() -> None:
    fixed_choice_inputs = {
        "data_analysis_flow/05_mongodb_data_loader.py": {
            "enabled": ("true", ["true", "false"]),
            "restore_mode": ("auto", ["auto", "preview", "full"]),
        },
        "data_analysis_flow/16a_pandas_repair_payload_builder.py": {
            "max_attempts": ("1", ["0", "1", "2"]),
        },
        "data_analysis_flow/17_mongodb_data_store.py": {
            "enabled": ("true", ["true", "false"]),
        },
        "session_state_flow/00_mongodb_session_state_loader.py": {
            "enabled": ("true", ["true", "false"]),
        },
        "session_state_flow/01_mongodb_session_state_writer.py": {
            "enabled": ("true", ["true", "false"]),
        },
        "domain_authoring_flow/00_domain_authoring_request_loader.py": {
            "load_existing": ("true", ["true", "false"]),
        },
        "table_catalog_authoring_flow/00_table_catalog_authoring_request_loader.py": {
            "load_existing": ("true", ["true", "false"]),
        },
        "main_flow_filters_authoring_flow/00_main_flow_filter_authoring_request_loader.py": {
            "load_existing": ("true", ["true", "false"]),
        },
    }

    for relative_path, inputs in fixed_choice_inputs.items():
        for input_name, (expected_value, expected_options) in inputs.items():
            input_item = _component_input(relative_path, input_name)
            assert input_item.__class__.__name__ == "_DropdownField"
            assert input_item.value == expected_value
            assert input_item.options == expected_options


def test_pandas_repair_components_use_single_output_ports() -> None:
    payload_outputs = _component_outputs("data_analysis_flow/16a_pandas_repair_payload_builder.py")
    assert list(payload_outputs) == ["payload_out"]
    assert getattr(payload_outputs["payload_out"], "group_outputs", False) is False
    assert getattr(payload_outputs["payload_out"], "method", "") == "build_payload"

    prompt_outputs = _component_outputs("data_analysis_flow/16b_pandas_repair_prompt_builder.py")
    assert list(prompt_outputs) == ["repair_prompt"]
    assert getattr(prompt_outputs["repair_prompt"], "group_outputs", False) is False
    assert getattr(prompt_outputs["repair_prompt"], "method", "") == "build_prompt"

def test_data_analysis_prompt_builders_use_single_prompt_output_pattern() -> None:
    expected_prompt_outputs = {
        "data_analysis_flow/02_intent_prompt_builder.py": "intent_prompt",
        "data_analysis_flow/14_pandas_prompt_builder.py": "pandas_prompt",
        "data_analysis_flow/16b_pandas_repair_prompt_builder.py": "repair_prompt",
        "data_analysis_flow/18_answer_prompt_builder.py": "answer_prompt",
    }

    for relative_path, output_name in expected_prompt_outputs.items():
        outputs = _component_outputs(relative_path)
        output_item = outputs[output_name]
        assert getattr(output_item, "group_outputs", False) is False
        assert not any(name.endswith("_prompt_text") for name in outputs)


def test_metadata_authoring_variable_builders_expose_prompt_template_variables() -> None:
    expected_outputs = {
        "domain_authoring_flow/01_domain_text_refinement_variables_builder.py": ["raw_text"],
        "domain_authoring_flow/03_domain_authoring_variables_builder.py": ["authoring_context"],
        "domain_authoring_flow/06_domain_review_variables_builder.py": ["review_input_json"],
        "table_catalog_authoring_flow/01_table_catalog_text_refinement_variables_builder.py": ["raw_text"],
        "table_catalog_authoring_flow/03_table_catalog_authoring_variables_builder.py": ["authoring_context"],
        "table_catalog_authoring_flow/06_table_catalog_review_variables_builder.py": ["review_input_json"],
        "main_flow_filters_authoring_flow/01_main_flow_filter_text_refinement_variables_builder.py": ["raw_text"],
        "main_flow_filters_authoring_flow/03_main_flow_filter_authoring_variables_builder.py": ["authoring_context"],
        "main_flow_filters_authoring_flow/06_main_flow_filter_review_variables_builder.py": ["review_input_json"],
    }

    for relative_path, output_names in expected_outputs.items():
        outputs = _component_outputs(relative_path)
        assert list(outputs) == output_names
        assert not any(name.endswith("_prompt") for name in outputs)


def test_source_retrieval_merger_exposes_dummy_input_for_local_validation() -> None:
    input_names = {
        getattr(item, "name", None)
        for item in _component_class("data_analysis_flow/12_source_retrieval_merger.py").inputs
    }

    assert {
        "dummy_retrieval",
        "oracle_retrieval",
        "h_api_retrieval",
        "datalake_retrieval",
        "goodocs_retrieval",
    }.issubset(input_names)


def _component_input(relative_path: str, input_name: str):
    component_class = _component_class(relative_path)
    for input_item in getattr(component_class, "inputs", []):
        if getattr(input_item, "name", None) == input_name:
            return input_item
    raise AssertionError(f"{relative_path} must expose input {input_name}")


def _component_outputs(relative_path: str) -> dict[str, object]:
    component_class = _component_class(relative_path)
    return {getattr(item, "name", ""): item for item in getattr(component_class, "outputs", [])}


def _component_class(relative_path: str):
    path = PROJECT_ROOT / "langflow_components" / relative_path
    module_name = f"output_contract_{path.stem}".replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    component_classes = [
        value
        for value in module.__dict__.values()
        if isinstance(value, type) and any("Component" in base.__name__ for base in value.__bases__)
    ]
    assert component_classes, f"{path} must define a Component subclass"
    return component_classes[0]

