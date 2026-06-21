from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError as exc:  # pragma: no cover - only used when local dependency is missing.
    raise SystemExit("requests package is required. Install it with: pip install requests") from exc


DEFAULT_INPUT_VALUE = "테스트 호출입니다. 가능한 간단히 응답해줘."


def main() -> int:
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).resolve().parent / ".env")
    args = parse_args()

    api_url = args.api_url or os.getenv("LANGFLOW_TEST_API_URL") or os.getenv("LANGFLOW_API_URL") or ""
    langflow_key = args.langflow_key or os.getenv("LANGFLOW_API_KEY") or os.getenv("LANGFLOW_KEY") or ""
    input_value = args.input_value or os.getenv("LANGFLOW_TEST_INPUT_VALUE") or DEFAULT_INPUT_VALUE

    if not api_url:
        print("ERROR: --api-url 또는 LANGFLOW_TEST_API_URL 값을 입력하세요.", file=sys.stderr)
        return 2

    request_payload = {
        "input_value": input_value,
        "input_type": args.input_type,
        "output_type": args.output_type,
    }
    if args.session_id:
        request_payload["session_id"] = args.session_id

    headers = {"Content-Type": "application/json"}
    if langflow_key:
        headers["x-api-key"] = langflow_key

    print(f"POST {api_url}")
    print("Request payload:")
    print(json.dumps(request_payload, ensure_ascii=False, indent=2))

    started_at = time.perf_counter()
    try:
        response = requests.post(api_url, headers=headers, json=request_payload, timeout=args.timeout)
    except Exception as exc:
        print(f"ERROR: request failed: {exc}", file=sys.stderr)
        return 1

    elapsed_seconds = round(time.perf_counter() - started_at, 3)
    print(f"\nStatus: {response.status_code} ({elapsed_seconds}s)")

    try:
        body: Any = response.json()
    except Exception:
        body = {"text": response.text}

    message = extract_message_text(body)
    if message:
        print("\nExtracted message:")
        print(message)

    print("\nRaw response:")
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0 if response.ok else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Langflow Run API 호출 테스트")
    parser.add_argument("--api-url", default="", help="예: http://127.0.0.1:7860/api/v1/run/<flow-id>")
    parser.add_argument("--langflow-key", default="", help="Langflow API key. 입력 시 x-api-key 헤더로 전달합니다.")
    parser.add_argument("--input-value", "--input", default="", help="Flow에 전달할 input_value")
    parser.add_argument("--input-type", default="chat", help="기본값: chat")
    parser.add_argument("--output-type", default="chat", help="기본값: chat")
    parser.add_argument("--session-id", default="", help="필요 시 session_id 전달")
    parser.add_argument("--timeout", type=int, default=180, help="HTTP timeout seconds")
    return parser.parse_args()


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def extract_message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value or "")

    candidates = [value.get("message"), value.get("answer_message"), value.get("result"), value.get("text")]
    api_response = value.get("api_response")
    if isinstance(api_response, dict):
        candidates.extend([api_response.get("answer_message"), api_response.get("message"), api_response.get("result")])

    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text

    outputs = value.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            text = extract_message_text(output)
            if text:
                return text

    results = value.get("results")
    if isinstance(results, dict):
        for result_value in results.values():
            text = extract_message_text(result_value)
            if text:
                return text

    data = value.get("data")
    if isinstance(data, dict):
        return extract_message_text(data)
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
