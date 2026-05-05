"""
rag.py — Retrieval-Augmented Generation
Busca chunks relevantes da base de conhecimento por TF-IDF simplificado.
Zero dependências externas. Puro Python.
"""
import re, math
from pathlib import Path
from functools import lru_cache
from collections import Counter

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# ── CONFIG ────────────────────────────────────────────────────────────────
MAX_CHUNK_CHARS = 600     # tamanho máximo de um chunk
MAX_CHUNKS_OUT  = 3       # chunks retornados por query
MIN_SCORE       = 0.05    # score mínimo para incluir chunk
MAX_RAG_CHARS   = 1500    # budget total de chars de RAG no prompt

# ── STOPWORDS ─────────────────────────────────────────────────────────────
_STOP = {
    "de","a","o","e","em","no","na","do","da","um","uma","para","com","por",
    "que","se","não","é","eu","você","isso","este","esse","como","mais",
    "mas","ou","os","as","ao","dos","das","nos","nas","me","te","ao","às",
    "the","and","for","with","this","that","are","was","have","from","its"
}

def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-záéíóúãõâêôçà\w]{2,}", text.lower())
            if w not in _STOP]

# ── CHUNKING ──────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    """Divide texto em chunks por parágrafo/seção, respeitando MAX_CHUNK_CHARS."""
    # divide por linhas em branco ou headers markdown
    raw = re.split(r"\n{2,}|(?=#{1,3} )", text)
    chunks = []
    buf = ""
    for part in raw:
        part = part.strip()
        if not part:
            continue
        if len(buf) + len(part) > MAX_CHUNK_CHARS and buf:
            chunks.append(buf.strip())
            buf = part
        else:
            buf = (buf + "\n" + part).strip() if buf else part
    if buf:
        chunks.append(buf.strip())
    return [c for c in chunks if len(c) > 30]

# ── TF-IDF SIMPLIFICADO ───────────────────────────────────────────────────

def _tf(tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    c = Counter(tokens)
    total = len(tokens)
    return {w: count / total for w, count in c.items()}

def _score_chunk(chunk_tokens: list[str], query_tokens: list[str],
                 idf: dict[str, float]) -> float:
    """Score TF-IDF do chunk em relação à query."""
    if not chunk_tokens or not query_tokens:
        return 0.0
    tf = _tf(chunk_tokens)
    score = sum(tf.get(q, 0) * idf.get(q, 1.0) for q in query_tokens)
    # bonus por matches exatos de termos técnicos de MAM
    mc_terms = {
        "item","bloco","block","entity","entidade","mob","bioma","biome",
        "crafting","receita","loot","spawn","textura","texture","behavior",
        "comportamento","resource","recurso","manifest","json","addon","mam",
        "bedrock","minecraft","component","components"
    }
    exact_bonus = sum(0.3 for q in query_tokens if q in mc_terms and q in tf)
    return score + exact_bonus

# ── MAIN FUNCTION ─────────────────────────────────────────────────────────

def retrieve(query: str, top_k: int = MAX_CHUNKS_OUT) -> str:
    """
    Busca chunks relevantes da knowledge base para a query.
    Retorna string formatada pronta para injetar no prompt.
    """
    if not KNOWLEDGE_DIR.exists():
        return ""

    # coleta todos os arquivos
    files = list(KNOWLEDGE_DIR.glob("*.txt")) + list(KNOWLEDGE_DIR.glob("*.json"))
    if not files:
        return ""

    query_tokens = _tokens(query)
    if not query_tokens:
        return ""

    # chunka todos os arquivos e calcula corpus para IDF
    all_chunks: list[tuple[str, list[str], str]] = []  # (text, tokens, source)
    doc_freq: Counter = Counter()

    for f in files:
        try:
            text = f.read_text("utf-8")
        except:
            continue
        chunks = _chunk_text(text)
        for chunk in chunks:
            toks = _tokens(chunk)
            unique = set(toks)
            doc_freq.update(unique)
            all_chunks.append((chunk, toks, f.name))

    if not all_chunks:
        return ""

    total_docs = len(all_chunks)

    # IDF para cada termo da query
    idf = {}
    for qt in query_tokens:
        df = doc_freq.get(qt, 0)
        idf[qt] = math.log((total_docs + 1) / (df + 1)) + 1

    # score cada chunk
    scored = []
    for chunk_text, chunk_toks, source in all_chunks:
        s = _score_chunk(chunk_toks, query_tokens, idf)
        if s >= MIN_SCORE:
            scored.append((s, chunk_text, source))

    if not scored:
        # fallback: retorna primeiro chunk de cada arquivo (overview)
        fallback = [all_chunks[0][0]] if all_chunks else []
        return _format_chunks([(0, c, "") for c in fallback])

    # top-k, sem duplicatas de conteúdo similar
    scored.sort(key=lambda x: -x[0])
    selected = _deduplicate(scored, top_k)

    return _format_chunks(selected)

def _deduplicate(scored: list, top_k: int) -> list:
    """Remove chunks muito similares (overlap > 60% de tokens)."""
    selected = []
    seen_tokens: list[set] = []
    for score, text, source in scored:
        toks = set(_tokens(text))
        is_dup = any(
            len(toks & seen) / max(len(toks | seen), 1) > 0.6
            for seen in seen_tokens
        )
        if not is_dup:
            selected.append((score, text, source))
            seen_tokens.append(toks)
        if len(selected) >= top_k:
            break
    return selected

def _format_chunks(chunks: list) -> str:
    """Formata chunks selecionados para o prompt."""
    if not chunks:
        return ""
    parts = []
    total = 0
    for _, text, source in chunks:
        if total + len(text) > MAX_RAG_CHARS:
            remaining = MAX_RAG_CHARS - total
            if remaining > 100:
                parts.append(text[:remaining] + "...")
            break
        parts.append(text)
        total += len(text)
    return "\n---\n".join(parts)
