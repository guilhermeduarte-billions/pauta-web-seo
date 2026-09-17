from __future__ import annotations

import re
import unicodedata

from match import extract_task_ids, extract_tickers, load_roster_index
from paths import load_coord_map

NAME_STOP = {
    "website", "landing", "importadora", "logistica", "revestimentos", "pisos",
    "consultoria", "associacao", "intermediacoes", "participacao", "industria",
    "comercio", "servicos", "group", "holdings", "brasil", "company", "ltda",
    "site", "seo", "geo", "web", "thread", "status", "acesso", "acessos",
    "diagnostico", "diagnosticos", "tarefa", "tarefas", "ajuste", "ajustes",
    "novo", "nova", "grupo", "erro", "erros", "pagina", "paginas", "cloudflare",
    "tray", "blog", "time", "colli", "para", "tudo", "com", "por", "uma",
    "mais", "aqui", "assessoria", "executar", "monetizacao", "eletronico",
    "sociedade", "fabrica", "fabricas", "maquinas", "acessorios", "blocos",
    "portas", "portoes", "variedades", "concierge", "medicine", "supply",
    "chain", "marcas", "patentes", "produtos", "produto", "beleza", "qualidade",
    "gestao", "engenharia", "projetos", "modelo", "imagem", "personalizacao",
    "ativacao", "loja", "todos", "como", "ainda", "categoria", "aluguel",
    "motos", "frutas", "distribuicao", "the", "and", "for", "you", "new", "old",
    "estar", "higiene", "commerce", "ecommerce", "centro", "studio",
    "locadora", "solucao", "construtora", "incorporadora", "desenvolvimento",
    "mobile", "phone", "henrique", "hoffman",
}


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()


def _coord_label(key: str, labels: dict) -> str:
    return labels.get(key) or key


