from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.errors import HttpError

from auth import build_chat
from chat_api import normalize_space
from paths import load_config

BRT = timezone(timedelta(hours=-3))


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _sender(msg: dict) -> tuple[str, str]:
    sender = msg.get("sender") or {}
    uid = sender.get("name") or ""
    nome = (sender.get("displayName") or "").strip() or uid
    return uid, nome


def _list_page(service, space: str, page_token: str | None, lookback_iso: str) -> dict:
    kwargs: dict[str, Any] = {
        "parent": normalize_space(space),
        "pageSize": 200,
        "orderBy": "createTime desc",
    }
    if page_token:
        kwargs["pageToken"] = page_token
    try:
        kwargs["filter"] = f'createTime > "{lookback_iso}"'
        return service.spaces().messages().list(**kwargs).execute()
    except HttpError:
        kwargs.pop("filter", None)
        return service.spaces().messages().list(**kwargs).execute()


def _get_message(service, name: str) -> dict | None:
    try:
        return service.spaces().messages().get(name=name).execute()
    except HttpError:
        return None


def ingest_chat(lookback_days: int | None = None) -> list[dict]:
    config = load_config()
    days = lookback_days if lookback_days is not None else int(config["lookback_days"])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    lookback_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    service = build_chat(allow_interactive=False)

    threads: dict[str, dict] = {}
    for space in config["spaces"]:
        space_id = space["id"]
        page_token = None
        while True:
            resp = _list_page(service, space_id, page_token, lookback_iso)
            messages = resp.get("messages") or []
            if not messages:
                break
            stop = False
            for msg in messages:
                created = _parse_time(msg.get("createTime"))
                if created and created < cutoff:
                    stop = True
                    continue
                thread = (msg.get("thread") or {}).get("name") or ""
                if not thread:
                    continue
                bucket = threads.setdefault(
                    thread,
                    {
                        "thread": thread,
                        "space_id": space_id,
                        "space_slug": space["slug"],
                        "space_label": space["label"],
                        "messages": [],
                    },
                )
                bucket["messages"].append(msg)
            if stop or not resp.get("nextPageToken"):
                break
            page_token = resp.get("nextPageToken")

    pedidos = []
    for thread, bucket in threads.items():
        msgs = sorted(bucket["messages"], key=lambda m: m.get("createTime") or "")
        root = next((m for m in msgs if not m.get("threadReply")), None)
        if root is None:
            thread_id = thread.rsplit("/", 1)[-1]
            root_name = f"{bucket['space_id']}/messages/{thread_id}"
            fetched = _get_message(service, root_name)
            if fetched:
                root = fetched
                msgs = sorted([fetched] + msgs, key=lambda m: m.get("createTime") or "")
        if root is None:
            root = msgs[0]
        root_created = _parse_time(root.get("createTime"))
        if root_created and root_created < cutoff:
            # thread antiga com reply recente: ainda entra, usando o root real
            pass
        autor_id, autor_nome = _sender(root)
        textos = []
        for msg in msgs:
            text = (msg.get("text") or "").strip()
            if text:
                textos.append(text)
        pedidos.append(
            {
                "thread": thread,
                "space_id": bucket["space_id"],
                "canal": bucket["space_slug"],
                "canal_label": bucket["space_label"],
                "root": root,
                "messages": msgs,
                "created_at": root.get("createTime"),
                "autor_id": autor_id,
                "autor_nome": autor_nome,
                "textos": textos,
                "trecho": (root.get("text") or "sem texto").strip()[:280],
            }
        )
    pedidos.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return pedidos
