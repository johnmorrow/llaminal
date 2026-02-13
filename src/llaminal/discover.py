"""Auto-discover running OpenAI-compatible LLM servers."""

import httpx

# (port, label) pairs to scan
KNOWN_SERVERS = [
    (8080, "llama.cpp"),
    (11434, "ollama"),
    (8000, "vLLM"),
    (5000, "local server"),
    (1234, "LM Studio"),
]

SCAN_TIMEOUT = 1.0  # seconds per probe


async def probe_server(base_url: str) -> bool:
    """Check if an OpenAI-compatible server is responding at base_url."""
    async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as client:
        try:
            resp = await client.get(f"{base_url}/v1/models")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
            return False


async def discover_servers() -> list[tuple[str, str]]:
    """Scan known ports and return list of (base_url, label) for responding servers."""
    found = []
    for port, label in KNOWN_SERVERS:
        base_url = f"http://localhost:{port}"
        if await probe_server(base_url):
            found.append((base_url, label))
    return found
