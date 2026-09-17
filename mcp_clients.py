from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from paths import EKYTE_MCP_URL, FLOW_MCP_URL, env, ekyte_token


class McpError(RuntimeError):
    pass


class JsonRpcClient:
    def __init__(self, url: str, headers: dict[str, str]):
        self.url = url
        self.headers = headers
        self.session_id: str | None = None
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, body: dict, expect_response: bool = True) -> dict | None:
        data = json.dumps(body).encode("utf-8")
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["mcp-session-id"] = self.session_id
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                if sid:
                    self.session_id = sid
                if resp.status == 202 and not expect_response:
                    return None
                raw = resp.read().decode("utf-8")
                return _parse_sse_or_json(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:800]
            raise McpError(f"HTTP {exc.code}: {detail}") from exc

    def initialize(self, name: str) -> None:
        self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": name, "version": "1.0"},
                },
            }
        )
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_response=False,
        )

    def call_tool(self, name: str, arguments: dict) -> Any:
        resp = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if not resp:
            raise McpError(f"Tool {name} sem resposta")
        if resp.get("error"):
            raise McpError(f"Tool {name}: {resp['error']}")
        result = resp.get("result") or {}
        content = result.get("content") or []
        texts = []
        for item in content:
            if item.get("type") == "text" and item.get("text"):
                texts.append(item["text"])
        if not texts:
            return result
        blob = texts[0]
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return {"text": blob}


def _parse_sse_or_json(raw: str) -> dict:
    stripped = raw.lstrip()
    if stripped.startswith("event:") or stripped.startswith("data:"):
        for line in raw.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise McpError(f"SSE sem data: {raw[:200]}")
    return json.loads(raw) if stripped else {}


def flow_client() -> JsonRpcClient:
    jwt = env("FLOW_MCP_JWT", "MCP_COCKPIT_JWT")
    gateway = env("FLOW_MCP_GATEWAY", "MCP_GATEWAY_TOKEN")
    if not jwt or not gateway:
        raise McpError("FLOW_MCP_JWT / FLOW_MCP_GATEWAY ausentes no .env (opcional).")
    client = JsonRpcClient(
        FLOW_MCP_URL,
        {
            "Authorization": f"Bearer {jwt}",
            "x-mcp-gateway": gateway,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    client.initialize("pauta-web-seo")
    return client


def ekyte_client() -> JsonRpcClient:
    token = ekyte_token()
    url = EKYTE_MCP_URL if "token=" in EKYTE_MCP_URL else f"{EKYTE_MCP_URL}?token={token}"
    if "token=" not in url:
        url = f"{url}?token={token}"
    client = JsonRpcClient(
        url,
        {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        client.initialize("pauta-web-seo")
    except McpError:
        pass
    return client


def ekyte_colli_client() -> JsonRpcClient:
    url = env("EKYTE_COLLI_URL")
    token = env("EKYTE_COLLI_TOKEN")
    if not url:
        raise McpError("EKYTE_COLLI_URL ausente — opcional, só para localize_project.")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    client = JsonRpcClient(url, headers)
    try:
        client.initialize("pauta-web-seo")
    except McpError:
        pass
    return client
