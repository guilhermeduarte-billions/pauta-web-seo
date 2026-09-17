#!/usr/bin/env python3
"""Gera a Pauta WEB/SEO (Chat × Ekyte). Não posta no Google Chat."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime

from googleapiclient.errors import HttpError

from enrich import enrich_pedido, unique_name_index
from ignored import stamp_row
from ingest_chat import ingest_chat
from ingest_ekyte import ingest_ekyte_tasks, ingest_executor_tasks
from ingest_flow import ingest_flow
from match import chat_url, classify_pedido, ekyte_url
from auth import build_chat
from chat_api import get_space
from paths import OUTPUT, ensure_output, load_config
from render import now_label, render
from serve import serve as serve_radar


def verify_spaces(config: dict) -> None:
    service = build_chat(allow_interactive=False)
    for space in config["spaces"]:
        space_id = space["id"]
        try:
            info = get_space(service, space_id)
        except HttpError as exc:
            raise SystemExit(
                f"Não consegui ler {space_id} ({space.get('display_name')}). "
                f"Confirme que você é membro do canal. HTTP {exc.resp.status}."
            ) from exc
        name = (info.get("displayName") or "").strip()
        print(f"ok space {space_id} · {name or space.get('label')}", flush=True)


def serialize_row(pedido: dict, classified: dict, task: dict | None) -> dict:
    task_id = None
    if pedido.get("task_ids"):
        task_id = pedido["task_ids"][0]
    created = pedido.get("created_at")
    days_open = 0
    if created:
        try:
            start = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_open = max(0, (datetime.now(start.tzinfo) - start).days)
        except ValueError:
            days_open = 0
    return {
        "canal": pedido.get("canal"),
        "canal_label": pedido.get("canal_label"),
        "created_at": created,
        "days_open": days_open,
        "autor_id": pedido.get("autor_id"),
        "autor_nome": pedido.get("autor_nome"),
        "solicitante_coord": pedido.get("solicitante_coord"),
        "solicitante_coord_label": pedido.get("solicitante_coord_label"),
        "ticker": pedido.get("ticker"),
        "cliente": pedido.get("cliente"),
        "gerencia": pedido.get("gerencia"),
        "cliente_coord": pedido.get("cliente_coord"),
        "cliente_coord_label": pedido.get("cliente_coord_label"),
        "trecho": pedido.get("trecho"),
        "respondida": classified.get("respondida"),
        "respondida_em": classified.get("respondida_em"),
        "encaminhada": classified.get("encaminhada"),
        "task_id": task_id,
        "task_url": ekyte_url(task_id) if task_id else None,
        "prazo": classified.get("prazo"),
        "concluida_em": classified.get("concluida_em"),
        "estado": classified.get("estado"),
        "executor": classified.get("executor"),
        "pauta": classified.get("pauta"),
        "gravidade": classified.get("gravidade"),
        "chat_url": chat_url(pedido["space_id"], pedido["thread"]),
        "task_title": (task or {}).get("title") if task else None,
        "thread": pedido.get("thread"),
        "space_id": pedido.get("space_id"),
        "body": "\n\n".join(pedido.get("textos") or [])[:4000],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pauta WEB/SEO — Chat × Ekyte.")
    parser.add_argument("--no-open", action="store_true", help="Não abre o HTML no browser.")
    parser.add_argument("--no-serve", action="store_true", help="Só gera o HTML (file://). Sem botão funcional.")
    parser.add_argument("--serve-only", action="store_true", help="Sobe o servidor no snapshot já gerado.")
    parser.add_argument("--port", type=int, help="Porta do servidor local.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_output()
    config = load_config()
    port = args.port or int((config.get("ekyte") or {}).get("serve_port") or 8768)

    if not args.serve_only:
        print("1/6 conferindo canais do Chat…", flush=True)
        verify_spaces(config)

        print("2/6 catálogo FLOW (gerência/coord por ticker)…", flush=True)
        catalog = ingest_flow()
        print(f"   {len(catalog)} tickers", flush=True)

        print("3/6 ingest Chat (45 dias, só leitura)…", flush=True)
        pedidos_raw = ingest_chat()
        print(f"   {len(pedidos_raw)} tópicos raiz", flush=True)

        print("4/6 Ekyte (Rafael/Bruno + URLs do Chat)…", flush=True)
        known = ingest_executor_tasks()
        print(f"   {len(known)} tasks listadas dos executores", flush=True)
        token_index = unique_name_index(catalog)
        print(f"   {len(token_index)} frases de nome no índice", flush=True)
        enriched = [enrich_pedido(pedido, catalog, token_index) for pedido in pedidos_raw]
        task_ids = [tid for pedido in enriched for tid in pedido.get("task_ids") or []]
        tasks = ingest_ekyte_tasks(task_ids, known)
        print(f"   {len(task_ids)} URLs Ekyte no Chat · {len(tasks)} tasks resolvidas", flush=True)

        print("5/6 classificando sinais…", flush=True)
        web_users = set(config.get("web_cell_chat_users") or [])
        sla = int(config.get("sla_business_days") or 1)
        rows = []
        for pedido in enriched:
            task = None
            if pedido.get("task_ids"):
                task = tasks.get(str(pedido["task_ids"][0]))
            classified = classify_pedido(pedido, task, web_users, sla)
            rows.append(stamp_row(serialize_row(pedido, classified, task)))

        snapshot = {
            "generated_at_label": now_label(),
            "lookback_days": int(config["lookback_days"]),
            "gate_password": config["gate_password"],
            "spaces": [
                {"slug": s["slug"], "label": s["label"], "id": s["id"]}
                for s in config["spaces"]
            ],
            "flow_tickers": len(catalog),
            "pedidos": rows,
        }
        print("6/6 render HTML Colli…", flush=True)
        out = render(snapshot)
        print(f"gravado {out}", flush=True)
    elif not (OUTPUT / "index.html").exists():
        raise SystemExit("Não há snapshot. Rode sem --serve-only primeiro.")

    if args.no_serve:
        if not args.no_open:
            webbrowser.open((OUTPUT / "index.html").as_uri())
        return 0
    serve_radar(port, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
