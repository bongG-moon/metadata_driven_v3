from __future__ import annotations

from typing import Any

from .analysis import run_analysis
from .answer import build_final_payload, build_metadata_context
from .metadata import load_metadata
from .planner import build_intent_plan
from .retrieval import execute_retrieval_jobs


def run_agent(
    question: str,
    state: dict[str, Any] | None = None,
    session_id: str = "demo-session",
    root: str | None = None,
    request_date: str | None = None,
) -> dict[str, Any]:
    metadata = load_metadata(root)
    intent_plan = build_intent_plan(question, metadata, state=state, request_date=request_date)
    metadata_context = build_metadata_context(metadata, intent_plan)
    retrieval = execute_retrieval_jobs(intent_plan.get("retrieval_jobs", []), metadata, root=root)
    analysis_result = run_analysis(intent_plan, retrieval["runtime_sources"])
    return build_final_payload(
        question=question,
        session_id=session_id,
        state=state or {},
        metadata_context=metadata_context,
        intent_plan=intent_plan,
        source_results=retrieval["source_results"],
        analysis_result=analysis_result,
    )
