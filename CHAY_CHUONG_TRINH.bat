@echo off
cd /d "%~dp0"

set "PYTHON_EXE="
if exist ".\python-3.13.14-embed-amd64\python.exe" (
  rem Uu tien ban Python portable da dong goi san (co du thu vien, khong can internet).
  set "PYTHON_EXE=.\python-3.13.14-embed-amd64\python.exe"
) else if exist ".\Python_Portable\python.exe" (
  set "PYTHON_EXE=.\Python_Portable\python.exe"
) else (
  where python >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_EXE=python"
  )
)

if not defined PYTHON_EXE (
  echo Khong tim thay Python tren he thong.
  echo Vui long cai dat Python tai https://www.python.org/downloads/ ^(nho tick "Add to PATH"^) roi chay lai file nay.
  pause
  exit /b 1
)

echo Dang kiem tra thu vien Python can thiet...
"%PYTHON_EXE%" -c "import fastapi, uvicorn, streamlit, pandas, sqlalchemy, openpyxl, xlsxwriter, requests, multipart" >nul 2>nul
if errorlevel 1 (
  echo Con thieu thu vien. Dang cai dat tu requirements.txt, vui long doi va dam bao may co internet...
  "%PYTHON_EXE%" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo.
    echo LOI: Khong the cai dat thu vien can thiet.
    echo Neu dang dung thu muc Python portable ^(khong co pip^), hay cai Python day du tu python.org roi chay lai file nay.
    pause
    exit /b 1
  )
)

echo Dang khoi dong Backend API...
start "BHXH Backend" cmd /k ""%PYTHON_EXE%" -m uvicorn Code.main:app --host 127.0.0.1 --port 8000"

set WAIT_COUNT=0
:WAIT_BACKEND
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',8000); exit 0 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto BACKEND_READY
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 30 goto BACKEND_TIMEOUT
timeout /t 1 >nul
goto WAIT_BACKEND

:BACKEND_TIMEOUT
echo.
echo LOI: Backend khong khoi dong duoc sau 30 giay.
echo Hay xem cua so "BHXH Backend" vua mo de biet chi tiet loi (vi du: thieu thu vien, loi code...).
pause
exit /b 1

:BACKEND_READY
echo Backend da san sang tren cong 8000.

echo Dang khoi dong giao dien Streamlit...
start "BHXH Dashboard" cmd /k ""%PYTHON_EXE%" -m streamlit run .\Code\app.py --server.address 127.0.0.1 --server.port 8501"

set WAIT_COUNT=0
:WAIT_FRONTEND
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',8501); exit 0 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto FRONTEND_READY
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 30 goto FRONTEND_TIMEOUT
timeout /t 1 >nul
goto WAIT_FRONTEND

:FRONTEND_TIMEOUT
echo.
echo LOI: Giao dien Streamlit khong khoi dong duoc sau 30 giay.
echo Hay xem cua so "BHXH Dashboard" vua mo de biet chi tiet loi.
pause
exit /b 1

:FRONTEND_READY
echo Giao dien da san sang tren cong 8501.
start http://127.0.0.1:8501
