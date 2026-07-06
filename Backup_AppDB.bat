@echo off
rem ============================================================================
rem Backup_AppDB.bat
rem
rem Cong cu backup THU CONG cho Data\app.db (khong duoc git theo doi vi la DB
rem song, tang dan moi thang). Chi tao 1 ban sao co timestamp trong Data\backups,
rem KHONG tu dong xoa bat ky ban backup nao.
rem
rem Ghi chu: App da co co che tu backup ben trong khi ghi de du lieu thang
rem (xem database.py -> backup_database_file, goi tu main.py truoc moi lan
rem overwrite). File .bat nay chi la cong cu bo sung neu ban muon tu tay tao
rem them 1 ban sao truoc khi lam viec gi do quan trong (vd: truoc khi cai lai
rem may, truoc khi copy du lieu sang noi khac).
rem
rem Vi app se khong co ai bao tri sau khi ban giao, KHONG dat lich chay tu dong
rem (Task Scheduler) va KHONG tu dong xoa backup cu -- de tranh mat du lieu ma
rem khong co ai kiem tra lai.
rem ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "SRC=Data\app.db"
set "BACKUP_DIR=Data\backups"

if not exist "%SRC%" (
  echo Khong tim thay %SRC%, khong co gi de backup.
  exit /b 1
)

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

rem Tao timestamp dang YYYYMMDD_HHMMSS khong phu thuoc dinh dang ngay/gio cua may
for /f "usebackq" %%I in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "TS=%%I"

set "DEST=%BACKUP_DIR%\app_backup_%TS%.db"
copy /y "%SRC%" "%DEST%" >nul
if errorlevel 1 (
  echo LOI: Backup that bai.
  exit /b 1
)
echo Da backup: %DEST%
echo Hoan tat. (Cac ban backup cu khong bi xoa - ban tu quan ly dung luong neu can.)
