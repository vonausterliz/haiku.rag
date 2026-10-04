# HANDOFF — RAG locale basato su haiku.rag + Ollama

_Ultimo aggiornamento: 2026-10-04 04:35 · Owner: Luca · Stato: **infrastruttura pronta, codice applicativo da scrivere**_

## ▶ Ripresa (leggere per primo)
Operazioni notturne del 2026-10-04 — **tutte completate**:
1. ✅ **Pull `qwen3.6:35b-a3b` completato** (22 GB; tutti e 3 i modelli presenti). Controllo: `~/Applications/Ollama.app/Contents/Resources/ollama list` deve mostrare 3 modelli. Se manca: `ollama pull qwen3.6:35b-a3b` (riprende dal punto in cui si era fermato).
2. ✅ **`docker-buildx` v0.37.2 installato** in `~/.docker/cli-plugins/`. Controllo: `docker buildx version`. Se il file è assente o corrotto, riscaricarlo da github.com/docker/buildx/releases (`buildx-<ver>.darwin-arm64`).
3. ✅ **Container RAG buildato e avviato**: immagine `haiku-local-rag:latest` 3,96 GB (arm64), container `haiku-rag` **healthy**. `/health` → config `/data/config/haiku.rag.yaml`, Ollama raggiungibile, 3 modelli visti. Primo avvio: config di default copiata e ~2,2 GB di modelli Docling/HF scaricati in `~/haiku-rag-data/cache` (avvisi HF senza token: innocui). Log build in `.build.log` (gitignored).

**Infrastruttura completa.** Prossimo passo: §8 punto 2 (ingest di prova) e poi l'app.

Dopo un riavvio del Mac, prima di tutto:
```sh
export PATH=~/.local/bin:$PATH
OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=10m \
  ~/Applications/Ollama.app/Contents/Resources/ollama serve &   # TODO: LaunchAgent
colima start
docker compose up -d                                          # RAG  → http://127.0.0.1:8000
docker compose -f infra/portainer.compose.yaml up -d          # Portainer → https://127.0.0.1:9443
```
Poi proseguire dal §8 "Prossimi passi" (test di ingest, poi implementazione `app/`).

⚠️ La rete di casa è lenta e a tratti instabile (caduta IPv6 durante la notte del 3/10): **mai scaricare modelli e pacchetti/immagini insieme**.

