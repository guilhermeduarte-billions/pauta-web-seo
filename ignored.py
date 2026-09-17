from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from paths import ROOT

BRT = timezone(timedelta(hours=-3))
STATE_DIR = ROOT / "state"
IGNORED_PATH = STATE_DIR / "ignored.json"

MOTIVOS = {
    "ja_resolvido": "Já resolvido",
    "nao_e_web": "Não é demanda WEB",
    "duplicado": "Duplicado",
    "outro": "Outro",
}


def load_ignored() -> dict:
    if not IGNORED_PATH.exists():
        return {"threads": {}}
    try:
        data = json.loads(IGNORED_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"threads": {}}
    threads = data.get("threads")
    if not isinstance(threads, dict):
        threads = {}
    return {"threads": threads}


def save_ignored(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    IGNORED_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def motivo_label(key: str) -> str:
    return MOTIVOS.get(key) or MOTIVOS["ja_resolvido"]


def apply_ignore(row: dict, record: dict | None = None) -> dict:
    row = dict(row)
    record = record or {}
    origem = row.get("estado_origem") or row.get("estado")
    if origem == "ignorado":
        origem = None
    row["ignorado"] = True
    row["estado_origem"] = origem
    row["estado"] = "ignorado"
    row["pauta"] = False
    row["gravidade"] = 9
    row["ignorado_em"] = record.get("at")
    row["ignorado_motivo"] = record.get("motivo") or "ja_resolvido"
    row["ignorado_motivo_label"] = motivo_label(row["ignorado_motivo"])
    return row


def clear_ignore(row: dict) -> dict:
    row = dict(row)
    origem = row.get("estado_origem")
    row["ignorado"] = False
    row["ignorado_em"] = None
    row["ignorado_motivo"] = None
    row["ignorado_motivo_label"] = None
    if origem and origem != "ignorado":
        row["estado"] = origem
        row["pauta"] = origem in {"sem_resposta", "respondida_sem_task", "task_atrasada"}
        if origem in {"sem_resposta", "respondida_sem_task"}:
            row["gravidade"] = 0
        elif origem == "task_atrasada":
            row["gravidade"] = 1
        else:
            row["gravidade"] = 9
    row["estado_origem"] = None
    return row


def stamp_row(row: dict, ignored: dict | None = None) -> dict:
    ignored = ignored or load_ignored()
    thread = row.get("thread")
    record = (ignored.get("threads") or {}).get(thread) if thread else None
    if record:
        return apply_ignore(row, record)
    if row.get("ignorado"):
        return clear_ignore(row)
    row = dict(row)
    row.setdefault("ignorado", False)
    return row


def stamp_snapshot(snapshot: dict, ignored: dict | None = None) -> dict:
    ignored = ignored or load_ignored()
    snapshot = dict(snapshot)
    snapshot["pedidos"] = [stamp_row(row, ignored) for row in snapshot.get("pedidos") or []]
    return snapshot


def ignore_thread(thread: str, row: dict, motivo: str = "ja_resolvido") -> dict:
    motivo = motivo if motivo in MOTIVOS else "ja_resolvido"
    data = load_ignored()
    record = {
        "at": datetime.now(BRT).isoformat(timespec="seconds"),
        "motivo": motivo,
        "ticker": row.get("ticker"),
        "cliente": row.get("cliente"),
        "trecho": (row.get("trecho") or "")[:180],
    }
    data["threads"][thread] = record
    save_ignored(data)
    return record


def unignore_thread(thread: str) -> None:
    data = load_ignored()
    data.get("threads", {}).pop(thread, None)
    save_ignored(data)
