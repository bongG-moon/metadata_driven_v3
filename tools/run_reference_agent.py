from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from reference_runtime import run_agent


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Run the reference metadata-driven agent.")
    parser.add_argument("--question", required=True, help="User question to run.")
    parser.add_argument("--session-id", default="demo-session", help="Session id for state memory.")
    parser.add_argument("--state-file", help="Optional previous state JSON file.")
    parser.add_argument("--json", action="store_true", help="Print the full payload as JSON.")
    args = parser.parse_args()

    state = {}
    if args.state_file:
        with Path(args.state_file).open("r", encoding="utf-8") as file:
            state = json.load(file)

    payload = run_agent(args.question, state=state, session_id=args.session_id, root=str(PROJECT_ROOT))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(payload["answer_message"])
    print()
    print("columns:", ", ".join(payload["data"]["columns"]))
    for row in payload["data"]["rows"]:
        print(json.dumps(row, ensure_ascii=False))
    print()
    print("applied_scope:")
    print(json.dumps(payload["applied_scope"], ensure_ascii=False, indent=2))
    return 0


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    raise SystemExit(main())
