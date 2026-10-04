# haiku-local-rag

RAG completamente locale basato su [haiku.rag](https://github.com/ggozad/haiku.rag) e [Ollama](https://ollama.com), pensato per un Mac Apple Silicon e portabile tramite container.

> **Stato:** infrastruttura pronta (Ollama + container RAG + Portainer). L'app espone per ora solo `GET /health`; chat, gestione corpus, pagina Admin e coda di ingestion sono in sviluppo. Dettagli e decisioni in [`HANDOFF.md`](HANDOFF.md).

## Architettura

```
┌──────────────────────────── Host (macOS) ─────────────────────────────┐
│                                                                       │
│  Ollama (nativo, GPU Metal) :11434                                    │
│   ├─ qwen3.6:35b-a3b      LLM per le risposte                         │
│   ├─ qwen3-embedding:4b   embeddings (2560 dim, multilingue)          │
│   └─ qwen3-vl:8b-instruct descrizione immagini in ingestion           │
│            ▲                                                          │
│            │ host.docker.internal                                     │
│  ┌─────────┴──────── Colima (VM Docker) ───────────┐                  │
│  │  haiku-rag  :8000   haiku.rag + Docling + UI     │◄── 127.0.0.1    │
│  │  portainer  :9443   gestione container           │                 │
│  └─────────┬────────────────────────────────────────┘                 │
│            │ bind mount /data                                         │
│  ~/haiku-rag-data/   config · corpora LanceDB · cache modelli         │
└───────────────────────────────────────────────────────────────────────┘
```

- **Ollama gira sull'host**, non nel container: su macOS Docker non accede alla GPU Metal.
- **Il container non contiene dati**: tutto vive nella cartella dell'host montata in `/data`.
- Pipeline documenti prevista: documento → Docling → **Markdown** (OCR + descrizione VLM delle immagini) → revisione opzionale → chunk + embeddings → LanceDB.

## Modelli

| Ruolo | Modello | RAM | Perché |
|---|---|---|---|
| LLM | `qwen3.6:35b-a3b` | ~22 GB | MoE: qualità alta e ~40 tok/s su M1 Max; il prompt processing veloce è decisivo nel RAG |
| Embeddings | `qwen3-embedding:4b` | ~3 GB | Multilingue (IT/EN), 32K contesto, vicino al top MTEB |
| Visione | `qwen3-vl:8b-instruct` | ~7 GB | Descrizioni precise delle immagini, caricato solo in ingestion |
| Reranker | `BAAI/bge-reranker-v2-m3` | ~0,6 GB | Cross-encoder locale multilingue |

L'analisi di fattibilità completa (alternative scartate, misure) è in [`HANDOFF.md`](HANDOFF.md#4-modelli-analisi-di-fattibilità).

## Requisiti

- macOS su Apple Silicon (testato: M1 Max, 32 GB) — o Linux per il solo container
- [Ollama](https://ollama.com) sull'host
- Un runtime Docker con Compose e buildx (qui: [Colima](https://github.com/abiosoft/colima))
- ~40 GB di disco per modelli e immagine

## Avvio rapido

```sh
# 1. Ollama sull'host, con impostazioni a basso carico
OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_FLASH_ATTENTION=1 \
OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=10m ollama serve &

ollama pull qwen3.6:35b-a3b
ollama pull qwen3-embedding:4b
ollama pull qwen3-vl:8b-instruct

# 2. Runtime container
colima start --vm-type vz --mount-type virtiofs --cpu 4 --memory 6 \
  --mount ~/haiku-rag-data:w

# 3. RAG
cp .env.example .env          # opzionale: cartella dati, porta, limiti CPU/RAM
docker compose up -d --build
curl http://127.0.0.1:8000/health

# 4. Portainer (opzionale)
docker compose -f infra/portainer.compose.yaml up -d   # → https://127.0.0.1:9443
```

Al primo avvio il container copia la configurazione di default in `~/haiku-rag-data/config/haiku.rag.yaml` e scarica ~2 GB di modelli Docling nella cache dati.

## Configurazione

| File | Uso |
|---|---|
| `~/haiku-rag-data/config/haiku.rag.yaml` | Config attiva del container (generata da `docker/default.haiku.rag.yaml`) |
| `haiku.rag.yaml` | Config per l'esecuzione nativa su macOS (OCR `ocrmac`) |
| `.env` | `RAG_DATA_DIR`, `RAG_PORT`, `RAG_CPUS`, `RAG_MEMORY`, `RAG_THREADS` |

Differenze container vs nativo: Ollama a `host.docker.internal`, OCR **Tesseract** (`ita`+`eng`) invece di `ocrmac`, torch solo CPU.

## Spostare il RAG su un'altra macchina

1. Clonare il repository (o `docker save haiku-local-rag` / `docker load`).
2. Copiare la cartella dati (`~/haiku-rag-data`).
3. Installare Ollama sull'host e scaricare i modelli.
4. `docker compose up -d --build`.

L'immagine è buildata per **arm64**: su un host x86 va ricostruita (`docker compose build`).

## Esecuzione nativa (sviluppo)

```sh
uv sync
uv run uvicorn haiku_local_rag.main:app --reload   # usa ./haiku.rag.yaml
uv run haiku-rag --help                            # CLI di haiku.rag
```

## Struttura

```
src/haiku_local_rag/     app FastAPI
docker/                  entrypoint e config di default del container
infra/                   servizi accessori (Portainer)
Dockerfile, compose.yaml container del RAG
haiku.rag.yaml           config per l'esecuzione nativa
HANDOFF.md               decisioni, stato e prossimi passi
```
