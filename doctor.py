#!/usr/bin/env python3
"""Confere se o setup local está pronto para gerar a pauta."""
from __future__ import annotations

import sys

from paths import ENV_FILE, FLOW_TICKERS_SEED, OAUTH_CLIENT, OAUTH_TOKEN, ROOT, env, load_config


def _ok(msg: str) -> None:
    print(f"  ok   {msg}")


def _warn(msg: str) -> None:
    print(f"  avis {msg}")


def _fail(msg: str) -> None:
    print(f"  falha {msg}")


def main() -> int:
    print("Pauta WEB/SEO — doctor\n")
    errors = 0

    print("1. Python e pasta")
    if sys.version_info < (3, 10):
        _fail(f"Python 3.10+ (achado {sys.version.split()[0]})")
        errors += 1
    else:
        _ok(f"Python {sys.version.split()[0]}")
    _ok(str(ROOT))

    print("\n2. Dependências")
    try:
        import googleapiclient  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        _fail(f"pip: {exc}. Rode python3 -m pip install -r requirements.txt")
        errors += 1
    else:
        _ok("google-api-python-client + PyYAML")

    print("\n3. Google Chat (OAuth da SUA conta)")
    if not OAUTH_CLIENT.exists():
        _fail(f"falta {OAUTH_CLIENT.relative_to(ROOT)} — SETUP.md, seção Google Cloud")
        errors += 1
    else:
        _ok("credentials/oauth_client.json")
    if not OAUTH_TOKEN.exists():
        _fail("falta credentials/token.json — rode python3 setup_auth.py")
        errors += 1
    else:
        _ok("credentials/token.json")
        try:
            from auth import build_chat
            from chat_api import get_space
            from googleapiclient.errors import HttpError

            service = build_chat(allow_interactive=False)
            config = load_config()
            for space in config.get("spaces") or []:
                try:
                    info = get_space(service, space["id"])
                    _ok(f"canal {space.get('label')}: {info.get('displayName') or space['id']}")
                except HttpError as exc:
                    _fail(
                        f"não li {space.get('display_name')}. "
                        f"Entre no canal com esta conta. HTTP {exc.resp.status}"
                    )
                    errors += 1
        except Exception as exc:  # noqa: BLE001
            _fail(f"Chat API: {exc}")
            errors += 1

    print("\n4. Ekyte")
    if not ENV_FILE.exists():
        _fail("falta .env — copie .env.example e cole o token MCP")
        errors += 1
    token = env("EKYTE_MCP_TOKEN")
    if not token:
        _fail("EKYTE_MCP_TOKEN vazio no .env")
        errors += 1
    else:
        _ok("EKYTE_MCP_TOKEN preenchido")
        try:
            from mcp_clients import ekyte_client

            client = ekyte_client()
            payload = client.call_tool("list_short_workspaces", {"active": 1, "textSearch": "KCE"})
            _ok(f"Ekyte MCP respondeu ({type(payload).__name__})")
        except Exception as exc:  # noqa: BLE001
            _fail(f"Ekyte MCP: {exc}")
            errors += 1

    print("\n5. FLOW (opcional)")
    if env("FLOW_MCP_JWT", "MCP_COCKPIT_JWT") and env("FLOW_MCP_GATEWAY", "MCP_GATEWAY_TOKEN"):
        try:
            from mcp_clients import flow_client

            flow_client()
            _ok("FLOW MCP conectou")
        except Exception as exc:  # noqa: BLE001
            _warn(f"FLOW MCP falhou ({exc}); o seed data/flow-tickers.json cobre o match de cliente")
    else:
        if FLOW_TICKERS_SEED.exists():
            _ok("sem FLOW no .env — usando data/flow-tickers.json")
        else:
            _warn("sem FLOW e sem seed; ticker/cliente pode ficar em branco")

    print("\n6. Arquivos do painel")
    for rel in ("config.yaml", "pessoas.yaml", "template.html", "assets/colli-red.png"):
        path = ROOT / rel
        if path.exists():
            _ok(rel)
        else:
            _fail(f"falta {rel}")
            errors += 1

    print()
    if errors:
        print(f"{errors} problema(s). Abre SETUP.md e resolve na ordem.")
        return 1
    print("Pronto. Rode: python3 run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
