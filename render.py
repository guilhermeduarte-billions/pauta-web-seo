from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paths import ASSETS, ASSETS_SRC, OUTPUT, ROOT, ensure_output

BRT = timezone(timedelta(hours=-3))
TEMPLATE = ROOT / "template.html"


def _copy_logos() -> None:
    ensure_output()
    for name in ("colli-red.png", "colli-white.png"):
        src = ASSETS_SRC / name
        if src.exists():
            shutil.copy2(src, ASSETS / name)


def render(snapshot: dict) -> Path:
    _copy_logos()
    html = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    payload = (
        payload.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("</", "<\\/")
    )
    html = html.replace("__SNAPSHOT__", payload)
    html = html.replace("__PASSWORD__", snapshot["gate_password"])
    html = html.replace("__GENERATED__", snapshot["generated_at_label"])
    out = OUTPUT / "index.html"
    out.write_text(html, encoding="utf-8")
    (OUTPUT / "snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out


def now_label() -> str:
    return datetime.now(BRT).strftime("%d/%m/%Y %H:%M")
