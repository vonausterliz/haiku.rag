"""Lettura e scrittura di haiku.rag.yaml: ogni salvataggio viene validato e la versione precedente archiviata."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from haiku.rag.config.models import AppConfig

CONFIG_PATH = Path(os.environ.get("HAIKU_RAG_CONFIG_PATH", "haiku.rag.yaml"))
BACKUP_DIR = CONFIG_PATH.parent / "backups"
HOST_INFO_PATH = CONFIG_PATH.parent / "host.json"


def load_raw() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text()) or {}


def load_config() -> AppConfig:
    return AppConfig.model_validate(load_raw())


def load_host_info() -> dict | None:
    """Hardware dell'host scritto da scripts/host-probe.sh (il container non lo vede)."""
    if not HOST_INFO_PATH.exists():
        return None
    return json.loads(HOST_INFO_PATH.read_text())


def _set(tree: dict, dotted_key: str, value: Any) -> None:
    *parents, leaf = dotted_key.split(".")
    for key in parents:
        tree = tree.setdefault(key, {})
    if value is None:
        tree.pop(leaf, None)
    else:
        tree[leaf] = value


def update(changes: dict[str, Any]) -> AppConfig:
    """Applica modifiche in notazione puntata (es. "qa.model.name"), valida e salva.

    Solleva pydantic.ValidationError senza toccare il file se il risultato non è valido.
    """
    raw = load_raw()
    for key, value in changes.items():
        _set(raw, key, value)
    config = AppConfig.model_validate(raw)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CONFIG_PATH, BACKUP_DIR / f"haiku.rag.{stamp}.yaml")
    CONFIG_PATH.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, width=100))
    return config
