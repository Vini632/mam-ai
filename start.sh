#!/bin/bash
cd "$(dirname "$0")"

echo "=============================="
echo "       MAM-AI LAUNCHER        "
echo "=============================="

# Backend
cd backend
pip install -r requirements.txt -q
python main.py &
BACKEND_PID=$!
echo "[✓] Backend rodando em http://localhost:8000"

# Frontend (servidor simples)
cd ../frontend
python3 -m http.server 3000 &
FRONTEND_PID=$!
echo "[✓] Frontend rodando em http://localhost:3000"

echo ""
echo "Abra no celular (mesma rede):"
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "  Frontend: http://$LOCAL_IP:3000"
echo "  Backend:  http://$LOCAL_IP:8000"
echo ""
echo "Para acesso externo (ngrok):"
echo "  ngrok http 8000"
echo "  (Cole a URL em Configurações no site)"
echo ""
echo "Ctrl+C para parar."

wait $BACKEND_PID $FRONTEND_PID