## 1. Obiettivo
RAG completamente locale su questo Mac, basato su **[haiku.rag](https://github.com/ggozad/haiku.rag)** (LanceDB + Docling + Ollama), con:
- **Pagina Admin**: parametri haiku.rag, scelta LLM / embeddings / VLM (dai modelli presenti in Ollama, con pull), profilo di ingestion.
- **Più corpus** (un DB LanceDB per corpus), interrogabili singolarmente o insieme.
- **Ingestion a basso impatto**: documento → **Markdown** (OCR + descrizione precisa delle immagini) → (revisione opzionale) → chunk + embeddings.

## 2. Macchina
MacBook Pro M1 Max, 10 CPU (8P+2E), GPU 32 core, **32 GB** unificata (~400 GB/s), macOS 27.0.1, 868 GB liberi.
GPU wired limit di default ≈ 21–24 GB (alzabile: `sudo sysctl iogpu.wired_limit_mb=26624`, non persistente — NON applicato).

## 3. Decisioni prese (con l'utente)
| Tema | Scelta |
|---|---|
| Framework RAG | haiku.rag (libreria Python, ≥3.12) |
| Documenti | PDF testuali + **scansionati**, Office/HTML/MD, **IT + EN** |
| Conversione | Tutto convertito in **.md** prima dell'ingest; immagini **descritte in modo preciso** dal VLM |
| Revisione MD | **Opzionale per corpus** (flag `review_required`: default off → auto-ingest; on → stato "da approvare" con anteprima/editor) |
| Utenti | **Solo locale**, bind `127.0.0.1`, Admin protetta da password semplice |
| Query | **Singolo corpus o multi-corpus** → vincolo: stesso embedder per tutti i corpus |
| Stack UI | **FastAPI + Jinja2 + HTMX** (un solo processo Python, niente Node) |
| VLM immagini | **Dedicato medio**: `qwen3-vl:8b` (alternativa `gemma4:12b`) |
| Deploy | **App RAG in container** (portabile), **Ollama nativo sull'host** (GPU Metal non accessibile da Docker su macOS) |
| Runtime container | **Colima** (binari in `~/.local/bin`, niente Homebrew) |
| Dati | **`~/haiku-rag-data`** sull'host, montata in `/data` (config, corpora, cache modelli HF). Nessun dato nell'immagine |

## 4. Modelli (analisi di fattibilità)
Nessun modello che entra in 32 GB è al livello di Opus; target realistico: classe Haiku/Sonnet su QA con contesto.
In RAG il collo di bottiglia è il **prompt processing** (contesti 4–8k token) → i **MoE** vincono.

| Ruolo | Modello | RAM | Note |
|---|---|---|---|
| **LLM (default)** | `qwen3.6:35b-a3b` | ~20–22 GB Q4 | ~40 tok/s gen, ~800 tok/s prompt su M1 Max. Miglior compromesso qualità/fruibilità |
| LLM alternativo | `gemma4:26b` (26B-A4B MoE) | ~17 GB | Selezionabile da Admin, NON scaricato |
| Scartato | `qwen3.6:27b` dense | ~17 GB | Qualità migliore ma ~8 tok/s e ~100 tok/s prompt → TTFT ~60 s: inusabile |
| **Embeddings** | `qwen3-embedding:4b` | ~3 GB | 2560 dim, 32K ctx, multilingue, MTEB ~67 |
| Embeddings "eco" | `qwen3-embedding:0.6b` | <1 GB | Fallback leggero (MTEB ~60) |
| Scartato | `qwen3-embedding:8b` | ~5–8 GB | Non convive con l'LLM |
| **VLM** | `qwen3-vl:8b` | ~6 GB | Solo durante l'ingestion |
| Reranker | `BAAI/bge-reranker-v2-m3` (cross-encoder) | ~0.6 GB | Opzionale, **da verificare** il supporto/nome chiave in haiku.rag |

## 5. Stato setup (fatto in questa sessione)
- [x] `uv` installato in `~/.local/bin/uv` + Python 3.12.15 (gestito da uv). Python di sistema 3.9 non usato.
- [x] **Ollama 0.35.1** in `~/Applications/Ollama.app` (nessun Homebrew sulla macchina, niente sudo).
  - Avviato **a mano** con: `OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=10m ~/Applications/Ollama.app/Contents/Resources/ollama serve`
  - ⚠️ Non è persistente: al riavvio va rilanciato → TODO: LaunchAgent (`~/Library/LaunchAgents/com.local.ollama.plist`) con queste env, oppure aprire Ollama.app e impostarle con `launchctl setenv`.
- [x] `qwen3-embedding:4b` scaricato.
- [x] `qwen3-vl:8b` scaricato.
- [x] `qwen3.6:35b-a3b` scaricato (22 GB). ~~pull in corso a fine sessione → verificare con `ollama list`, eventualmente rilanciare `ollama pull` (riprende da dove si era fermato).~~
- [x] Progetto uv `haiku-local-rag` (layout `src/haiku_local_rag`), dipendenze installate: **haiku.rag 0.92.0**, fastapi, uvicorn, jinja2, python-multipart, ocrmac, pyyaml; `git init` fatto, primo commit con setup + container.
- [x] `haiku.rag.yaml` scritto e **validato** con `AppConfig.model_validate` (reranker `cross-encoder` verificato nel sorgente; prompt VLM custom in `prompts.picture_description`).
- [x] `uv run haiku-rag doctor` gira: segnala solo "Database path does not exist" (normale prima del primo ingest).
- [x] Colima attivo (Docker 29.5, VM vz 4 CPU / 8 GB). Contesto docker `colima`. Dopo un riavvio del Mac: `colima start` (riusa la config in `~/.colima/default/colima.yaml`).
- [x] **Portainer CE** (`infra/portainer.compose.yaml`) su https://127.0.0.1:9443, dati nel volume `portainer_data`. Al primo avvio l'admin va creato entro 5 min (altrimenti `docker restart portainer`).
- [x] Verificato: un container raggiunge Ollama su `host.docker.internal:11434` anche con Ollama in ascolto solo su 127.0.0.1.
- [x] Immagine RAG buildata con buildx (il builder legacy non supporta `RUN --mount`), container `haiku-rag` healthy su http://127.0.0.1:8000/health.
- [ ] Ingest di prova end-to-end (nel container).

> ⚠️ **Lezione di rete:** connessione lenta/instabile. Pull Ollama + `uv add` in parallelo → `uv` fallisce per timeout (`transformers` wheel). Usare `UV_HTTP_TIMEOUT=600` e non scaricare modelli e pacchetti contemporaneamente.

## 5b. Container
File: `Dockerfile`, `compose.yaml`, `docker/entrypoint.sh`, `docker/default.haiku.rag.yaml`, `.env.example`.
- Immagine `python:3.12-slim-bookworm` + uv; **torch solo CPU** su Linux (indice `pytorch-cpu` in `pyproject.toml`, torch/torchvision dipendenze dirette altrimenti le `sources` uv non si applicano → senza, l'immagine tirerebbe giù GB di pacchetti `nvidia-*`).
- OCR nel container: **Tesseract `ita`+`eng`** (ocrmac è solo macOS; resta per l'esecuzione nativa, dipendenza con marker `sys_platform == 'darwin'`).
- `/data/config/haiku.rag.yaml` creato dall'entrypoint al primo avvio copiando `docker/default.haiku.rag.yaml`; poi è la pagina Admin a modificarlo. Modelli Docling/HF scaricati una volta in `/data/cache/huggingface`.
- Ollama raggiunto a `http://host.docker.internal:11434` (`extra_hosts: host-gateway`). Con Colima funziona anche con Ollama in ascolto su 127.0.0.1 (**verificato**).
- Limiti risorse da `.env`: `RAG_CPUS=4`, `RAG_MEMORY=6g`, `RAG_THREADS=2`; porta solo su `127.0.0.1:8000`.
- Colima avviato con: `colima start --vm-type vz --vz-rosetta --mount-type virtiofs --cpu 4 --memory 8 --disk 60 --mount ~/haiku-rag-data:w --mount <progetto>`.
- Spostare su un'altra macchina: repo (o immagine `docker save`) + cartella dati + Ollama installato sull'host. Immagine buildata per arm64: su server x86 rifare `docker compose build` (o `buildx --platform linux/amd64`).
- Ingestion nel container: Docling su CPU (niente MPS) → più lenta che nativa, ma i limiti del container la tengono sotto controllo.
- App attuale: solo `GET /health` (`src/haiku_local_rag/main.py`) — config caricata + raggiungibilità Ollama.

## 6. Vincoli tecnici di haiku.rag (dalla doc)
- Config: `haiku.rag.yaml` (cwd) o `HAIKU_RAG_CONFIG_PATH`. Corpus = `lancedb.databases.<nome>: <path>`.
- **Un solo writer per database** → ingestion serializzata per corpus.
- **Stessa coppia provider/modello/dim** per tutti i DB interrogati insieme, altrimenti `ConfigMismatchError`. Cambio embedder da Admin ⇒ **reindicizzazione** di tutti i corpus (job in coda, dalla cache .md: niente riconversione).
- `processing.pictures: description` + `conversion_options.picture_description` = descrizioni VLM inline. `ocr_engine: ocrmac` = OCR Apple Vision.
- Ingester ufficiale (`haiku-ingester`) esiste (queue SQLite, worker default 4, dashboard :8765) — valutato **non** adatto come base: vogliamo controllo fine su carico, revisione MD e UI unica. Si può riusarne le idee.
- Sorgente installato: `.venv/lib/python3.12/site-packages/haiku/rag/` (config: `config/models.py` → `AppConfig`, `PromptsConfig`, `RerankingConfig`; validare lo YAML con `AppConfig.model_validate`).
- Doc: [config](https://ggozad.github.io/haiku.rag/configuration/) · [providers](https://ggozad.github.io/haiku.rag/configuration/providers/) · [processing](https://ggozad.github.io/haiku.rag/configuration/processing/) · [multi-db](https://ggozad.github.io/haiku.rag/configuration/multiple-databases/) · [ingester](https://ggozad.github.io/haiku.rag/ingester/)

## 7. Architettura da implementare
```
app/
  main.py            FastAPI (127.0.0.1:8000), mount static, router
  settings.py        lettura/scrittura haiku.rag.yaml + app.yaml (profili, password admin, flag corpus)
  ollama_client.py   /api/tags, /api/pull (stream progress), /api/ps, unload (keep_alive=0)
  corpora.py         CRUD corpus → data/corpora/<nome>.lancedb + data/corpora/<nome>/{inbox,markdown,originals}
  pipeline/
    convert.py       Docling → Markdown (ocrmac, VLM picture description) → salva .md
    index.py         haiku.rag client: add document from .md (metadati: corpus, file originale)
    queue.py         coda SQLite (jobs: convert|review|index|reindex), 1 worker, pausa/riprendi
  rag.py             query/ask su uno o più corpus (haiku.rag multi-db), citazioni
  templates/         chat.html, corpora.html, corpus_detail.html, review.html, admin.html (HTMX)
data/                (gitignored)
```
Flusso documento: `upload → originals/ → [job convert] → markdown/<doc>.md → (review_required? stato "pending_review" : ) → [job index] → LanceDB`.
Usare il **.md come sorgente di verità** per indicizzazione e reindex.

### Ingestion a basso impatto ("profili" in Admin)
- **1 worker** globale; job eseguiti in subprocess con `taskpolicy -b` (core efficienti/background QoS) + `nice 10`.
- Docling: `OMP_NUM_THREADS` / `torch.set_num_threads` = 2 (Leggero) / 4 (Bilanciato) / 6 (Veloce).
- Prima della fase VLM: scaricare l'LLM (`POST /api/generate {"model": LLM, "keep_alive": 0}`); dopo la fase VLM scaricare il VLM.
- `embeddings.batch_size` basso (32), pausa configurabile tra documenti, `split_pages: 10`.
- Pausa/riprendi coda + "pausa automatica se l'utente sta chattando" (lock condiviso).

### Pagina Admin (campi)
LLM (select da `ollama list` + pull), temperature, max_tokens, thinking · Embedder (select + avviso reindex) · VLM + max_tokens + prompt descrizione (IT, "descrivi in modo preciso: testo visibile, dati di grafici/tabelle, relazioni") · chunk_size, chunker_type, tabelle markdown · OCR on/force, lingue · reranking on/off · profilo ingestion · stato Ollama (`/api/ps`, RAM).

## 8. Prossimi passi (in ordine)
1. Verificare pull completati (`~/Applications/Ollama.app/Contents/Resources/ollama list`) e `uv run haiku-rag doctor`.
2. Test end-to-end da CLI: `uv run haiku-rag add-src <pdf>` + `uv run haiku-rag ask "..."`; misurare RAM (`/api/ps`) e tempi; verificare la qualità delle descrizioni VLM (prompt in `prompts.picture_description`) e la latenza del reranker.
3. Verificare API Python di haiku.rag (client, multi-db, conversione a Markdown via Docling) — leggere il codice in `.venv/lib/python3.12/site-packages/haiku/rag/`.
4. Implementare `app/` secondo §7, partendo da coda + pipeline, poi UI.
5. LaunchAgent per Ollama e per l'app.
6. Benchmark qualità su un set di 10–20 domande reali; eventuale confronto `gemma4:26b`.

## 9. Domande ancora aperte
- Password Admin: definirla al primo avvio (proposta: setup wizard).
- Mantenere copia degli originali dopo la conversione? (proposta: sì, in `originals/`).
- Lingua del prompt di sistema QA: italiano con risposta nella lingua della domanda (proposta).
