from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_web_app_imports_with_only_app_py_web_app_and_env(tmp_path: Path) -> None:
    shutil.copy2(ROOT / "app.py", tmp_path / "app.py")
    shutil.copytree(ROOT / "web_app", tmp_path / "web_app", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LANGFLOW_BASE_URL=http://127.0.0.1:7860",
                "LANGFLOW_ROUTER_FLOW_ID=router-id",
                "MONGODB_URI=mongodb://example",
                "MONGODB_DATABASE=metadata_driven_agent_v3",
            ]
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", "import app; from web_app.langflow_client import LangflowSettings; s=LangflowSettings.from_env(); print(s.router_api_url)"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "http://127.0.0.1:7860/api/v1/run/router-id" in result.stdout
