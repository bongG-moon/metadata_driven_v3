from __future__ import annotations

import json
import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    load_env_file(PROJECT_ROOT / ".env")
    api_key = first_value("LLM_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
    model_name = os.getenv("LLM_MODEL_NAME", "").strip()
    temperature = float(os.getenv("LLM_TEMPERATURE", "0") or 0)

    if not api_key or not model_name:
        print("Missing Gemini settings. Fill LLM_API_KEY and LLM_MODEL_NAME in .env.")
        return 2

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        print("Missing dependency: install langchain-google-genai.")
        return 2

    llm = ChatGoogleGenerativeAI(
        api_key=api_key,
        model=model_name,
        temperature=temperature,
        convert_system_message_to_human=True,
    )
    prompt = (
        "Return one strict JSON object only. "
        "Use this exact schema: {\"status\":\"ok\",\"provider\":\"gemini\"}."
    )
    response = llm.invoke(prompt)
    text = str(getattr(response, "content", response))
    parsed = extract_json_object(text)
    print(json.dumps({"model": model_name, "parsed": parsed, "raw_text": text[:500]}, ensure_ascii=False, indent=2))
    return 0 if parsed.get("status") == "ok" else 1


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def first_value(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def extract_json_object(text: str) -> dict:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
