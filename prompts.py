"""
prompts.py — System prompts com injeção de memória e RAG.
Cada seção tem budget claro para não desperdiçar tokens.
"""

_BASE_RULES = {
    "script": (
        "Você é um gerador de scripts JSON para Mobile Addon Maker (MAM) no Minecraft Bedrock.\n"
        "REGRAS: gere APENAS o código solicitado | máx 2 frases de contexto | "
        "pronto para copiar | formato Bedrock correto | comente só linhas críticas."
    ),
    "idea": (
        "Você é um gerador de ideias de addons Minecraft Bedrock via MAM.\n"
        "REGRAS: máx 5 ideias | formato '**Nome**: descrição 1 frase' | "
        "viáveis no MAM mobile | seja criativo e específico."
    ),
    "chat": (
        "Você é um assistente especializado em addons Minecraft Bedrock Edition com Mobile Addon Maker (MAM).\n"
        "REGRAS: direto e prático | foque em soluções implementáveis no mobile | "
        "explique só se pedido | respostas concisas."
    ),
}

def build_prompt(
    mode: str,
    rag_context: str = "",
    profile_context: str = "",
) -> str:
    base = _BASE_RULES.get(mode, _BASE_RULES["chat"])
    parts = [base]

    if profile_context.strip():
        parts.append(f"\n[PERFIL DO USUÁRIO]\n{profile_context}")

    if rag_context.strip():
        parts.append(f"\n[BASE DE CONHECIMENTO RELEVANTE]\n{rag_context}")

    return "\n".join(parts)
