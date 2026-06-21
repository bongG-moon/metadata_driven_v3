from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class GateResult:
    name: str
    status: str
    command: str
    summary: str
    output: str = ""
    returncode: int | None = None

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    @property
    def failed(self) -> bool:
        return self.status == "fail"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run service-readiness gates for metadata_driven_v3.")
    parser.add_argument("--skip-pytest", action="store_true", help="Skip the full pytest gate for a faster preflight.")
    parser.add_argument("--skip-live-llm", action="store_true", help="Skip live Gemini component validation even when credentials exist.")
    parser.add_argument("--require-live-llm", action="store_true", help="Fail when live Gemini component validation cannot run or fails.")
    parser.add_argument("--live-limit", type=int, default=1, help="Number of component LLM regression cases to run when LLM settings exist.")
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    load_env_file(PROJECT_ROOT / ".env", env)

    results: list[GateResult] = []
    results.append(run_ast_gate())
    if not args.skip_pytest:
        results.append(run_command_gate("pytest", [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], env))
    else:
        results.append(GateResult("pytest", "skip", "python -m pytest tests -q -p no:cacheprovider", "Skipped by --skip-pytest."))
    results.append(run_command_gate("regression", [sys.executable, "tools/validate_regression.py"], env))
    results.append(run_command_gate("mongodb_metadata_dry_run", [sys.executable, "tools/upload_json_to_mongodb.py", "--dry-run"], env))
    results.append(run_env_gate(env))
    if args.skip_live_llm:
        results.append(
            GateResult(
                "component_llm_live",
                "skip",
                f"python tools/validate_component_llm_flow.py --limit {args.live_limit}",
                "Skipped by --skip-live-llm.",
            )
        )
    else:
        results.append(run_live_llm_gate(env, args.live_limit, args.require_live_llm))

    run_dir = PROJECT_ROOT / "validation_runs" / datetime.now().strftime("%Y%m%d_%H%M%S_service_readiness")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "results.json").write_text(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "REPORT.md").write_text(build_report(results, args.require_live_llm), encoding="utf-8")

    print(build_console_summary(results))
    print(f"report: {run_dir / 'REPORT.md'}")

    required_failures = [item for item in results if item.failed and item.name not in {"environment", "component_llm_live"}]
    if args.require_live_llm:
        required_failures.extend(item for item in results if item.name == "component_llm_live" and not item.passed)
    return 1 if required_failures else 0


def load_env_file(path: Path, env: dict[str, str]) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def run_ast_gate() -> GateResult:
    try:
        count = 0
        for path in PROJECT_ROOT.rglob("*.py"):
            if any(part in {".git", ".pytest_cache", "__pycache__", "validation_runs"} for part in path.parts):
                continue
            ast.parse(path.read_text(encoding="utf-8"))
            count += 1
        return GateResult("ast_parse", "pass", "internal ast.parse over *.py", f"AST_OK {count} files")
    except Exception as exc:
        return GateResult("ast_parse", "fail", "internal ast.parse over *.py", f"{type(exc).__name__}: {exc}")


def run_command_gate(name: str, command: list[str], env: dict[str, str]) -> GateResult:
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env, capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    summary = last_non_empty_line(output) or f"exit {completed.returncode}"
    return GateResult(
        name=name,
        status="pass" if completed.returncode == 0 else "fail",
        command=command_to_text(command),
        summary=summary,
        output=trim_output(output),
        returncode=completed.returncode,
    )


def run_env_gate(env: dict[str, str]) -> GateResult:
    if not (PROJECT_ROOT / ".env").exists() and not env.get("AGENT_TIMEZONE"):
        return GateResult(
            "environment",
            "skip",
            "python tools/validate_env.py",
            ".env is missing; copy .env.example and fill runtime/LLM/MongoDB values for live service validation.",
        )
    return run_command_gate("environment", [sys.executable, "tools/validate_env.py"], env)


def run_live_llm_gate(env: dict[str, str], limit: int, require_live_llm: bool) -> GateResult:
    model = env.get("LLM_MODEL_NAME", "").strip()
    api_key = next((env.get(key, "").strip() for key in ["LLM_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"] if env.get(key, "").strip()), "")
    if not model or not api_key:
        status = "fail" if require_live_llm else "skip"
        return GateResult(
            "component_llm_live",
            status,
            f"python tools/validate_component_llm_flow.py --limit {limit}",
            "Missing Gemini settings. Fill LLM_API_KEY and LLM_MODEL_NAME in .env.",
        )
    return run_command_gate("component_llm_live", [sys.executable, "tools/validate_component_llm_flow.py", "--limit", str(limit)], env)


def build_report(results: list[GateResult], require_live_llm: bool) -> str:
    lines = ["# Service Readiness Validation Report", "", f"- Generated: {datetime.now().isoformat(timespec='seconds')}", f"- Require live LLM: {require_live_llm}", ""]
    lines.append("## Gate Summary")
    lines.append("")
    lines.append("| Gate | Status | Summary |")
    lines.append("| --- | --- | --- |")
    for item in results:
        lines.append(f"| `{item.name}` | {item.status.upper()} | {escape_table(item.summary)} |")
    lines.append("")
    lines.append("## Details")
    for item in results:
        lines.extend(["", f"### {item.name}", "", f"- Status: `{item.status}`", f"- Command: `{item.command}`", f"- Summary: {item.summary}"])
        if item.output:
            lines.extend(["", "```text", item.output, "```"])
    lines.append("")
    lines.append("## Interpretation")
    live_item = next((item for item in results if item.name == "component_llm_live"), None)
    if live_item and live_item.status == "skip" and "--skip-live-llm" in live_item.summary:
        lines.append("Live Gemini component validation was intentionally skipped for this readiness run. Use the saved component LLM report, or rerun without `--skip-live-llm`, when live pandas-code generation evidence is required.")
    elif any(item.name == "component_llm_live" and item.status == "skip" for item in results):
        lines.append("Local deterministic gates passed or failed independently of live LLM credentials. Live Gemini pandas-code generation remains pending until `.env` contains `LLM_API_KEY` and `LLM_MODEL_NAME`.")
    elif any(item.name == "component_llm_live" and item.status == "pass" for item in results):
        lines.append("At least one live Gemini component loop completed. Run without `--live-limit` for the full live question set before production cutover.")
    else:
        lines.append("Review failed gates before production cutover.")
    lines.append("")
    return "\n".join(lines)


def build_console_summary(results: list[GateResult]) -> str:
    return "\n".join(f"{item.status.upper():4} {item.name}: {item.summary}" for item in results)


def command_to_text(command: list[str]) -> str:
    return " ".join(str(part) for part in command)


def last_non_empty_line(output: str) -> str:
    for line in reversed(output.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def trim_output(output: str, limit: int = 4000) -> str:
    output = output.strip()
    if len(output) <= limit:
        return output
    return output[:2000] + "\n... output truncated ...\n" + output[-2000:]


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
