from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any

from match import add_business_days, ekyte_url
from mcp_clients import JsonRpcClient, McpError, ekyte_client, ekyte_colli_client
from paths import load_config

BRT = timezone(timedelta(hours=-3))
WEB_TYPE_ID_DEFAULT = 79514
WEB_TYPE_NEEDLE = "Solicitação Web"


class CreateEkyteError(RuntimeError):
    pass


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()


def _as_list(payload: Any) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "workspaces", "projects", "result", "value"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _iso_day(value: date | datetime) -> str:
    if isinstance(value, datetime):
        value = value.date()
    return f"{value.isoformat()}T00:00:00"


def _add_bd(start: date, days: int) -> date:
    if days <= 0:
        return start
    dt = datetime.combine(start, datetime.min.time(), tzinfo=BRT)
    return add_business_days(dt, days).date()


def _demanda(row: dict) -> str:
    blob = (row.get("trecho") or row.get("body") or "").strip()
    line = re.split(r"[\n\r]+", blob)[0]
    line = re.sub(r"https?://\S+", "", line)
    line = re.sub(r"\s+", " ", line).strip(" .-|")
    if len(line) > 90:
        line = line[:87].rstrip() + "…"
    return line or "Solicitação WEB"


def _cliente_label(row: dict) -> str:
    nome = (row.get("cliente") or "").strip()
    if nome and nome.lower() not in {"nao_classificado", "não classificado", "-"}:
        return nome
    ticker = (row.get("ticker") or "").strip()
    return ticker or "Cliente"


def _task_title(row: dict) -> str:
    return f"[01][WEB] {_cliente_label(row)} | {_demanda(row)}"


