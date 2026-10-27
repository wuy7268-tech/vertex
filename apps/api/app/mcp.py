import json
from typing import Any

import httpx

from app.errors import PermanentToolError, TransientToolError


class HTTPMCPClient:
    """Minimal MCP-over-HTTP client.

    Speaks JSON-RPC `tools/list` and `tools/call`, which is the surface Vertex
    uses for Google Calendar, Gmail, Drive, GitHub, and Notion.
    """

    def __init__(self, url: str, headers: dict[str, str] | None = None, transport: httpx.BaseTransport | None = None):
        self.url = url
        self.headers = headers or {}
        self.transport = transport
        self._id = 0

    def list_tools(self) -> Any:
        return self._rpc("tools/list", {})

    def call(self, name: str, arguments: dict) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return normalize_mcp_result(result)

    def _rpc(self, method: str, params: dict) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        try:
            with httpx.Client(transport=self.transport, timeout=20.0) as client:
                response = client.post(self.url, json=payload, headers=self.headers)
        except httpx.TimeoutException as exc:
            raise TransientToolError(f"MCP timeout calling {method}") from exc
        except httpx.HTTPError as exc:
            raise TransientToolError(f"MCP request failed: {exc}") from exc
        if response.status_code >= 500:
            raise TransientToolError(f"MCP {response.status_code} from {method}")
        if response.status_code >= 400:
            raise PermanentToolError(f"MCP {response.status_code} from {method}")
        body = response.json()
        if isinstance(body, dict) and body.get("error"):
            message = body["error"].get("message", "MCP error") if isinstance(body["error"], dict) else str(body["error"])
            raise PermanentToolError(message)
        return body.get("result") if isinstance(body, dict) else body


def normalize_mcp_result(result: Any) -> Any:
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        texts = [item.get("text", "") for item in result["content"] if isinstance(item, dict)]
        joined = "\n".join(texts).strip()
        if not joined:
            return {"items": [], "count": 0}
        try:
            parsed = json.loads(joined)
        except json.JSONDecodeError:
            return {"text": joined, "items": [], "count": 0}
        return parsed if isinstance(parsed, dict) else {"items": parsed, "count": len(parsed)}
    if isinstance(result, dict):
        return result
    return {"text": "" if result is None else str(result), "items": [], "count": 0}
