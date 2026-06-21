# Service Readiness Audit

Date: 2026-06-20
Target: `C:\Users\qkekt\Desktop\metadata_driven_v3`

This audit maps the requested end state to current evidence. It is intentionally separate from the implementation notes so a reviewer can check whether the v3 flow is service-ready without rereading the entire repo.

## Requirement Matrix

| Requirement | Current status | Evidence |
| --- | --- | --- |
| Inspect existing `pkg_agent_langflow` and `metadata_driven_v2` flows before designing v3 | Proven | `docs/FLOW_AUDIT_AND_V3_DESIGN.md` documents both audits and the design decision. |
| Build the implementation in a new Desktop folder named `metadata_driven_v3` | Proven | Current target folder exists and contains README, docs, metadata, reference runtime, tests, tools, web app, and Langflow components. |
| Keep the Langflow canvas readable instead of one large flow | Proven | `langflow_components/` is split into router, metadata QA, data analysis, report, diagnosis, session state, and three authoring flows. `docs/LANGFLOW_NODE_CONNECTION_GUIDE.md` indexes the runtime flows. |
| Avoid an always-on MongoDB loader in the analysis path | Proven | `langflow_components/data_analysis_flow/CONNECTION_GUIDE.md` routes `04 Previous Result Restore Router.payload_out` directly to `06 Previous Result Restore Merger.main_payload`; `05 MongoDB Data Loader` is only on the `restore_payload` branch when `previous_result_restore.required=true`. Covered by `tests/test_split_flow_contracts.py`. |
| Pass compact payloads between components and avoid repeated full rows | Proven | `17_mongodb_data_store.py`, `21_api_response_builder.py`, and session-state components keep preview rows plus `data_ref` pointers. Covered by `tests/test_mongodb_result_store_flow.py`, `tests/test_main_flow_api_response_builder.py`, and `tests/test_session_state_flow.py`. |
| Plan required data and sequential analysis from metadata | Proven locally | `metadata/domain_items.json` contains `analysis_recipes`; `reference_runtime/planner.py` reads recipe cues, dataset families, aliases, defaults, and step templates; `03_intent_plan_normalizer.py` does the same for Langflow payloads. Regression includes recipe cases. |
| Generate pandas code through an LLM and execute it | Proven on limited live set | `14_pandas_prompt_builder.py` creates the pandas prompt and `15_pandas_code_executor.py` executes LLM JSON code with guardrails. `python tools\validate_component_llm_flow.py --case multi_step_rank_wip_with_production --case top_wip_process_hold_lot_in_tat` passed `2/2`; report is `validation_runs/20260620_141405_component_llm/REPORT.md`. `python tools\validate_llm_in_loop.py --limit 2` also passed `2/2`; report is `validation_runs/20260620_142650_llm/REPORT.md`. |
| Repair pandas failures by passing previous code and error context to a rewrite route | Proven locally | `16a_pandas_repair_payload_builder.py` keeps the repair decision in Data payload, and `16b_pandas_repair_prompt_builder.py` exposes a single Agent-compatible `repair_prompt`; second `15 Pandas Code Executor` is the recommended retry path. Covered by `tests/test_langflow_llm_node_flow.py::test_pandas_repair_builder_builds_payload_and_prompt_on_failure` and related repair tests. |
| Let users enter metadata in natural language, not JSON | Proven locally | `domain_authoring_flow`, `table_catalog_authoring_flow`, and `main_flow_filters_authoring_flow` each have numbered standalone components, connection guides, and raw text examples. Covered by `tests/test_metadata_authoring_flows.py` and `tests/test_metadata_text_input_examples.py`. |
| Keep Langflow custom components standalone because local helper imports are not available | Proven | `tests/test_component_contracts.py::test_numbered_components_are_standalone_imports`; direct search found no sibling helper imports or local file read/write in `langflow_components/*.py`. |
| Validate the prior question set end to end through intent, retrieval scope, analysis kind, data columns, and result rows | Proven locally | `python tools\validate_regression.py` passed `23/23`; latest report is `validation_runs/20260620_142530/REPORT.md`. |
| Verify code health | Proven locally | `python -m pytest tests -q -p no:cacheprovider` passed `166`; AST parse over 119 Python files passed. |
| Verify metadata upload shape | Proven locally | `python tools\upload_json_to_mongodb.py --dry-run` reports `agent_v3_domain_items: 38`, `agent_v3_table_catalog_items: 9`, `agent_v3_main_flow_filters: 18`. |

## One-Command Readiness Gate

Run this before handoff:

```powershell
python tools\\validate_service_readiness.py
```

Use `--skip-live-llm` when you need a no-cost local/structure readiness report, and use `--require-live-llm` when `.env` contains Gemini credentials and live LLM pandas-code generation must be a hard production gate.

## Remaining External Gates

The implementation now has a populated `.env`, and the Gemini connection plus two representative component-level LLM cases have passed. The following command is the low-cost live proof used for this audit:

```powershell
python tools\validate_component_llm_flow.py --case multi_step_rank_wip_with_production --case top_wip_process_hold_lot_in_tat
# 2/2 component LLM cases passed
```

Before claiming full live-service completion for every regression prompt and every live source system, run these in the target environment:

```powershell
python tools\validate_env.py
python tools\validate_gemini_connection.py
python tools\validate_component_llm_flow.py
python tools\validate_llm_in_loop.py --limit 1
python tools\validate_llm_in_loop.py
```

If source systems are enabled, also set `RUN_LIVE_SOURCE_RETRIEVAL=true` and validate Oracle/H-API/Datalake/Goodocs credentials in the target environment.

## Current Decision

Local implementation, deterministic validation, Gemini connection validation, two representative live component LLM cases, and two representative LLM-in-the-loop cases are complete. Latest readiness report: `validation_runs/20260620_142530_service_readiness/REPORT.md`. Full live-service validation across all regression prompts and live source systems remains a production-environment gate.







