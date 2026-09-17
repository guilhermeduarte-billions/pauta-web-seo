from __future__ import annotations

from pathlib import Path

from paths import OAUTH_CLIENT, OAUTH_TOKEN

# Só leitura. Este painel não posta no Google Chat.
SCOPES = (
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.messages.readonly",
)


class ChatAuthError(RuntimeError):
    pass


def missing_scopes(creds) -> list[str]:
    granted = set(creds.scopes or [])
    return [scope for scope in SCOPES if scope not in granted]


def get_credentials(*, allow_interactive: bool = True):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise ChatAuthError(
            "Dependências Google ausentes. Rode: python3 -m pip install -r requirements.txt"
        ) from exc

    creds = None
    if OAUTH_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(OAUTH_TOKEN), list(SCOPES))

    if creds and not missing_scopes(creds):
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            OAUTH_TOKEN.write_text(creds.to_json(), encoding="utf-8")
            return creds

    if not allow_interactive:
        faltando = missing_scopes(creds) if creds else list(SCOPES)
        raise ChatAuthError(
            "Token do Google Chat ausente ou incompleto.\n"
            "Rode: python3 setup_auth.py\n"
            "Faltando:\n  " + "\n  ".join(faltando)
        )

    if not OAUTH_CLIENT.exists():
        raise ChatAuthError(
            f"OAuth client não encontrado em {OAUTH_CLIENT}.\n"
            "Baixe o JSON do cliente Desktop no Google Cloud e salve nesse caminho.\n"
            "Passo a passo: SETUP.md, seção Google Cloud."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CLIENT), list(SCOPES))
    for section in ("installed", "web"):
        if section in flow.client_config and "client_secret" not in flow.client_config[section]:
            flow.client_config[section]["client_secret"] = ""
    creds = flow.run_local_server(port=0, prompt="consent")
    OAUTH_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    OAUTH_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_chat(*, allow_interactive: bool = False):
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ChatAuthError("google-api-python-client ausente. Instale requirements.txt.") from exc

    creds = get_credentials(allow_interactive=allow_interactive)
    return build("chat", "v1", credentials=creds, cache_discovery=False)