def _clean_name(nome: str) -> str:
    text = nome or ""
    text = re.sub(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", " ", text)
    text = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+-\s+monetizacao.*", " ", text, flags=re.I)
    text = re.sub(r"\([^)]*\)", " ", text)
    return text


def _tokens(nome: str) -> list[str]:
    folded = _fold(_clean_name(nome))
    return [part for part in re.split(r"[^a-z0-9]+", folded) if part]


def _compact(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(_clean_name(nome)))


def _word_in(folded: str, token: str) -> bool:
    if not token:
        return False
    variants = {folded, folded.replace("-", ""), re.sub(r"[^a-z0-9]+", "", folded)}
    return any(
        re.search(rf"(?<![a-z0-9/]){re.escape(token)}(?![a-z0-9])", variant)
        for variant in variants
        if variant
    )


def _is_hexish(token: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{4,}", token))


def _prefer(keys: list[str], flow_catalog: dict[str, dict]) -> str:
    rank = {"billions": 0, "invictus": 1, "exclusive": 2}
    return sorted(keys, key=lambda key: (rank.get(flow_catalog[key].get("gerencia"), 9), len(key)))[0]


def _names_of(info: dict) -> list[str]:
    names = [info.get("nome"), *(info.get("aliases") or [])]
    return [item for item in names if item]


def build_name_index(flow_catalog: dict[str, dict]) -> list[tuple[int, str, str]]:
    """Lista (peso, frase, ticker) ordenada da mais específica para a mais curta."""
    token_owners: dict[str, list[str]] = {}
    phrases: list[tuple[int, str, str]] = []
    for ticker, info in flow_catalog.items():
        seen: set[str] = set()
        for raw in _names_of(info):
            folded = _fold(_clean_name(raw))
            compact = _compact(raw)
            tokens = _tokens(raw)
            if folded and len(folded) >= 4 and folded not in seen:
                seen.add(folded)
                phrases.append((len(folded) + 20, folded, ticker))
            if compact and len(compact) >= 5 and compact not in seen:
                seen.add(compact)
                phrases.append((len(compact) + 15, compact, ticker))
            plain = [tok for tok in tokens if not _is_hexish(tok) and len(tok) >= 3]
            meaningful = [tok for tok in plain if tok not in NAME_STOP]
            if len(plain) >= 2:
                bigram = " ".join(plain[:2])
                if bigram not in seen and len(bigram) >= 6:
                    seen.add(bigram)
                    phrases.append((len(bigram) + 12, bigram, ticker))
            if len(meaningful) >= 2:
                bigram = " ".join(meaningful[:2])
                if bigram not in seen and len(bigram) >= 6:
                    seen.add(bigram)
                    phrases.append((len(bigram) + 12, bigram, ticker))
            for tok in meaningful:
                if tok in seen:
                    continue
                seen.add(tok)
                token_owners.setdefault(tok, []).append(ticker)

    for tok, keys in token_owners.items():
        if len(tok) < 3 or tok in NAME_STOP:
            continue
        unique_keys = list(dict.fromkeys(keys))
        if len(tok) <= 3 and len(unique_keys) != 1:
            continue
        ticker = _prefer(unique_keys, flow_catalog)
        weight = len(tok) + (8 if len(unique_keys) == 1 else 3)
        phrases.append((weight, tok, ticker))

    extra = {
        "new york": "nova york",
        "minusso": "minussi",
        "minusso home": "minussi home",
        "berry house": "berrygood",
    }
    seeded: list[tuple[int, str, str]] = []
    seen_seed: set[tuple[str, str]] = set()
    for _weight, phrase, ticker in phrases:
        for alias, source in extra.items():
            if source == phrase or phrase.startswith(source + " ") or source in phrase.split():
                key = (alias, ticker)
                if key in seen_seed:
                    continue
                seen_seed.add(key)
                seeded.append((len(alias) + 12, alias, ticker))
    phrases.extend(seeded)

    phrases.sort(key=lambda item: (-item[0], -len(item[1])))
    return phrases


def unique_name_index(flow_catalog: dict[str, dict]) -> list[tuple[int, str, str]]:
    return build_name_index(flow_catalog)


def _edit1(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1 or min(len(left), len(right)) < 6:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    if len(left) < len(right):
        left, right = right, left
    i = j = diffs = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        diffs += 1
        i += 1
        if diffs > 1:
            return False
    return True


def match_by_name(
    blob: str,
    flow_catalog: dict[str, dict],
    name_index: list[tuple[int, str, str]] | None = None,
    *,
    min_len: int = 4,
) -> tuple[str | None, str | None]:
    """Retorna (ticker, frase_casada)."""
    if not blob:
        return None, None
    folded = _fold(blob)
    index = name_index or build_name_index(flow_catalog)
    for _weight, phrase, ticker in index:
        core = phrase.replace(" ", "")
        if " " not in phrase and len(core) < min_len:
            continue
        if _word_in(folded, phrase):
            return ticker, phrase

    if min_len <= 4:
        words = [part for part in re.split(r"[^a-z0-9]+", folded) if len(part) >= 6]
        for _weight, phrase, ticker in index:
            if len(phrase) < 6 or " " in phrase:
                continue
            if any(_edit1(word, phrase) for word in words):
                return ticker, phrase
    return None, None


def resolve_cliente(
    pedido: dict,
    flow_catalog: dict[str, dict],
    name_index: list[tuple[int, str, str]] | None = None,
) -> str | None:
    title = pedido.get("trecho") or ""
    textos = pedido.get("textos") or []
    body = "\n".join(textos)
    index = name_index or build_name_index(flow_catalog)
    catalog_keys = sorted(flow_catalog.keys(), key=len, reverse=True)

    brackets_title = extract_tickers([title], None, title)
    name_title, _ = match_by_name(title, flow_catalog, index, min_len=3)
    tickers_title = extract_tickers([title], catalog_keys, title)
    name_body, _ = match_by_name(body, flow_catalog, index, min_len=7)
    brackets_body = extract_tickers(textos, None, title)
    tickers_body = extract_tickers(textos, catalog_keys, title)

    for candidate in (
        next((item for item in brackets_title if item in flow_catalog), None),
        name_title,
        next((item for item in tickers_title if item in flow_catalog), None),
        name_body,
        next((item for item in brackets_body if item in flow_catalog), None),
        next((item for item in tickers_body if item in flow_catalog), None),
    ):
        if candidate:
            return candidate
    return None


def enrich_pedido(
    pedido: dict,
    flow_catalog: dict[str, dict],
    token_index: list[tuple[int, str, str]] | None = None,
) -> dict:
    roster = load_roster_index()
    labels = load_coord_map().get("coordenacoes") or {}
    pessoa = roster.get(pedido.get("autor_id") or "") or {}
    papel = pessoa.get("papel") or "ops"
    if papel == "web":
        solicitante_coord = "operacao_web"
    else:
        solicitante_coord = pessoa.get("coordenacao") or "nao_mapeado"

    textos = pedido.get("textos") or []
    ticker = resolve_cliente(pedido, flow_catalog, token_index)

    cliente = None
    gerencia = "nao_classificado"
    cliente_coord = "nao_classificado"
    if ticker and ticker in flow_catalog:
        info = flow_catalog[ticker]
        cliente = info.get("nome")
        gerencia = info.get("gerencia") or "nao_classificado"
        cliente_coord = info.get("coord") or "nao_classificado"

    return {
        **pedido,
        "task_ids": extract_task_ids(textos),
        "ticker": ticker,
        "cliente": cliente,
        "gerencia": gerencia,
        "cliente_coord": cliente_coord,
        "cliente_coord_label": _coord_label(cliente_coord, labels)
        if cliente_coord != "nao_classificado"
        else "sem ticker",
        "solicitante_coord": solicitante_coord,
        "solicitante_coord_label": _coord_label(solicitante_coord, labels),
        "solicitante_papel": papel,
        "autor_nome": pessoa.get("nome") or pedido.get("autor_nome"),
    }
