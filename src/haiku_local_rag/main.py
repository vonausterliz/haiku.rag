"""Entry point FastAPI. Per ora espone solo l'health check: chat, corpus e admin arriveranno qui."""

import os
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI
from haiku.rag.config.models import AppConfig

CONFIG_PATH = Path(os.environ.get("HAIKU_RAG_CONFIG_PATH", "haiku.rag.yaml"))

app = FastAPI(title="haiku-local-rag")


def load_config() -> AppConfig:
    return AppConfig.model_validate(yaml.safe_load(CONFIG_PATH.read_text()))


@app.get("/health")
async def health() -> dict:
    config = load_config()
    ollama_url = config.providers.ollama.base_url
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            tags = (await client.get(f"{ollama_url}/api/tags")).json()
        ollama = {"reachable": True, "models": [m["name"] for m in tags.get("models", [])]}
    except httpx.HTTPError as exc:
        ollama = {"reachable": False, "error": str(exc)}
    return {
        "config_path": str(CONFIG_PATH),
        "corpora": dict(config.lancedb.databases),
        "llm": config.qa.model.name,
        "embeddings": config.embeddings.model.name,
        "ollama_url": ollama_url,
        "ollama": ollama,
    }
