# Setup — Pauta WEB/SEO

Do zero até o painel abrir no browser. Conta **sua** (Gustavo / quem for operar). Sem token de outra pessoa.

Tempo honesto: 20–40 min na primeira vez (a maior parte é o Google Cloud). Depois é `python3 run.py`.

Você precisa:

- Python 3.10 ou mais novo (`python3 --version`)
- Navegador
- Login `…@v4company.com` no Google
- Ser membro dos canais `[Colli&Co] Suporte WEB/SEO` e `[Colli&Co] CC Web/SEO`
- Acesso ao Ekyte da Colli

---

## 0. Clonar e instalar Python

No Cursor / VS Code / terminal:

```bash
git clone https://github.com/guilhermeduarte-billions/pauta-web-seo.git
cd pauta-web-seo
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Abra a pasta no Cursor: **File → Open Folder → pauta-web-seo**.

O `.env` ainda está vazio. Não rode `run.py` agora.

---

## 1. Google Cloud — projeto e API do Chat

O painel lê as mensagens dos canais com a **Google Chat API**, autenticado como você (OAuth de usuário). Não é bot. Não posta nada.

### 1.1 Criar o projeto

1. Abra [console.cloud.google.com](https://console.cloud.google.com/) com a conta Colli.
2. Se o Google pedir organização, escolha a da V4/Colli.
3. Canto superior: seletor de projeto → **New project**.
4. Nome: `pauta-web-seo` (ou outro). Create.

### 1.2 Ligar a API

1. No projeto novo: **APIs & Services → Library**.
2. Busque **Google Chat API**.
3. Abra o card e clique **Enable**.

Sem isso o OAuth passa e a leitura dos canais quebra com 403.

### 1.3 Tela de permissão OAuth (consent screen)

Caminho atual no Console: **APIs & Services → OAuth consent screen** (às vezes aparece como **Google Auth platform**).

1. User type: **Internal** (só gente do Workspace V4). Se Internal não aparecer, a conta não está no Workspace certo — troca para `v4company.com` e tenta de novo.
2. App name: `Pauta WEB/SEO`.
3. User support email: o seu.
4. Developer contact: o seu.
5. Save.

**Scopes (Acesso a dados):** adicione estes dois, e só estes:

- `https://www.googleapis.com/auth/chat.spaces.readonly`
- `https://www.googleapis.com/auth/chat.messages.readonly`

São leitura de espaços e de mensagens. Sem `chat.messages` o ingest volta vazio. Sem `chat.spaces` o `doctor.py` não confirma o canal.

### 1.4 Cliente OAuth Desktop

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**.
3. Name: `pauta-web-seo-desktop`.
4. Create.
5. **Download JSON**.
6. Salve o arquivo neste repo, exatamente aqui:

```text
pauta-web-seo/credentials/oauth_client.json
```

Pode se chamar `client_secret_….json` no download — renomeie para `oauth_client.json`.

Esse JSON identifica o *app*. Ainda não é o seu login. O login vem no passo 3.

### 1.5 Configuração do app Chat (página da própria API)

1. **APIs & Services → Google Chat API → Configuration** (ou **Google Chat API → Manage → Configuration**).
2. App name: `Pauta WEB/SEO`.
3. Avatar: opcional.
4. Description: `Leitura dos canais WEB/SEO para a pauta. Não envia mensagem.`
5. Functionality: pode deixar **sem** interactive features (não precisa de comando slash nem DM do app).
6. Visibility: o Workspace da Colli / V4.
7. App status: **Live** (ou habilitado para a organização).
8. Save.

Se esta tela pedir “Interactive features” obrigatório, ligue o mínimo e **não** marque receber mensagem 1:1. O script usa credencial de usuário, não webhook.

---

## 2. Autorizar a sua conta no Chat

No terminal, **dentro da pasta do repo**:

```bash
python3 setup_auth.py
```

O navegador abre. Entre com a **mesma conta** que você usa no Google Chat da Colli. Aceite os dois scopes de leitura.

Isso grava `credentials/token.json` na sua máquina. Não commite. Se outra pessoa for usar o painel, ela roda o `setup_auth.py` de novo, com a conta dela.

