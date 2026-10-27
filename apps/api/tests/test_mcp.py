import json

import httpx

from app.errors import TransientToolError
from app.mcp import HTTPMCPClient


def test_mcp_client_calls_tools_and_parses_content():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            result = {"tools": [{"name": "gmail.list_messages"}]}
        else:
            assert body["method"] == "tools/call"
            assert body["params"]["name"] == "gmail.list_messages"
            result = {"content": [{"type": "text", "text": json.dumps({"items": [{"subject": "Hello"}], "count": 1})}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    client = HTTPMCPClient("http://mcp.test/rpc", transport=httpx.MockTransport(handler))
    assert client.list_tools()["tools"][0]["name"] == "gmail.list_messages"
    assert client.call("gmail.list_messages", {"query": "unread"})["count"] == 1


def test_mcp_server_error_is_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"jsonrpc": "2.0", "id": 1, "error": {"message": "unavailable"}})

    client = HTTPMCPClient("http://mcp.test/rpc", transport=httpx.MockTransport(handler))
    try:
        client.list_tools()
        raise AssertionError("expected a retryable error")
    except TransientToolError:
        pass
