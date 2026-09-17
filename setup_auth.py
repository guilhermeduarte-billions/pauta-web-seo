#!/usr/bin/env python3
"""Abre o navegador para autorizar leitura do Google Chat com A SUA conta.

Gera credentials/token.json. Não usa token de outra pessoa.
"""
from __future__ import annotations

import sys

from auth import ChatAuthError, get_credentials
from paths import OAUTH_CLIENT, OAUTH_TOKEN


def main() -> int:
    print("Pauta WEB/SEO — autorização Google Chat (só leitura)")
    print(f"Cliente OAuth: {OAUTH_CLIENT}")
    print(f"Token vai para: {OAUTH_TOKEN}")
    print()
    if not OAUTH_CLIENT.exists():
        print(
            f"ERRO: não achei {OAUTH_CLIENT}.\n"
            "Siga o SETUP.md até baixar o JSON do cliente Desktop e salvar nesse arquivo.",
            file=sys.stderr,
        )
        return 1
    print("O navegador vai abrir. Entre com a conta que você usa no Google Chat da Colli.")
    print("Aceite os dois scopes de LEITURA (espaços e mensagens). Nada é postado.\n")
    try:
        creds = get_credentials(allow_interactive=True)
    except ChatAuthError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    scopes = list(creds.scopes or [])
    print(f"OK. Token gravado com {len(scopes)} scope(s).")
    print("Próximo: python3 doctor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
