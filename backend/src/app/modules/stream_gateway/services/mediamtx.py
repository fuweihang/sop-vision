import httpx


class MediaMTXClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
        )

    async def is_ready(self) -> bool:
        try:
            response = await self._client.get("/v3/config/paths/list")
        except httpx.RequestError:
            return False
        return response.is_success

    async def close(self) -> None:
        await self._client.aclose()
