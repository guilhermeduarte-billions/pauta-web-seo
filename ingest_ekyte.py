from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from mcp_clients import ekyte_client
from paths import load_config


def _as_list(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "tasks", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        nested = payload.get("task")
        if isinstance(nested, dict):
            return [nested]
    return []


def _normalize_task(payload: Any, fallback_id: int | str | None = None) -> dict:
    task = payload if isinstance(payload, dict) else {}
    for key in ("task", "data", "item"):
        nested = task.get(key)
        if isinstance(nested, dict) and (nested.get("id") or fallback_id):
            task = nested
            break
    if fallback_id and not task.get("id"):
        task["id"] = fallback_id
    return task


def ingest_executor_tasks(lookback_days: int | None = None) -> dict[str, dict]:
    config = load_config()
    days = lookback_days if lookback_days is not None else int(config["lookback_days"])
    start = (date.today() - timedelta(days=days)).isoformat()
    executor_ids = ",".join(
        str(info["id"]) for info in (config.get("ekyte") or {}).get("executors", {}).values()
    )
    found: dict[str, dict] = {}
    if not executor_ids:
        return found
    try:
        client = ekyte_client()
    except Exception as exc:
        print(f"aviso: Ekyte MCP indisponível ({exc})", flush=True)
        return found

    queries = [
        {"situation": "10,20", "creationDateStart": start},
        {"situation": "30", "concludedDateStart": start},
    ]
    for extra in queries:
        try:
            payload = client.call_tool(
                "list_tasks",
                {
                    "limit": 200,
                    "executorId": executor_ids,
                    "order": 50,
                    **extra,
                },
            )
        except Exception as exc:
            print(f"aviso: list_tasks {extra} falhou ({exc})", flush=True)
            continue
        for row in _as_list(payload):
            task = _normalize_task(row)
            tid = str(task.get("id") or "")
            if tid:
                found[tid] = task
    return found


def ingest_ekyte_tasks(task_ids: list[int], known: dict[str, dict] | None = None) -> dict[str, dict]:
    found = dict(known or {})
    missing = [tid for tid in sorted(set(task_ids)) if str(tid) not in found]
    if not missing:
        return found
    try:
        client = ekyte_client()
    except Exception as exc:
        print(f"aviso: Ekyte MCP indisponível ({exc})", flush=True)
        return found
    for task_id in missing:
        try:
            detail = client.call_tool("get_detailed_task", {"taskId": int(task_id)})
        except Exception as exc:
            print(f"aviso: get_detailed_task {task_id} falhou ({exc})", flush=True)
            continue
        task = _normalize_task(detail, task_id)
        if task.get("id"):
            found[str(task["id"])] = task
    return found
