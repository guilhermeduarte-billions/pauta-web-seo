# Pauta WEB/SEO

Painel local (HTML Colli) da fila dos canais Google Chat **Suporte WEB/SEO** e **CC Web/SEO**, cruzada com tasks do Ekyte.

Não posta no Chat. Operação WEB é PJ: cobrança humana. O painel só lê o Chat, lista o Ekyte e — se você clicar — sobe a task ou ignora o pedido.

Setup do zero (Google Cloud, OAuth, Ekyte, `.env`): **[SETUP.md](SETUP.md)**.

## Depois do setup

```bash
python3 doctor.py
python3 run.py
```

Abre `http://127.0.0.1:8768/`. Senha do gate: a de `config.yaml` (`gate_password`).

- **Subir no Ekyte** — cria `[01][WEB] Cliente | Demanda` no workspace do cliente
- **Ignorar** — tira da pauta o que já foi resolvido (fica em `state/ignored.json`)

`Ctrl+C` para o servidor.

## O que o painel mede

| Sinal | Regra |
|---|---|
| Pedido | tópico raiz da thread (45 dias) |
| Respondida | reply de Rafael, Bruno ou Gustavo em até 1 dia útil |
| Encaminhada | URL `app.ekyte.com/.../tasks/{id}` em alguma mensagem |
| OTIF | `concludedDate` ≤ `currentDueDate` |
| Cliente | ticker `[ABCD]` ou nome do projeto no título/corpo |

## Sem os tokens de outra pessoa

OAuth, token do Chat e token do Ekyte são **da sua conta**, na sua máquina:

- `credentials/oauth_client.json` — JSON Desktop que você baixa no Google Cloud
- `credentials/token.json` — gerado por `python3 setup_auth.py`
- `.env` — `EKYTE_MCP_TOKEN` (e FLOW, se quiser)

Nada disso vai para o Git.

## Requisitos

- Python 3.10+
- Conta Google da Colli, membro dos dois canais WEB/SEO
- Usuário Ekyte com permissão de criar task WEB
- Cursor, VS Code ou terminal (não precisa do Brain do Guilherme)
