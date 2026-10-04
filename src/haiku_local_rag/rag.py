"""Client haiku.rag condiviso tra le richieste.

Aprirne uno per domanda ricarica ogni volta reranker e connessioni (minuti con un
cross-encoder su CPU): lo teniamo aperto e lo ricreiamo solo quando cambia la config.
"""

import asyncio

from haiku.rag.client import HaikuRAG

from haiku_local_rag import settings

_client: HaikuRAG | None = None
_config_mtime: float | None = None
_lock = asyncio.Lock()


async def get_client() -> HaikuRAG:
    global _client, _config_mtime
    async with _lock:
        mtime = settings.CONFIG_PATH.stat().st_mtime
        if _client is None or mtime != _config_mtime:
            if _client is not None:
                await _client.__aexit__(None, None, None)
            client = HaikuRAG(config=settings.load_config(), read_only=True)
            _client = await client.__aenter__()
            _config_mtime = mtime
        return _client


async def close() -> None:
    global _client
    async with _lock:
        if _client is not None:
            await _client.__aexit__(None, None, None)
            _client = None
