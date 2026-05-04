@echo off
echo ==============================
echo       MAM-AI LAUNCHER
echo ==============================

cd /d "%~dp0backend"

echo [1/3] Instalando dependencias...
pip install -r requirements.txt -q

echo [2/3] Iniciando backend...
start "MAM-AI Backend" cmd /k "python main.py"
timeout /t 2 /nobreak > nul

echo [3/3] Iniciando frontend...
cd /d "%~dp0frontend"
start "MAM-AI Frontend" cmd /k "python -m http.server 3000"
timeout /t 2 /nobreak > nul

echo.
echo ==============================
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:3000
echo ==============================
echo.
echo LEMBRE-SE: configure GEMINI_API_KEY
echo   set GEMINI_API_KEY=sua_chave
echo   ou crie backend\.env
echo.
start http://localhost:3000
pause