def _briefing(row: dict, workspace_name: str, due: date) -> str:
    cliente = _cliente_label(row)
    autor = row.get("autor_nome") or ""
    canal = row.get("canal_label") or ""
    chat = row.get("chat_url") or ""
    ticker = row.get("ticker") or "sem ticker"
    body = (row.get("body") or row.get("trecho") or "").strip()
    if len(body) > 2500:
        body = body[:2497].rstrip() + "…"
    body_html = (
        body.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    due_br = due.strftime("%d/%m/%Y")
    today_br = date.today().strftime("%d/%m/%Y")
    return (
        "<div><b>BRIEFING - SOLICITAÇÃO DE AJUSTE WEB</b><br><br>"
        f"<b>Origem:</b> Pauta WEB/SEO (Chat × Ekyte)<br>"
        f"Cliente: {cliente} ({ticker})<br>"
        f"Workspace: {workspace_name}<br>"
        f"Canal: {canal}<br>"
        f"Solicitante: {autor}<br>"
        f"Data da solicitação: {today_br}<br>"
        f"Data de entrega sugerida: {due_br}<br>"
        f'Thread: <a href="{chat}">{chat}</a><br><br>'
        "<b>1) SOLICITAÇÃO</b><br>"
        f"{_demanda(row)}<br><br>"
        "<b>2) DESCRIÇÃO</b><br>"
        f"{body_html}<br><br>"
        "<b>3) ANEXOS E PRINTS</b><br>"
        "Ver thread no Google Chat (link acima). Esta task não dispara mensagem no Chat."
        "</div>"
    )


def _score_workspace(ws: dict, ticker: str, cliente: str) -> int:
    name = _fold(ws.get("name") or "")
    if not name:
        return -1
    score = 0
    t = _fold(ticker)
    c = _fold(cliente)
    if t and t in name.split():
        score += 20
    elif t and t in name:
        score += 12
    if c and len(c) >= 4 and c in name:
        score += 10
    if c and len(name) >= 4 and name in c:
        score += 6
    return score


def _search_workspaces(client: JsonRpcClient, query: str) -> list[dict]:
    if not query or len(query.strip()) < 2:
        return []
    payload = client.call_tool(
        "list_short_workspaces",
        {"textKey": 20, "textSearch": query.strip(), "active": 1},
    )
    return [item for item in _as_list(payload) if isinstance(item, dict)]


def _localize_workspace(ticker: str, cliente: str) -> dict | None:
    try:
        colli = ekyte_colli_client()
    except McpError:
        return None
    search = ticker or cliente
    if not search:
        return None
    try:
        payload = colli.call_tool(
            "localize_project",
            {
                "integration_slug": "ekyte",
                "limit": "8",
                "only_with_integrations": "true",
                "search_text": search,
            },
        )
    except McpError:
        return None
    rows = _as_list(payload)
    if isinstance(payload, dict) and not rows:
        rows = [payload]
    best = None
    best_score = -1
    for row in rows:
        if not isinstance(row, dict):
            continue
        ws_id = row.get("ekyte_workspace_id") or row.get("workspace_id")
        if not ws_id:
            continue
        row_ticker = str(row.get("project_ticker") or "").upper()
        score = 0
        if ticker and row_ticker == ticker.upper():
            score += 30
        name = str(row.get("project_name") or "")
        score += _score_workspace({"name": name}, ticker, cliente)
        if score > best_score:
            best_score = score
            best = {
                "id": int(str(ws_id).split(",")[0]),
                "name": name or f"workspace {ws_id}",
            }
    return best if best_score >= 0 else None


def find_workspace(client: JsonRpcClient, row: dict) -> dict:
    ticker = (row.get("ticker") or "").strip()
    cliente = _cliente_label(row)
    queries = []
    for item in (ticker, cliente):
        if item and item not in queries and item != "Cliente":
            queries.append(item)
    if cliente and " " in cliente:
        first = cliente.split()[0]
        if len(first) >= 4 and first not in queries:
            queries.append(first)
    scored: list[tuple[int, dict]] = []
    seen: set[int] = set()
    for query in queries:
        for ws in _search_workspaces(client, query):
            ws_id = ws.get("id")
            if not ws_id or int(ws_id) in seen:
                continue
            seen.add(int(ws_id))
            score = _score_workspace(ws, ticker, cliente)
            if score > 0:
                scored.append((score, ws))
    if scored:
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_score = scored[0][0]
        tied = [ws for score, ws in scored if score == top_score]
        if len(tied) > 1 and ticker:
            needle = ticker.upper()
            exact = [ws for ws in tied if needle in str(ws.get("name") or "").upper()]
            if len(exact) == 1:
                tied = exact
        if len(tied) > 1:
            names = ", ".join(str(ws.get("name") or ws.get("id")) for ws in tied[:4])
            raise CreateEkyteError(
                f"Vários workspaces possíveis ({names}). Confirme ticker/nome no pedido."
            )
        top = tied[0]
        return {"id": int(top["id"]), "name": top.get("name") or str(top["id"])}
    localized = _localize_workspace(ticker, cliente if cliente != "Cliente" else "")
    if localized:
        return localized
    raise CreateEkyteError(
        "Não achei workspace Ekyte deste cliente. Confira ticker/nome ou suba a task na mão."
    )


def _resolve_task_type(client: JsonRpcClient, workspace_id: int, configured_id: int) -> tuple[int, dict]:
    try:
        flow = client.call_tool(
            "get_task_type_flow",
            {"id": configured_id, "workspaceId": workspace_id},
        )
        if isinstance(flow, dict) and flow.get("flowPhases"):
            return configured_id, flow
    except McpError:
        flow = None
    payload = client.call_tool(
        "list_task_types_create_task",
        {"textKey": 20, "textSearch": WEB_TYPE_NEEDLE},
    )
    for item in _as_list(payload):
        name = str(item.get("name") or "")
        if "solicitacao web" in _fold(name) or "solicitação web" in name.lower():
            type_id = int(item["id"])
            flow = client.call_tool(
                "get_task_type_flow",
                {"id": type_id, "workspaceId": workspace_id},
            )
            if isinstance(flow, dict):
                return type_id, flow
    raise CreateEkyteError("Tipo [01][IA] Solicitação Web não está disponível neste workspace.")


def _build_flow(
    flow_payload: dict, type_id: int, executor_id: str, start: date
) -> tuple[list[dict], int, date, date, int]:
    phases = sorted(
        [p for p in (flow_payload.get("flowPhases") or []) if isinstance(p, dict)],
        key=lambda p: int(p.get("sequential") or 0),
    )
    if not phases:
        raise CreateEkyteError("Fluxo do tipo WEB veio sem etapas.")
    cursor = start
    items: list[dict] = []
    first_due = start
    last_active_due = start
    first_phase_id = None
    estimated = 0
    saw_active = False
    for phase in phases:
        duration = int(phase.get("duration") or 0)
        effort = int(phase.get("effort") or 0)
        active = int(phase.get("active") or 0)
        phase_id = int(phase.get("phaseId") or (phase.get("phase") or {}).get("id") or 0)
        if not phase_id:
            continue
        phase_start = cursor
        phase_due = _add_bd(phase_start, duration) if duration else phase_start
        items.append(
            {
                "active": active,
                "effort": effort,
                "executorId": executor_id,
                "phaseId": phase_id,
                "sequential": int(phase.get("sequential") or len(items) + 1),
                "taskTypeId": type_id,
                "phaseStartDate": _iso_day(phase_start),
                "phaseDueDate": _iso_day(phase_due),
            }
        )
        if active:
            if not saw_active:
                first_phase_id = phase_id
                first_due = phase_due
                saw_active = True
            last_active_due = phase_due
            estimated += effort
        cursor = phase_due
    if not first_phase_id:
        raise CreateEkyteError("Fluxo WEB sem etapa ativa.")
    return items, first_phase_id, first_due, last_active_due, max(estimated, 60)


def _executor(config: dict, key: str) -> tuple[str, str]:
    executors = (config.get("ekyte") or {}).get("executors") or {}
    slug = (key or "rafael").strip().lower()
    if slug not in executors:
        raise CreateEkyteError("Executor inválido. Use Rafael ou Bruno.")
    block = executors[slug]
    return str(block["id"]), str(block.get("nome") or slug)


def _extract_created_id(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("id", "taskId", "ctcTaskId"):
            if payload.get(key):
                return int(payload[key])
        nested = payload.get("data") or payload.get("task") or {}
        if isinstance(nested, dict) and nested.get("id"):
            return int(nested["id"])
        text = payload.get("text") or ""
        match = re.search(r"\b(\d{6,})\b", str(text))
        if match:
            return int(match.group(1))
    raise CreateEkyteError(f"Ekyte criou a task, mas não devolveu o ID: {payload!r}"[:400])


def create_web_task(row: dict, executor_key: str, due: date | None = None) -> dict:
    if row.get("encaminhada") and row.get("task_id"):
        return {
            "created": False,
            "already": True,
            "task_id": row["task_id"],
            "task_url": row.get("task_url") or ekyte_url(row["task_id"]),
            "title": row.get("task_title") or "",
        }
    config = load_config()
    ekyte_cfg = config.get("ekyte") or {}
    type_id = int(ekyte_cfg.get("web_task_type_id") or WEB_TYPE_ID_DEFAULT)
    default_days = int(ekyte_cfg.get("default_due_business_days") or 4)
    executor_id, executor_nome = _executor(config, executor_key)
    start = date.today()
    target_due = due or _add_bd(start, default_days)
    if target_due < start:
        raise CreateEkyteError("Prazo não pode ser no passado.")

    client = ekyte_client()
    workspace = find_workspace(client, row)
    type_id, flow_payload = _resolve_task_type(client, workspace["id"], type_id)
    flow, phase_id, first_due, last_due, estimated = _build_flow(
        flow_payload, type_id, executor_id, start
    )
    if target_due > last_due:
        last_due = target_due
        if flow:
            flow[-1]["phaseDueDate"] = _iso_day(last_due)

    payload = {
        "title": _task_title(row),
        "description": _briefing(row, workspace["name"], last_due),
        "phaseStartDate": _iso_day(start),
        "phaseDueDate": _iso_day(first_due),
        "currentDueDate": _iso_day(last_due),
        "originalDueDate": _iso_day(last_due),
        "estimatedTime": estimated,
        "workspaceId": workspace["id"],
        "executorId": executor_id,
        "phaseId": phase_id,
        "ctcTaskTypeId": type_id,
        "situation": 10,
        "allocationType": 20,
        "priority": 300,
        "quantity": 0,
        "recurring": 0,
        "updateFlow": True,
        "flow": flow,
    }
    try:
        created = client.call_tool("create_task", payload)
    except McpError as exc:
        raise CreateEkyteError(f"Ekyte recusou a criação: {exc}") from exc
    task_id = _extract_created_id(created)
    return {
        "created": True,
        "already": False,
        "task_id": task_id,
        "task_url": ekyte_url(task_id),
        "title": payload["title"],
        "workspace_id": workspace["id"],
        "workspace_name": workspace["name"],
        "executor": executor_nome,
        "prazo": last_due.isoformat(),
    }


def apply_created_to_row(row: dict, result: dict) -> dict:
    row = dict(row)
    row["encaminhada"] = True
    row["task_id"] = result["task_id"]
    row["task_url"] = result["task_url"]
    row["task_title"] = result.get("title")
    row["prazo"] = result.get("prazo") or row.get("prazo")
    row["executor"] = (result.get("executor") or "").split()[0].lower() if result.get("executor") else row.get("executor")
    if result.get("executor"):
        nome = result["executor"].lower()
        if "rafael" in nome:
            row["executor"] = "rafael"
        elif "bruno" in nome:
            row["executor"] = "bruno"
    row["estado"] = "task_no_prazo"
    row["pauta"] = False
    row["gravidade"] = 9
    return row