Erro comum: “access_denied” / scope não concedido → o scope não está na tela OAuth do projeto (passo 1.3).

Erro “redirect_uri_mismatch” → o cliente não é Desktop; apague e crie de novo como Desktop app.

---

## 3. Entrar nos canais

A API só lê espaço do qual **você é membro**.

Confira no Chat:

- `[Colli&Co] Suporte WEB/SEO`
- `[Colli&Co] CC Web/SEO`

Os IDs já estão em `config.yaml`. Se o `doctor.py` disser HTTP 403/404 no canal, você não está nele — pede para te adicionarem; não adianta copiar token.

---

## 4. Token MCP do Ekyte

O painel lista as tasks do Rafael/Bruno e, no botão **Subir no Ekyte**, cria a demanda.

1. Entre no Ekyte da Colli com o **seu** usuário.
2. Abra **Configurações** (cadastro do usuário, não a tela do projeto).
3. Copie o **token MCP** (documentação: [developers.ekyte.com/docs/mcp](https://developers.ekyte.com/docs/mcp/)).
4. No `.env` da pasta do repo:

```bash
EKYTE_MCP_TOKEN=cole_aqui_sem_aspas
```

Não cole o token do Guilherme, nem o `mcp.json` da máquina dele. O Ekyte registra quem criou a task; tem que ser você.

O botão de criar task precisa de permissão de criar no workspace do cliente. Se o Ekyte recusar, é perfil — não é bug do painel.

---

## 5. FLOW (opcional)

O match de cliente (ticker / nome tipo “Maidpad”) já vem com `data/flow-tickers.json`.

Se você tiver JWT do Cockpit FLOW, pode atualizar o catálogo a cada `run.py`. No `.env`:

```bash
FLOW_MCP_JWT=
FLOW_MCP_GATEWAY=
```

Sem isso o painel ainda abre. Só não refresca gerência/coord de cliente novo.

`EKYTE_COLLI_URL` / `EKYTE_COLLI_TOKEN` também são opcionais (atalho para achar workspace pelo ticker). Sem eles, o botão busca o workspace pelo nome no Ekyte oficial.

---

## 6. Conferir e abrir

```bash
python3 doctor.py
python3 run.py
```

O `doctor.py` testa Python, OAuth, se você lê os dois canais, e se o Ekyte responde.

`run.py` gera o HTML, sobe `http://127.0.0.1:8768/` e abre o browser.

Senha do painel: `v4v4v4xablau` (troque em `config.yaml` se quiser). Fica no `sessionStorage` deste endereço local.

---

## 7. Uso no dia a dia

| Comando | O que faz |
|---|---|
| `python3 run.py` | ingest Chat + Ekyte, render, serve |
| `python3 run.py --serve-only` | só reabre o último snapshot |
| `python3 run.py --no-open` | serve sem abrir o browser |

Pauta = sem task, atrasada ou sem 1ª resposta. **Subir no Ekyte** fecha o loop no Ekyte. **Ignorar** tira o que já foi resolvido. Os ignorados ficam em `state/` na sua máquina.

Não há FUP automático no Chat.

---

## Problemas frequentes

| Sintoma | Causa típica |
|---|---|
| `oauth_client.json` não encontrado | arquivo no lugar errado ou nome diferente |
| Token sem scopes | `setup_auth.py` de novo depois de incluir os scopes no Console |
| HTTP 403 no canal | conta do OAuth ≠ membro do espaço |
| Chat ingest 0 tópicos | scope `chat.messages.readonly` faltando, ou lookback/canal errado |
| Ekyte 401 | token MCP errado / expirado |
| Botão Subir não cria | `run.py` tem que estar servindo localhost; `file://` só mostra o HTML |
| Workspace não encontrado | ticker/nome vazios no pedido, ou você não vê o workspace no Ekyte |

Python no Mac: se `python3` for 3.9, instale 3.12+ com `brew install python` e use `python3.12`.

---

## O que este repo de propósito não tem

- Token OAuth de outra pessoa
- `~/.cursor/mcp.json` do Guilherme
- `~/.config/colli/mcp.env`
- Snapshot de Chat (`output/` é local e gitignored)
- Envio de mensagem no Google Chat
