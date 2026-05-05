"""
main.py — MAM-AI Backend (Gemini 2.0 Flash)
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx, json, os
from pathlib import Path

from prompts import build_prompt
from memory import (
    save_turn, get_session_context, get_session_stats, clear_session,
    update_profile, get_profile_context, get_profile_data, clear_profile
)
from rag import retrieve

app = FastAPI(title="MAM-AI", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.0-flash"
GEMINI_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
GEMINI_URL_NS  = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
KNOWLEDGE_DIR  = Path(__file__).parent / "knowledge"
KNOWLEDGE_DIR.mkdir(exist_ok=True)

# ── SCHEMAS ───────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    mode: str        = "chat"
    message: str
    session_id: str  = "default"
    profile_id: str  = "default"
    script_type: str = ""
    stream: bool     = True

class KnowledgeAdd(BaseModel):
    filename: str
    content: str

# ── HELPERS ───────────────────────────────────────────────────────────────
def _build_gemini_contents(system: str, session_turns: list, message: str) -> list:
    """Monta o array contents no formato Gemini."""
    contents = []
    # injeta system como primeiro turno de usuário (Gemini não tem role=system nativo)
    contents.append({"role": "user", "parts": [{"text": f"[INSTRUÇÕES DO SISTEMA]\n{system}"}]})
    contents.append({"role": "model", "parts": [{"text": "Entendido. Vou seguir essas instruções."}]})
    # histórico de sessão
    for turn in session_turns:
        role = "model" if turn["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": turn["content"]}]})
    # mensagem atual
    contents.append({"role": "user", "parts": [{"text": message}]})
    return contents

# ── HEALTH ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    has_key = bool(GEMINI_API_KEY)
    if not has_key:
        return {"status": "ok", "gemini": False, "error": "GEMINI_API_KEY não configurada"}
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"role":"user","parts":[{"text":"oi"}]}],
                      "generationConfig":{"maxOutputTokens":5}}
            )
            ok = r.status_code == 200
        return {"status": "ok", "gemini": ok, "model": GEMINI_MODEL}
    except:
        return {"status": "ok", "gemini": False}

# ── CHAT ──────────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: ChatRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(400, "GEMINI_API_KEY não configurada")

    rag_ctx     = retrieve(req.message)
    profile_ctx = get_profile_context(req.profile_id)
    system      = build_prompt(req.mode, rag_ctx, profile_ctx)
    sess_turns  = get_session_context(req.session_id, req.message)
    contents    = _build_gemini_contents(system, sess_turns, req.message)

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 800,
            "temperature": 0.7,
            "topP": 0.9,
        }
    }

    save_turn(req.session_id, "user", req.message, req.mode)
    update_profile(req.profile_id, req.message, req.mode, req.script_type)

    if not req.stream:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(GEMINI_URL_NS, json=payload)
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            save_turn(req.session_id, "assistant", text, req.mode)
            return {"response": text}

    async def stream_gen():
        full = []
        async with httpx.AsyncClient(timeout=60) as c:
            async with c.stream("POST", GEMINI_URL, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        token = (chunk.get("candidates", [{}])[0]
                                      .get("content", {})
                                      .get("parts", [{}])[0]
                                      .get("text", ""))
                        if token:
                            full.append(token)
                            yield f"data: {json.dumps({'token': token})}\n\n"
                    except:
                        pass
        save_turn(req.session_id, "assistant", "".join(full), req.mode)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_gen(), media_type="text/event-stream")

# ── MEMORY ────────────────────────────────────────────────────────────────
@app.get("/memory/session/{sid}")
async def session_info(sid: str): return get_session_stats(sid)

@app.get("/memory/profile/{pid}")
async def profile_info(pid: str): return get_profile_data(pid)

@app.delete("/memory/session/{sid}")
async def del_session(sid: str): clear_session(sid); return {"cleared": sid}

@app.delete("/memory/profile/{pid}")
async def del_profile(pid: str): clear_profile(pid); return {"cleared": pid}

# ── KNOWLEDGE ─────────────────────────────────────────────────────────────
@app.post("/knowledge")
async def add_knowledge(data: KnowledgeAdd):
    safe = "".join(c for c in data.filename if c.isalnum() or c in "._-")
    if not safe.endswith((".txt", ".json")): safe += ".txt"
    (KNOWLEDGE_DIR / safe).write_text(data.content, encoding="utf-8")
    return {"saved": safe}

@app.get("/knowledge")
async def list_knowledge():
    return {"files": [{"name": f.name, "size": f.stat().st_size}
                      for f in KNOWLEDGE_DIR.iterdir() if f.suffix in (".txt",".json")]}

@app.delete("/knowledge/{filename}")
async def delete_knowledge(filename: str):
    path = KNOWLEDGE_DIR / filename
    if not path.exists() or path.parent != KNOWLEDGE_DIR:
        raise HTTPException(404, "Não encontrado")
    path.unlink(); return {"deleted": filename}

@app.get("/debug/rag")
async def debug_rag(q: str = "item"):
    r = retrieve(q); return {"query": q, "result": r, "chars": len(r)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
