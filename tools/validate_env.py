from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    checks = []

    checks.append(_check_present("AGENT_TIMEZONE"))
    checks.append(_check_present("AGENT_DEFAULT_DATE"))

    if _is_true(os.getenv("RUN_MONGODB_VALIDATION")):
        checks.extend(
            [
                _check_present("MONGODB_URI"),
                _check_present("MONGODB_DATABASE"),
                _check_present("MONGODB_DOMAIN_COLLECTION"),
                _check_present("MONGODB_TABLE_CATALOG_COLLECTION"),
                _check_present("MONGODB_MAIN_FLOW_FILTER_COLLECTION"),
                _check_present("MONGODB_RESULT_COLLECTION"),
            ]
        )
    else:
        checks.append(("RUN_MONGODB_VALIDATION", "skip", "set true to require MongoDB variables"))

    if _is_true(os.getenv("RUN_LLM_VALIDATION")):
        provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        checks.extend(
            [
                _check_present("LLM_PROVIDER"),
                _check_expected("LLM_PROVIDER", "gemini", provider),
                _check_any_present("LLM_API_KEY", ["LLM_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"]),
                _check_present("LLM_MODEL_NAME"),
            ]
        )
    else:
        checks.append(("RUN_LLM_VALIDATION", "skip", "set true to require LLM variables"))

    if _is_true(os.getenv("RUN_LANGFLOW_API_VALIDATION")):
        checks.extend(
            [
                _check_present("LANGFLOW_BASE_URL"),
                _check_api_url_or_flow_id("LANGFLOW_ROUTER", "LANGFLOW_ROUTER_API_URL", "LANGFLOW_ROUTER_FLOW_ID"),
                _check_api_url_or_flow_id("LANGFLOW_METADATA_QA", "LANGFLOW_METADATA_QA_API_URL", "LANGFLOW_METADATA_QA_FLOW_ID"),
                _check_api_url_or_flow_id("LANGFLOW_DATA_ANALYSIS", "LANGFLOW_DATA_ANALYSIS_API_URL", "LANGFLOW_DATA_ANALYSIS_FLOW_ID"),
                _check_api_url_or_flow_id(
                    "LANGFLOW_REPORT_GENERATION",
                    "LANGFLOW_REPORT_GENERATION_API_URL",
                    "LANGFLOW_REPORT_GENERATION_FLOW_ID",
                ),
                _check_api_url_or_flow_id(
                    "LANGFLOW_OPERATIONS_DIAGNOSIS",
                    "LANGFLOW_OPERATIONS_DIAGNOSIS_API_URL",
                    "LANGFLOW_OPERATIONS_DIAGNOSIS_FLOW_ID",
                ),
            ]
        )
    else:
        checks.append(("RUN_LANGFLOW_API_VALIDATION", "skip", "set true to require Langflow flow ids or API URLs"))

    failed = [item for item in checks if item[1] == "fail"]
    for key, status, message in checks:
        print(f"{status.upper():4} {key}: {message}")
    return 1 if failed else 0


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _check_present(key: str) -> tuple[str, str, str]:
    value = os.getenv(key, "")
    if value:
        redacted = "***" if "KEY" in key or "URI" in key else value
        return key, "pass", redacted
    return key, "fail", "missing"


def _check_any_present(label: str, keys: list[str]) -> tuple[str, str, str]:
    for key in keys:
        value = os.getenv(key, "")
        if value:
            return label, "pass", f"provided by {key}"
    return label, "fail", "missing; checked " + ", ".join(keys)


def _check_api_url_or_flow_id(label: str, api_url_key: str, flow_id_key: str) -> tuple[str, str, str]:
    api_url = os.getenv(api_url_key, "").strip()
    flow_id = os.getenv(flow_id_key, "").strip()
    base_url = os.getenv("LANGFLOW_BASE_URL", "").strip()
    if api_url:
        return label, "pass", f"provided by {api_url_key}"
    if base_url and flow_id:
        return label, "pass", f"provided by LANGFLOW_BASE_URL + {flow_id_key}"
    if flow_id and not base_url:
        return label, "fail", f"{flow_id_key} is set, but LANGFLOW_BASE_URL is missing"
    return label, "fail", f"missing; set {api_url_key} or LANGFLOW_BASE_URL + {flow_id_key}"


def _check_expected(key: str, expected: str, actual: str) -> tuple[str, str, str]:
    if actual == expected:
        return key, "pass", actual
    return key, "fail", f"expected {expected}, actual {actual or 'missing'}"


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
