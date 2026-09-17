from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
ASSETS_SRC = ROOT / "assets"
ASSETS = OUTPUT / "assets"
CREDENTIALS = ROOT / "credentials"
DATA = ROOT / "data"
ENV_FILE = ROOT / ".env"
OAUTH_CLIENT = CREDENTIALS / "oauth_client.json"
OAUTH_TOKEN = CREDENTIALS / "token.json"
FLOW_TICKERS_SEED = DATA / "flow-tickers.json"

FLOW_MCP_URL = "https://mcp-cockpit.dados.collieassociados.com/mcp"
EKYTE_MCP_URL = "https://api.ekyte.com/mcp"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_config() -> dict:
    return load_yaml(ROOT / "config.yaml")


def load_coord_map() -> dict:
    return load_yaml(ROOT / "coord-map.yaml")


def load_pessoas() -> list[dict]:
    return list((load_yaml(ROOT / "pessoas.yaml").get("pessoas") or []))


def ensure_output() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    CREDENTIALS.mkdir(parents=True, exist_ok=True)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env() -> dict[str, str]:
    values = parse_env_file(ENV_FILE)
    for key, value in list(values.items()):
        os.environ.setdefault(key, value)
    return values


def env(name: str, *aliases: str) -> str:
    load_env()
    for key in (name, *aliases):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def ekyte_token() -> str:
    raw = env("EKYTE_MCP_TOKEN")
    if raw:
        return raw.split("token=")[-1]
    raise SystemExit(
        "EKYTE_MCP_TOKEN ausente. Copie .env.example para .env e cole o token MCP do Ekyte. "
        "Ver SETUP.md, seção Ekyte."
    )
