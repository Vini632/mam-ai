"""
memory.py — Session + Persistent memory
- Session: in-memory dict, expires after TTL
- Persistent: JSON file per profile
- Token-aware: never bloats the prompt
"""
import json, time, re
from pathlib import Path
from collections import Counter

# ── DIRS ─────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent / "memory"
SESSIONS_DIR = BASE / "sessions"
PROFILES_DIR = BASE / "profiles"
for d in [SESSIONS_DIR, PROFILES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── CONSTANTS ─────────────────────────────────────────────────────────────
SESSION_TTL     = 3600       # 1h inatividade limpa sessão
MAX_SESSION_TURNS = 20       # turns armazenados por sessão
CONTEXT_TURNS   = 4          # turns injetados no prompt
MAX_CONTEXT_CHARS = 1200     # budget de chars para contexto de sessão
MAX_PROFILE_CHARS = 400      # budget de chars para contexto de perfil

# ── IN-MEMORY SESSIONS ────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}

def _now() -> float:
    return time.time()

def _prune_expired():
    dead = [k for k, v in _sessions.items() if _now() - v["last_active"] > SESSION_TTL]
    for k in dead:
        del _sessions[k]

# ── SESSION FUNCTIONS ─────────────────────────────────────────────────────

def save_turn(session_id: str, role: str, content: str, mode: str = "chat"):
    """Salva um turno na sessão em memória."""
    _prune_expired()
    if session_id not in _sessions:
        _sessions[session_id] = {"turns": [], "last_active": _now()}
    sess = _sessions[session_id]
    sess["turns"].append({
        "role": role,
        "content": content[:2000],   # limita tamanho de cada turno
        "mode": mode,
        "ts": _now()
    })
    # mantém só os últimos N
    if len(sess["turns"]) > MAX_SESSION_TURNS:
        sess["turns"] = sess["turns"][-MAX_SESSION_TURNS:]
    sess["last_active"] = _now()

def get_session_context(session_id: str, query: str) -> list[dict]:
    """
    Retorna turns relevantes da sessão como lista de mensagens.
    Estratégia: últimos CONTEXT_TURNS + qualquer turno com overlap de palavras-chave.
    Respeita MAX_CONTEXT_CHARS.
    """
    _prune_expired()
    sess = _sessions.get(session_id)
    if not sess or not sess["turns"]:
        return []

    turns = sess["turns"]
    # últimos turns (exclui o turno atual que ainda não foi salvo)
    recent = turns[-CONTEXT_TURNS * 2:]  # *2 porque user+assistant
    
    # filtra por relevância se tiver mais turns que o budget
    query_words = set(_tokenize(query))
    scored = []
    for t in recent:
        words = set(_tokenize(t["content"]))
        score = len(query_words & words) + (2 if t["role"] == "assistant" else 1)
        scored.append((score, t))
    scored.sort(key=lambda x: -x[0])

    # monta lista respeitando budget de chars
    selected = []
    total_chars = 0
    for _, t in scored:
        chars = len(t["content"])
        if total_chars + chars > MAX_CONTEXT_CHARS:
            break
        selected.append(t)
        total_chars += chars

    # reordena por timestamp (ordem cronológica)
    selected.sort(key=lambda t: t["ts"])
    return [{"role": t["role"], "content": t["content"]} for t in selected]

def get_session_stats(session_id: str) -> dict:
    sess = _sessions.get(session_id)
    if not sess:
        return {"turns": 0, "active_mins": 0}
    turns = sess["turns"]
    if not turns:
        return {"turns": 0, "active_mins": 0}
    span = (turns[-1]["ts"] - turns[0]["ts"]) / 60
    return {"turns": len(turns), "active_mins": round(span, 1)}

def clear_session(session_id: str):
    _sessions.pop(session_id, None)

# ── PERSISTENT PROFILE ────────────────────────────────────────────────────

def _profile_path(profile_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", profile_id)
    return PROFILES_DIR / f"{safe}.json"

def _load_profile(profile_id: str) -> dict:
    path = _profile_path(profile_id)
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except:
            pass
    return {
        "created_at": _now(),
        "last_active": _now(),
        "script_types": {},      # {"item": 5, "entity": 2, ...}
        "topics": [],            # últimos 15 tópicos/keywords detectados
        "preferences": [],       # ["prefere código simples", ...]
        "total_interactions": 0,
        "modes_used": {},        # {"script": 10, "chat": 5, ...}
        "last_messages": []      # últimas 3 mensagens do usuário (resumo)
    }

def _save_profile(profile_id: str, data: dict):
    data["last_active"] = _now()
    _profile_path(profile_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def update_profile(profile_id: str, message: str, mode: str, script_type: str = ""):
    """Atualiza perfil persistente com dados da interação atual."""
    p = _load_profile(profile_id)
    p["total_interactions"] += 1
    
    # rastrear modo usado
    p["modes_used"][mode] = p["modes_used"].get(mode, 0) + 1

    # rastrear tipo de script
    if script_type and mode == "script":
        p["script_types"][script_type] = p["script_types"].get(script_type, 0) + 1

    # extrair tópicos/keywords da mensagem
    keywords = _extract_keywords(message)
    p["topics"] = (keywords + p["topics"])[:15]

    # detectar preferências implícitas
    prefs = _detect_preferences(message)
    for pref in prefs:
        if pref not in p["preferences"]:
            p["preferences"].append(pref)
    p["preferences"] = p["preferences"][:8]

    # salvar resumo das últimas mensagens
    p["last_messages"] = ([message[:120]] + p["last_messages"])[:3]

    _save_profile(profile_id, p)

def get_profile_context(profile_id: str) -> str:
    """Retorna contexto do perfil formatado para injeção no prompt."""
    p = _load_profile(profile_id)
    if p["total_interactions"] == 0:
        return ""

    parts = []

    # scripts mais usados
    if p["script_types"]:
        top = sorted(p["script_types"].items(), key=lambda x: -x[1])[:3]
        parts.append("Scripts frequentes: " + ", ".join(f"{k}({v}x)" for k, v in top))

    # modo preferido
    if p["modes_used"]:
        top_mode = max(p["modes_used"], key=p["modes_used"].get)
        parts.append(f"Modo preferido: {top_mode}")

    # tópicos recentes únicos
    unique_topics = list(dict.fromkeys(p["topics"]))[:6]
    if unique_topics:
        parts.append("Tópicos recentes: " + ", ".join(unique_topics))

    # preferências detectadas
    if p["preferences"]:
        parts.append("Preferências: " + "; ".join(p["preferences"]))

    context = " | ".join(parts)
    # respeita budget
    return context[:MAX_PROFILE_CHARS] if context else ""

def get_profile_data(profile_id: str) -> dict:
    """Retorna perfil completo para exibição na UI."""
    return _load_profile(profile_id)

def clear_profile(profile_id: str):
    path = _profile_path(profile_id)
    if path.exists():
        path.unlink()

# ── HELPERS ──────────────────────────────────────────────────────────────

_STOPWORDS = {
    "de","a","o","e","em","no","na","do","da","um","uma","para","com","por",
    "que","se","não","é","eu","você","isso","este","esse","como","mais",
    "mas","ou","um","uma","os","as","ao","dos","das","nos","nas","me","te",
    "create","make","add","use","the","and","for","with","this","that"
}

def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-záéíóúãõâêôçà\w]{3,}", text.lower())
    return [w for w in words if w not in _STOPWORDS]

def _extract_keywords(text: str) -> list[str]:
    """Extrai keywords relevantes de uma mensagem."""
    tokens = _tokenize(text)
    # prioriza termos técnicos de Minecraft/MAM
    mc_terms = {
        "item","bloco","block","entidade","entity","mob","bioma","biome",
        "crafting","receita","recipe","loot","spawn","textura","texture",
        "comportamento","behavior","recurso","resource","script","addon",
        "dano","damage","velocidade","speed","vida","health","magia","magic",
        "espada","sword","armadura","armor","poção","potion","ferramenta","tool"
    }
    # tokens que são termos técnicos primeiro, depois os mais frequentes
    tech = [t for t in tokens if t in mc_terms]
    other = [t for t in tokens if t not in mc_terms]
    freq = [w for w, _ in Counter(other).most_common(4)]
    return list(dict.fromkeys(tech + freq))[:6]

def _detect_preferences(text: str) -> list[str]:
    """Detecta preferências implícitas no texto do usuário."""
    text_lower = text.lower()
    prefs = []
    if any(w in text_lower for w in ["simples","básico","fácil","simpl"]):
        prefs.append("prefere implementações simples")
    if any(w in text_lower for w in ["avançado","complexo","detalhado","completo"]):
        prefs.append("prefere implementações detalhadas")
    if any(w in text_lower for w in ["rápido","curto","só o código","direto"]):
        prefs.append("prefere respostas diretas sem explicação")
    if any(w in text_lower for w in ["explicar","entender","como funciona","porquê"]):
        prefs.append("gosta de explicações")
    return prefs
