#!/bin/sh
# Prepara la cartella dati montata al primo avvio, poi esegue il comando del container.
set -e

mkdir -p "$DATA_DIR/config" "$DATA_DIR/corpora" "$DATA_DIR/cache/huggingface"

if [ ! -f "$HAIKU_RAG_CONFIG_PATH" ]; then
    echo "Prima esecuzione: copio la configurazione di default in $HAIKU_RAG_CONFIG_PATH"
    cp /app/default.haiku.rag.yaml "$HAIKU_RAG_CONFIG_PATH"
fi

# Modelli Docling (layout, tabelle, OCR) nella cache dati: scaricati una volta sola
if [ ! -f "$DATA_DIR/cache/.docling-models-ready" ]; then
    echo "Scarico i modelli Docling in $HF_HOME (solo la prima volta)..."
    haiku-rag download-models \
        && touch "$DATA_DIR/cache/.docling-models-ready"
fi

exec "$@"
