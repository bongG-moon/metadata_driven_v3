from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import types
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLE_PATH = PROJECT_ROOT / "langflow_components" / "domain_authoring_flow" / "raw_text_input_example.md"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "validation_runs" / "domain_authoring_from_text"


def main() -> int:
    install_lfx_stubs()
    load_env_file(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Run the domain authoring component flow over raw_text_input_example.md single blocks and save to MongoDB."
    )
    parser.add_argument("--examples", default=str(DEFAULT_EXAMPLE_PATH), help="Markdown file containing <!-- single_*:start --> blocks.")
    parser.add_argument("--marker", action="append", default=[], help="Specific marker to run. Can be repeated.")
    parser.add_argument("--duplicate-action", default="replace", choices=["ask", "merge", "replace", "skip", "create_new"])
    parser.add_argument("--prompt-language", default="ko", choices=["ko", "en"])
    parser.add_argument("--model", default=os.getenv("LLM_MODEL_NAME", "").strip())
    parser.add_argument("--temperature", type=float, default=float(os.getenv("LLM_TEMPERATURE", "0") or 0))
    parser.add_argument("--mongo-uri", default=os.getenv("MONGODB_URI", ""))
    parser.add_argument("--database", default=os.getenv("MONGODB_DATABASE", "metadata_driven_agent_v3"))
    parser.add_argument("--domain-collection", default=os.getenv("MONGODB_DOMAIN_COLLECTION", "agent_v3_domain_items"))
    parser.add_argument("--table-catalog-collection", default=os.getenv("MONGODB_TABLE_CATALOG_COLLECTION", "agent_v3_table_catalog_items"))
    parser.add_argument("--main-flow-filter-collection", default=os.getenv("MONGODB_MAIN_FLOW_FILTER_COLLECTION", "agent_v3_main_flow_filters"))
    parser.add_argument("--load-limit", default="1000")
    parser.add_argument("--clear-existing", action="store_true", help="Delete all documents in the target domain collection before saving.")
    parser.add_argument("--yes", action="store_true", help="Required with --clear-existing.")
    parser.add_argument("--dry-run", action="store_true", help="Run conversion but do not write or clear MongoDB.")
    parser.add_argument(
        "--empty-domain-context",
        action="store_true",
        help="Ignore currently stored domain items while still loading table catalog and main filter context.",
    )
    parser.add_argument("--auto-review", action="store_true", help="Use a deterministic ready_to_save review instead of calling the review LLM.")
    parser.add_argument(
        "--raw-as-refined",
        action="store_true",
        help="Feed the original block text through the refinement normalizer as refined_text instead of calling the refinement LLM.",
    )
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument(
        "--export-json",
        default="",
        help="After a successful MongoDB write, export the full domain collection to this JSON file.",
    )
    args = parser.parse_args()

    if args.clear_existing and not args.yes:
        print("--clear-existing requires --yes.", file=sys.stderr)
        return 2
    if not args.dry_run and not args.mongo_uri:
        print("Missing MongoDB URI. Set MONGODB_URI or pass --mongo-uri.", file=sys.stderr)
        return 2

    components = load_domain_components()
    blocks = read_single_blocks(Path(args.examples))
    if args.marker:
        wanted = set(args.marker)
        blocks = [block for block in blocks if block["marker"] in wanted]
    if not blocks:
        print("No input blocks selected.", file=sys.stderr)
        return 2

    llm = build_gemini_llm(args.model, args.temperature)
    templates = load_prompt_templates(args.prompt_language)

    report_root = Path(args.report_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    report_root.mkdir(parents=True, exist_ok=True)

    if args.clear_existing and not args.dry_run:
        deleted_count = clear_domain_collection(args.mongo_uri, args.database, args.domain_collection)
        print(f"cleared {deleted_count} existing domain documents from {args.database}.{args.domain_collection}")
    else:
        deleted_count = 0

    results: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        print(f"[{index}/{len(blocks)}] {block['marker']}")
        try:
            result = run_one_block(block, components, templates, llm, args)
        except Exception as exc:
            result = {
                "marker": block["marker"],
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "saved_count": 0,
            }
        results.append(result)
        (report_root / f"{index:02d}_{safe_filename(block['marker'])}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  status={result.get('status')} saved={result.get('saved_count', 0)}")
        if result.get("status") == "error":
            print(f"  error={result.get('error') or result.get('message')}")

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "database": args.database,
        "domain_collection": args.domain_collection,
        "cleared_count": deleted_count,
        "total_blocks": len(blocks),
        "ok_blocks": sum(1 for item in results if item.get("status") == "ok"),
        "saved_count": sum(int(item.get("saved_count") or 0) for item in results),
        "results": results,
    }
    if args.export_json and not args.dry_run and all(item.get("status") == "ok" for item in results):
        exported = export_domain_collection_to_json(
            args.mongo_uri,
            args.database,
            args.domain_collection,
            Path(args.export_json),
        )
        summary["export_json"] = str(Path(args.export_json))
        summary["exported_documents"] = exported
    (report_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (report_root / "REPORT.md").write_text(build_report(summary), encoding="utf-8")
    print(f"report: {report_root / 'REPORT.md'}")
    return 0 if all(item.get("status") == "ok" for item in results) else 1


def run_one_block(block: dict[str, str], components: dict[str, Any], templates: dict[str, str], llm: Any, args: argparse.Namespace) -> dict[str, Any]:
    request = components["request"].build_domain_authoring_request(
        block["text"],
        mongo_uri=args.mongo_uri,
        mongo_database=args.database,
        collection_name=args.domain_collection,
        table_catalog_collection_name=args.table_catalog_collection,
        main_flow_filter_collection_name=args.main_flow_filter_collection,
        duplicate_action=args.duplicate_action,
        load_existing="true",
        load_limit=args.load_limit,
    )
    if args.empty_domain_context or args.clear_existing:
        request["existing_items"] = []
        request.setdefault("load_summary", {})["domain_items"] = 0

    if args.raw_as_refined:
        refinement_text = json.dumps({"refined_text": block["text"], "needs_more_input": False, "missing_information": []}, ensure_ascii=False)
    else:
        refinement_prompt = templates["refinement"].format(raw_text=block["text"])
        refinement_text = call_llm_text(llm, refinement_prompt)
    refined = components["refine"].normalize_domain_refinement(request, refinement_text)

    authoring_context = components["authoring_vars"].build_domain_authoring_prompt_variables(refined)["authoring_context"]
    authoring_prompt = templates["authoring"].format(authoring_context=authoring_context)
    authoring_text = call_llm_text(llm, authoring_prompt)
    normalized = components["normalizer"].normalize_domain_authoring_result(refined, authoring_text)

    checked = components["similarity"].check_domain_similarity(normalized, args.duplicate_action)

    if args.auto_review:
        review_text = json.dumps({"ready_to_save": True, "summary": "로컬 실행에서 자동 승인했습니다.", "supplement_requests": [], "item_reviews": []}, ensure_ascii=False)
    else:
        review_input_json = components["review_vars"].build_domain_review_prompt_variables(checked)["review_input_json"]
        review_prompt = templates["review"].format(review_input_json=review_input_json)
        review_text = call_llm_text(llm, review_prompt)

    if args.dry_run:
        written = dict(checked)
        written["review"] = {"ready_to_save": True, "summary": "dry-run: MongoDB 저장은 수행하지 않았습니다.", "supplement_requests": []}
        written["write_result"] = {"status": "ok", "saved_count": len(checked.get("items", [])), "saved_items": [], "errors": [], "skipped_reason": "dry-run"}
    else:
        written = components["writer"].review_and_write_domain_payload(
            checked,
            review_text,
            mongo_uri=args.mongo_uri,
            mongo_database=args.database,
            collection_name=args.domain_collection,
        )
    response = components["response"].build_domain_authoring_response(written)
    write_result = written.get("write_result") if isinstance(written.get("write_result"), dict) else {}
    return {
        "marker": block["marker"],
        "status": write_result.get("status", response.get("status")),
        "saved_count": write_result.get("saved_count", 0),
        "saved_items": write_result.get("saved_items", []),
        "message": response.get("message"),
        "items": written.get("items", []),
        "review": written.get("review", {}),
        "write_result": write_result,
        "refinement_text": refinement_text,
        "authoring_text": authoring_text,
        "review_text": review_text,
    }


def read_single_blocks(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    pattern = r"<!--\s*(single_[a-zA-Z0-9_]+):start\s*-->(.*?)<!--\s*\1:end\s*-->"
    blocks = []
    for match in re.finditer(pattern, text, re.DOTALL):
        marker = match.group(1)
        content = match.group(2).strip()
        fenced = re.fullmatch(r"```(?:text)?\s*\n(.*?)\n```", content, re.DOTALL)
        blocks.append({"marker": marker, "text": (fenced.group(1) if fenced else content).strip()})
    return blocks


def load_domain_components() -> dict[str, Any]:
    return {
        "request": load_component("langflow_components/domain_authoring_flow/00_domain_authoring_request_loader.py"),
        "refine": load_component("langflow_components/domain_authoring_flow/02_domain_text_refinement_normalizer.py"),
        "authoring_vars": load_component("langflow_components/domain_authoring_flow/03_domain_authoring_variables_builder.py"),
        "normalizer": load_component("langflow_components/domain_authoring_flow/04_domain_authoring_result_normalizer.py"),
        "similarity": load_component("langflow_components/domain_authoring_flow/05_domain_similarity_checker.py"),
        "review_vars": load_component("langflow_components/domain_authoring_flow/06_domain_review_variables_builder.py"),
        "writer": load_component("langflow_components/domain_authoring_flow/07_domain_review_writer.py"),
        "response": load_component("langflow_components/domain_authoring_flow/08_domain_authoring_response_builder.py"),
    }


def load_component(relative_path: str) -> Any:
    path = PROJECT_ROOT / relative_path
    module_name = "domain_authoring_local_" + path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load component: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_prompt_templates(language: str) -> dict[str, str]:
    suffix = "_ko" if language == "ko" else ""
    base = PROJECT_ROOT / "langflow_components" / "domain_authoring_flow"
    return {
        "refinement": (base / f"01_domain_text_refinement_prompt_template{suffix}.md").read_text(encoding="utf-8"),
        "authoring": (base / f"03_domain_authoring_prompt_template{suffix}.md").read_text(encoding="utf-8"),
        "review": (base / f"06_domain_review_prompt_template{suffix}.md").read_text(encoding="utf-8"),
    }


def build_gemini_llm(model_name: str, temperature: float) -> Any:
    api_key = first_env_value("LLM_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
    if not api_key or not model_name:
        raise SystemExit("Missing Gemini settings. Fill LLM_API_KEY/GOOGLE_API_KEY/GEMINI_API_KEY and LLM_MODEL_NAME in .env.")
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise SystemExit("Missing dependency: langchain-google-genai") from exc
    return ChatGoogleGenerativeAI(
        api_key=api_key,
        model=model_name,
        temperature=temperature,
        convert_system_message_to_human=True,
    )


def call_llm_text(llm: Any, prompt: str) -> str:
    response = llm.invoke(prompt)
    return str(getattr(response, "content", response))


def clear_domain_collection(mongo_uri: str, database: str, collection: str) -> int:
    from pymongo import MongoClient

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        result = client[database][collection].delete_many({})
        return int(result.deleted_count)
    finally:
        client.close()


def export_domain_collection_to_json(mongo_uri: str, database: str, collection: str, output_path: Path) -> int:
    from pymongo import MongoClient

    grouped: dict[str, Any] = {
        "process_groups": {},
        "product_terms": {},
        "quantity_terms": {},
        "metric_terms": {},
        "analysis_recipes": {},
        "status_terms": {},
        "product_key_columns": [],
    }
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        docs = list(client[database][collection].find({}).sort([("section", 1), ("key", 1)]))
    finally:
        client.close()

    for doc in docs:
        section = str(doc.get("section") or "").strip()
        key = str(doc.get("key") or "").strip()
        payload = doc.get("payload") if isinstance(doc.get("payload"), dict) else {}
        if section == "product_key_columns":
            columns = doc.get("columns") or payload.get("columns") or payload.get("product_key_columns") or []
            grouped["product_key_columns"] = [str(item) for item in columns if str(item or "").strip()]
            continue
        if section in grouped and isinstance(grouped[section], dict) and key:
            grouped[section][key] = json_ready(payload)

    output_path = output_path if output_path.is_absolute() else PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(docs)


def json_ready(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def first_env_value(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def build_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Domain Authoring From Raw Text Report",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Dry run: {summary['dry_run']}",
        f"- Database: {summary['database']}",
        f"- Domain collection: {summary['domain_collection']}",
        f"- Cleared documents: {summary['cleared_count']}",
        f"- Total blocks: {summary['total_blocks']}",
        f"- OK blocks: {summary['ok_blocks']}",
        f"- Saved items: {summary['saved_count']}",
        "",
        "| Marker | Status | Saved | Items |",
        "|---|---:|---:|---|",
    ]
    for result in summary["results"]:
        items = ", ".join(f"{item.get('section')}/{item.get('key')}" for item in result.get("items", [])[:8])
        lines.append(f"| `{result.get('marker')}` | {result.get('status')} | {result.get('saved_count', 0)} | {items} |")
    return "\n".join(lines)


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "block"


def install_lfx_stubs() -> None:
    def ensure_module(name: str) -> types.ModuleType:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
        return sys.modules[name]

    ensure_module("lfx")
    ensure_module("lfx.custom")
    ensure_module("lfx.custom.custom_component")
    component_mod = ensure_module("lfx.custom.custom_component.component")
    io_mod = ensure_module("lfx.io")
    ensure_module("lfx.schema")
    data_mod = ensure_module("lfx.schema.data")
    message_mod = ensure_module("lfx.schema.message")

    class Component:
        pass

    class Input:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.name = kwargs.get("name") or (args[0] if args else None)
            for key, value in kwargs.items():
                setattr(self, key, value)

    class Data:
        def __init__(self, data: Any = None, **kwargs: Any) -> None:
            self.data = data if data is not None else kwargs

    class Message:
        def __init__(self, text: str = "", **kwargs: Any) -> None:
            self.text = text
            for key, value in kwargs.items():
                setattr(self, key, value)

    component_mod.Component = Component
    for name in ("DataInput", "MessageTextInput", "Output", "DropdownInput", "BoolInput", "IntInput"):
        setattr(io_mod, name, Input)
    data_mod.Data = Data
    message_mod.Message = Message


if __name__ == "__main__":
    raise SystemExit(main())
