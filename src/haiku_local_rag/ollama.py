"""Client minimale per l'API di Ollama: inventario modelli con capacità e modelli caricati."""

import asyncio

import httpx


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()

    async def version(self) -> str:
        return (await self._get("/api/version"))["version"]

    async def loaded(self) -> list[dict]:
        """Modelli attualmente in memoria (/api/ps)."""
        models = (await self._get("/api/ps")).get("models", [])
        return [
            {
                "name": m["name"],
                "size_gib": round(m.get("size", 0) / 2**30, 1),
                "vram_gib": round(m.get("size_vram", 0) / 2**30, 1),
                "expires_at": m.get("expires_at"),
            }
            for m in models
        ]

    async def show(self, name: str) -> dict:
        return await self._post("/api/show", {"model": name})

    async def models(self) -> list[dict]:
        """Modelli installati, arricchiti con capacità, contesto e dimensione embedding."""
        tags = (await self._get("/api/tags")).get("models", [])
        details = await asyncio.gather(
            *(self.show(m["name"]) for m in tags), return_exceptions=True
        )
        result = []
        for tag, show in zip(tags, details, strict=True):
            show = show if isinstance(show, dict) else {}
            info = show.get("model_info", {})
            arch = info.get("general.architecture", "")
            capabilities = show.get("capabilities", [])
            result.append(
                {
                    "name": tag["name"],
                    "size_gib": round(tag.get("size", 0) / 2**30, 1),
                    "family": tag.get("details", {}).get("family"),
                    "parameters": tag.get("details", {}).get("parameter_size"),
                    "quantization": tag.get("details", {}).get("quantization_level"),
                    "capabilities": capabilities,
                    "context_length": info.get(f"{arch}.context_length"),
                    "embedding_length": info.get(f"{arch}.embedding_length"),
                    "experts": info.get(f"{arch}.expert_count"),
                    "is_embedding": "embedding" in capabilities,
                    "is_vision": "vision" in capabilities,
                    "is_llm": "completion" in capabilities and "embedding" not in capabilities,
                }
            )
        return sorted(result, key=lambda m: m["name"])
