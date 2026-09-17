from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from paths import load_config, load_pessoas

BRT = timezone(timedelta(hours=-3))
EKYTE_RE = re.compile(
    r"app\.ekyte\.com/(?:#/)?tasks(?:/list)?/(\d+)",
    re.IGNORECASE,
)
TICKER_RE = re.compile(r"\[([A-Z0-9]{2,8})\]")


def load_roster_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for bloco in load_pessoas():
        slug = bloco.get("slug")
        chat_user = bloco.get("chat_user")
        info = {
            "slug": slug,
            "nome": bloco.get("nome"),
            "coordenacao": bloco.get("coordenacao") or "nao_mapeado",
            "papel": bloco.get("papel") or "ops",
        }
        if chat_user:
            index[chat_user] = info
        if slug:
            index[f"slug:{slug}"] = info
    return index


def extract_task_ids(textos: list[str]) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for texto in textos:
        for match in EKYTE_RE.finditer(texto or ""):
            task_id = int(match.group(1))
            if task_id not in seen:
                seen.add(task_id)
                ids.append(task_id)
    return ids


SKIP_TICKERS = {"COLLI", "WEB", "SEO", "IA", "CC", "BILLIONS", "V4", "HTML", "GEO"}


def extract_tickers(
    textos: list[str],
    catalog_keys: list[str] | None = None,
    root_text: str | None = None,
) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    blob = "\n".join(textos or [])
    for match in TICKER_RE.finditer(blob.upper()):
        ticker = match.group(1).upper()
        if ticker in SKIP_TICKERS or ticker in seen:
            continue
        seen.add(ticker)
        found.append(ticker)
    if catalog_keys:
        long_blob = blob
        short_blob = root_text if root_text is not None else blob
        for key in catalog_keys:
            ticker = (key or "").upper()
            if not ticker or ticker in SKIP_TICKERS or ticker in seen:
                continue
            hay = short_blob if len(ticker) <= 3 else long_blob
            if re.search(rf"(?<![A-Za-z0-9/]){re.escape(ticker)}(?![A-Za-z0-9])", hay or "", re.IGNORECASE):
                seen.add(ticker)
                found.append(ticker)
    return found


def add_business_days(start: datetime, days: int) -> datetime:
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def first_web_reply(pedido: dict, web_users: set[str]) -> dict | None:
    autor = pedido.get("autor_id")
    for msg in pedido.get("messages") or []:
        if not msg.get("threadReply"):
            continue
        sender = (msg.get("sender") or {}).get("name") or ""
        if sender == autor:
            continue
        if sender in web_users:
            return msg
    return None


def chat_url(space_id: str, thread: str) -> str:
    space = space_id.split("/")[-1]
    thread_id = thread.split("/")[-1]
    return f"https://chat.google.com/room/{space}/{thread_id}/{thread_id}"


def ekyte_url(task_id: int | str) -> str:
    return f"https://app.ekyte.com/#/tasks/list/{task_id}/edit"


def parse_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    return text[:10] if len(text) >= 10 else None


def classify_pedido(pedido: dict, task: dict | None, web_users: set[str], sla_days: int) -> dict:
    raw_created = (pedido.get("created_at") or "").replace("Z", "+00:00")
    try:
        created = datetime.fromisoformat(raw_created) if raw_created else datetime.now(timezone.utc)
    except ValueError:
        created = datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    deadline = add_business_days(created.astimezone(BRT), sla_days)
    reply = first_web_reply(pedido, web_users)
    respondida_em = None
    respondida = False
    if reply:
        respondida_em = reply.get("createTime")
        reply_dt = datetime.fromisoformat((respondida_em or "").replace("Z", "+00:00"))
        if reply_dt.tzinfo is None:
            reply_dt = reply_dt.replace(tzinfo=timezone.utc)
        respondida = reply_dt.astimezone(BRT) <= deadline

    encaminhada = bool(task and task.get("id"))
    executor = "sem_task"
    prazo = None
    concluida_em = None
    situation = None
    if task:
        prazo = parse_date(task.get("currentDueDate"))
        concluida_em = parse_date(task.get("concludedDate"))
        situation = task.get("situation")
        if isinstance(situation, dict):
            situation = situation.get("id") or situation.get("code") or situation.get("value")
        try:
            situation = int(situation) if situation is not None else None
        except (TypeError, ValueError):
            situation = None
        raw_exec = task.get("executor")
        if isinstance(raw_exec, dict):
            executor_id = raw_exec.get("id") or raw_exec.get("userId")
        else:
            executor_id = raw_exec or task.get("executorId")
        config = load_config()
        for slug, info in (config.get("ekyte") or {}).get("executors", {}).items():
            if str(info.get("id")) == str(executor_id or ""):
                executor = slug
                break
        else:
            if encaminhada:
                executor = "outro"

    today = datetime.now(BRT).date().isoformat()
    if encaminhada:
        concluded = situation == 30 or bool(concluida_em)
        if concluded:
            if prazo and concluida_em and concluida_em <= prazo:
                estado = "concluida_no_prazo"
            else:
                estado = "concluida_fora"
        elif prazo and today > prazo:
            estado = "task_atrasada"
        else:
            estado = "task_no_prazo"
    elif respondida:
        estado = "respondida_sem_task"
    else:
        estado = "sem_resposta"

    sem_task = not encaminhada
    atrasada = estado == "task_atrasada"
    pauta = sem_task or atrasada or not respondida
    if sem_task:
        gravidade = 0
    elif atrasada:
        gravidade = 1
    elif not respondida:
        gravidade = 2
    else:
        gravidade = 9

    return {
        "respondida": respondida,
        "respondida_em": respondida_em,
        "encaminhada": encaminhada,
        "prazo": prazo,
        "concluida_em": concluida_em,
        "estado": estado,
        "executor": executor,
        "pauta": pauta and estado not in {"concluida_no_prazo", "task_no_prazo"},
        "gravidade": gravidade,
    }
