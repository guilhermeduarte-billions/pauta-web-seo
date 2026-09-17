from __future__ import annotations

import json
import re
import unicodedata

from mcp_clients import McpError, flow_client
from paths import FLOW_TICKERS_SEED, OUTPUT, load_config, load_coord_map


def _slugify(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def _coord_from_username(username: str | None, mapping: dict) -> str:
    if not username:
        return "nao_classificado"
    key = str(username).strip()
    lower = key.lower()
    if key in mapping:
        return mapping[key]
    if lower in mapping:
        return mapping[lower]
    if "smarito" in lower:
        return "smarito"
    if "duarte" in lower or "guilherme" in lower:
        return "duarte"
    if "nayara" in lower or "ventura" in lower:
        return "ventura"
    return "outra"


def _squad_slug(raw) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return _slugify(raw)
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict):
            return _slugify(first.get("name") or "")
        return _slugify(str(first))
    if isinstance(raw, dict):
        return _slugify(raw.get("name") or "")
    return None


def _rows(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return (
            payload.get("data")
            or payload.get("rows")
            or payload.get("items")
            or payload.get("projects")
            or []
        )
    return []


def _looks_legal(name: str) -> bool:
    upper = (name or "").upper()
    return "LTDA" in upper or "S/A" in upper or "S/S" in upper or "/0001-" in upper


def _best_display(*names: str | None) -> str:
    candidates = [item.strip() for item in names if item and str(item).strip()]
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (_looks_legal(item), len(item)))
    return candidates[0]


def _upsert(
    catalog: dict[str, dict],
    ticker: str,
    *,
    nome: str | None,
    gerencia: str | None,
    coord: str | None,
    fonte: str,
    aliases: list[str] | None = None,
) -> None:
    ticker = (ticker or "").upper()
    if not ticker:
        return
    prev = catalog.get(ticker) or {}
    merged = set(prev.get("aliases") or [])
    if prev.get("nome"):
        merged.add(prev["nome"])
    if nome:
        merged.add(nome)
    for alias in aliases or []:
        if alias:
            merged.add(alias)
    catalog[ticker] = {
        "ticker": ticker,
        "nome": _best_display(prev.get("nome"), nome) or ticker,
        "aliases": sorted(merged),
        "gerencia": gerencia or prev.get("gerencia") or "nao_classificado",
        "coord": coord or prev.get("coord") or "nao_classificado",
        "fonte": fonte or prev.get("fonte"),
    }


def _from_seed() -> dict[str, dict]:
    if not FLOW_TICKERS_SEED.exists():
        return {}
    try:
        raw = json.loads(FLOW_TICKERS_SEED.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    catalog: dict[str, dict] = {}
    for ticker, info in raw.items():
        if not isinstance(info, dict):
            continue
        _upsert(
            catalog,
            ticker,
            nome=info.get("nome"),
            gerencia=info.get("gerencia"),
            coord=info.get("coord"),
            fonte=info.get("fonte") or "seed",
            aliases=list(info.get("aliases") or []),
        )
    return catalog


def ingest_flow() -> dict[str, dict]:
    config = load_config()
    mapping = load_coord_map().get("flow_coord") or {}
    catalog = _from_seed()
    try:
        client = flow_client()
    except McpError as exc:
        print(f"aviso: FLOW MCP indisponível ({exc}); usando data/flow-tickers.json", flush=True)
        client = None

    if client:
        for squad in config.get("flow_squads") or ["Billions"]:
            try:
                page = 1
                while page <= 20:
                    snap = client.call_tool(
                        "cockpit_query_table",
                        {
                            "page": page,
                            "pageSize": 50,
                            "filterBySquad": squad,
                            "filterByStatus": "active",
                            "sortBy": "name",
                            "sortOrder": "asc",
                        },
                    )
                    rows = _rows(snap)
                    if not rows:
                        break
                    for raw in rows:
                        ticker = (raw.get("ticker") or "").upper()
                        if not ticker:
                            continue
                        _upsert(
                            catalog,
                            ticker,
                            nome=raw.get("name") or ticker,
                            gerencia=_squad_slug(raw.get("squad")) or _slugify(squad),
                            coord=_coord_from_username(raw.get("project_coordinator"), mapping),
                            fonte="flow",
                            aliases=[raw.get("name")],
                        )
                    if len(rows) < 50:
                        break
                    page += 1
            except Exception as exc:  # noqa: BLE001
                print(f"aviso: cockpit_query_table {squad} falhou ({exc})", flush=True)

    cache = OUTPUT / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "flow-tickers.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return catalog
