"""App FastAPI: pagina Chat (/), pagina Admin (/admin) e relative API."""

from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from haiku.rag.client import HaikuRAG
from pydantic import BaseModel, ValidationError

from haiku_local_rag import settings
from haiku_local_rag.ollama import OllamaClient

HERE = Path(__file__).parent

app = FastAPI(title="haiku-local-rag")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

# Chiavi di haiku.rag.yaml modificabili dalla pagina Admin, con il loro tipo
EDITABLE_KEYS: dict[str, type] = {
    "providers.ollama.base_url": str,
    "qa.model.name": str,
    "qa.model.temperature": float,
    "qa.model.max_tokens": int,
    "qa.model.thinking": bool,
    "embeddings.model.name": str,
    "embeddings.model.vector_dim": int,
    "embeddings.batch_size": int,
    "reranking.model": dict,
    "processing.chunk_size": int,
    "processing.chunker_type": str,
    "processing.chunking_use_markdown_tables": bool,
    "processing.pictures": str,
    "processing.conversion_options.do_ocr": bool,
    "processing.conversion_options.force_ocr": bool,
    "processing.conversion_options.ocr_engine": str,
    "processing.conversion_options.ocr_lang": list,
    "processing.conversion_options.table_mode": str,
    "processing.conversion_options.picture_description.model.name": str,
    "processing.conversion_options.picture_description.max_tokens": int,
    "processing.conversion_options.picture_description.timeout": int,
    "prompts.picture_description": str,
}


def ollama() -> OllamaClient:
    return OllamaClient(settings.load_config().providers.ollama.base_url)


# ---------- pagine ----------


@app.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    config = settings.load_config()
    return templates.TemplateResponse(
        request,
        "chat.html",
        {"corpora": list(config.lancedb.databases), "llm": config.qa.model.name},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "config": settings.load_config(),
            "config_path": settings.CONFIG_PATH,
            "host": settings.load_host_info(),
        },
    )


# ---------- API ----------


@app.get("/health")
async def health() -> dict:
    config = settings.load_config()
    client = ollama()
    try:
        models = [m["name"] for m in await client.models()]
        ollama_status = {"reachable": True, "models": models}
    except httpx.HTTPError as exc:
        ollama_status = {"reachable": False, "error": str(exc)}
    return {
        "config_path": str(settings.CONFIG_PATH),
        "corpora": dict(config.lancedb.databases),
        "llm": config.qa.model.name,
        "embeddings": config.embeddings.model.name,
        "ollama_url": config.providers.ollama.base_url,
        "ollama": ollama_status,
    }


@app.get("/api/status")
async def status() -> dict:
    """Stato per la pagina Admin: Ollama, modelli caricati, hardware host."""
    client = ollama()
    try:
        version, loaded = await client.version(), await client.loaded()
        ollama_status = {"reachable": True, "version": version, "loaded": loaded}
    except httpx.HTTPError as exc:
        ollama_status = {"reachable": False, "error": str(exc)}
    return {"ollama": ollama_status, "host": settings.load_host_info()}


@app.get("/api/models")
async def models() -> list[dict]:
    try:
        return await ollama().models()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Ollama non raggiungibile: {exc}") from exc


@app.get("/api/config")
async def get_config() -> dict:
    return settings.load_config().model_dump(mode="json")


@app.put("/api/config")
async def put_config(changes: dict[str, Any]) -> dict:
    unknown = set(changes) - set(EDITABLE_KEYS)
    if unknown:
        raise HTTPException(400, f"Chiavi non modificabili: {', '.join(sorted(unknown))}")

    previous = settings.load_config()
    try:
        config = settings.update(changes)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc

    embedder_changed = (
        config.embeddings.model.name != previous.embeddings.model.name
        or config.embeddings.model.vector_dim != previous.embeddings.model.vector_dim
    )
    return {"saved": True, "reindex_required": embedder_changed}


class AskRequest(BaseModel):
    question: str
    corpora: list[str] | None = None


@app.post("/api/ask")
async def ask(body: AskRequest) -> dict:
    if not body.question.strip():
        raise HTTPException(400, "Domanda vuota")
    config = settings.load_config()
    async with HaikuRAG(config=config, read_only=True) as rag:
        answer, citations = await rag.ask(body.question, sources=body.corpora or None)
    return {
        "answer": answer,
        "citations": [
            {
                "index": c.index,
                "corpus": c.source,
                "title": c.document_title or c.document_uri,
                "pages": c.page_numbers,
                "headings": c.headings or [],
                "content": c.content,
            }
            for c in citations
        ],
    }
