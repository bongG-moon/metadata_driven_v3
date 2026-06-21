# Langflow Components

This folder contains standalone custom components for Langflow Desktop.

## Custom Component Shape

Langflow Desktop scans only top-level classes when it builds a custom component.
Each component file must keep this shape:

```python
from lfx.custom.custom_component.component import Component


class MyComponent(Component):
    ...
```

Do not wrap the `Component` import or class definition in `try:`, `if LANGFLOW_AVAILABLE:`,
or another conditional block. The code can be standalone without sibling imports, but the
`Component` subclass itself must be visible at module top level.

## Split Flow Direction

The recommended Langflow shape is now a routed split flow with independently runnable subflows:

1. `router_flow/` classifies the user request and produces `selected_flow`.
2. `05 Orchestrator Response Builder` packages the selected subflow API call as `subflow_call.api_url + subflow_call.input_value`.
3. A direct Langflow router canvas uses `06 Selected Flow API Runner` to call exactly one selected subflow API.
4. `06 Selected Flow API Runner.Message` goes to the single Chat Output.
5. Each subflow should remain runnable on its own with one Chat Input and one Chat Output.
6. The old combined `main_flow/` canvas has been removed; new wiring should use the split flows directly.

This keeps metadata/help/catalog questions out of the heavy data-analysis path and makes future request types additive.

## Component Rules

- Do not import sibling project files from numbered component files.
- Pass compact `payload` dictionaries between nodes.
- Pass compact previous `state.current_data` into request loader nodes when possible.
- In `data_analysis_flow/`, call `05 MongoDB Data Loader` only through the `04 Previous Result Restore Router` branch when full previous rows are required.
- Store source `runtime_sources` and pandas `analysis.rows` in the MongoDB result collection immediately after pandas execution.
- Preserve `state`, `current_data`, `followup_source_results`, and `data_ref` fields for follow-up questions.
- For operating inside Langflow Desktop, prefer the `lfx.*` imports used by the generated files.

## Flow Connection Guides

Detailed wiring guides now live with each flow folder:

- `../docs/ROUTED_RUN_FLOW_SESSION_WIRING_GUIDE.md` for the full router + selected subflow + session-state wiring
- `router_flow/CONNECTION_GUIDE.md`
- `metadata_qa_flow/CONNECTION_GUIDE.md`
- `data_analysis_flow/CONNECTION_GUIDE.md`
- `report_generation_flow/CONNECTION_GUIDE.md`
- `report_generation_flow/example_questions.md`
- `operations_diagnosis_flow/CONNECTION_GUIDE.md`
- `operations_diagnosis_flow/example_questions.md`
- `domain_authoring_flow/CONNECTION_GUIDE.md`
- `table_catalog_authoring_flow/CONNECTION_GUIDE.md`
- `main_flow_filters_authoring_flow/CONNECTION_GUIDE.md`

`report_generation_flow` and `operations_diagnosis_flow` examples are written as E2E business requests. They should look like complete report/diagnosis tasks, not only follow-up prompts such as "방금 결과로 ...".

## Split Runtime LLM Node Pattern

Start with `router_flow/`, then call the selected subflow through `06 Selected Flow API Runner` or the web backend's second API call. Data-analysis questions use `data_analysis_flow/`.

Use Langflow's Gemini/LLM nodes for the actual reasoning calls:

1. `router_flow/00~05` classify the request and produce one `selected_flow`; use `03A Route Prompt Context Builder` plus a built-in Prompt Template where the route/API catalog can be edited directly.
2. `router_flow/04 Route Classifier Normalizer -> 05 Orchestrator Response Builder -> 06 Selected Flow API Runner -> Chat Output`.
3. For metadata questions, call `metadata_qa_flow/`.
4. For analysis questions, call `data_analysis_flow/02 Intent Prompt Builder -> Gemini/LLM -> 03 Intent Plan Normalizer`.
5. `data_analysis_flow/07~12` retriever/merger nodes -> `13 Retrieval Payload Adapter`.
6. `14 Pandas Prompt Builder -> Gemini/LLM -> 15 Pandas Code Executor`.
7. Optional pandas repair branch: `16A Pandas Repair Payload Builder -> 16B Pandas Repair Prompt Builder -> Gemini/LLM -> second 15 Pandas Code Executor`.
8. Final pandas payload -> `17 MongoDB Data Store -> 18 Answer Prompt Builder -> Gemini/LLM -> 19 Answer Response Builder`.
9. `19 Answer Response Builder.payload_out -> 20 Answer Message Adapter.message -> Chat Output`.

The final adapter formats one playground-friendly Markdown message from the existing final payload.
It includes the answer, result table, intent summary, retrieval/step plan summary, pandas execution
status, and generated pandas code without adding another payload branch.

## Metadata Authoring Flow Pattern

The three metadata authoring flows use the same shape:

1. request loader with existing MongoDB metadata summary
2. text refinement prompt -> Gemini/LLM -> refinement normalizer
3. authoring prompt -> Gemini/LLM -> authoring result normalizer
4. similarity checker for same or confusingly similar existing metadata
5. review prompt -> Gemini/LLM -> review writer
6. response builder for Playground/API output

The review writer saves only when the review says the item is ready and no duplicate choice is pending.


