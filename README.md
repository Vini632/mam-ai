# MAM·AI — Gemini 2.0 Flash Edition

## Pré-requisitos
- Python 3.10+
- Gemini API Key gratuita → https://aistudio.google.com/apikey

## Rodar local (Windows)

```bat
# 1. Configurar API Key (PowerShell)
$env:GEMINI_API_KEY="sua_chave_aqui"

# 2. Dar duplo clique no start.bat
```
Ou manualmente:
```powershell
cd backend
pip install -r requirements.txt
$env:GEMINI_API_KEY="sua_chave_aqui"
python main.py
# outro terminal:
cd frontend
python -m http.server 3000
```
Acesse: http://localhost:3000
Em Configurações, coloque a API Key no campo.

---

## Deploy na nuvem (Railway + Firebase)

### Backend → Railway
1. Crie conta em https://railway.app
2. Suba esta pasta no GitHub
3. No Railway: "Deploy from GitHub" → seleciona o repo
4. Adicione variável de ambiente: `GEMINI_API_KEY=sua_chave`
5. Railway detecta o Procfile e faz deploy automático
6. Copie a URL gerada (ex: `https://mam-ai.up.railway.app`)

### Frontend → Firebase Hosting
```bash
npm install -g firebase-tools
firebase login
firebase init hosting
# Public directory: frontend
# Single-page app: No
firebase deploy
```
No site: Configurações → URL do Backend → cole a URL do Railway

---

## Estrutura
```
mam-ai/
├── backend/
│   ├── main.py        # FastAPI + Gemini 2.0 Flash
│   ├── memory.py      # Sessão + perfil persistente
│   ├── rag.py         # TF-IDF retrieval
│   ├── prompts.py     # System prompts
│   ├── requirements.txt
│   └── knowledge/
│       └── mam_base.txt
├── frontend/
│   └── index.html
├── Procfile           # Railway deploy
├── railway.json
├── nixpacks.toml
├── start.bat          # Windows
└── start.sh           # Linux/Mac
```
