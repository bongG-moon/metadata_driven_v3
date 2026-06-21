from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_root(root: str | Path | None = None) -> Path:
    if root is None:
        return PROJECT_ROOT
    return Path(root).resolve()


def load_metadata(root: str | Path | None = None) -> dict[str, Any]:
    project_root = resolve_root(root)
    metadata_dir = project_root / "metadata"
    return {
        "domain_items": read_json(metadata_dir / "domain_items.json"),
        "table_catalog": read_json(metadata_dir / "table_catalog.json"),
        "main_flow_filters": read_json(metadata_dir / "main_flow_filters.json"),
    }


def get_dataset_catalog(metadata: dict[str, Any], dataset_key: str) -> dict[str, Any]:
    datasets = metadata["table_catalog"]["datasets"]
    if dataset_key not in datasets:
        raise KeyError(f"Unknown dataset_key: {dataset_key}")
    return datasets[dataset_key]


def get_product_key_columns(metadata: dict[str, Any]) -> list[str]:
    return list(metadata["domain_items"].get("product_key_columns", []))
