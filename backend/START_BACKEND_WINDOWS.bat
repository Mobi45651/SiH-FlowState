@echo off
setlocal
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo [1/3] Creating virtual environment...
  py -m venv venv
)
echo [2/3] Installing backend dependencies...
venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
echo [3/3] Starting FlowState backend on http://localhost:5000
venv\Scripts\python.exe app.py
pause
