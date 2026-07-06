@echo off
cd /d "%~dp0"
set "PYTHON_EXE=.\Python_Portable\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=.\python-3.15.0b3-embed-amd64\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Khong tim thay Python portable. Vui long them thu muc Python_Portable hoac python-3.15.0b3-embed-amd64.
  exit /b 1
)
start "" "%PYTHON_EXE%" ".\Code\main.py"
timeout /t 5 >nul
start http://127.0.0.1:8000
