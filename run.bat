@echo off
cd /d "%~dp0"
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 main.py
if errorlevel 1 (
  echo. 
  echo Aplikasi gagal dijalankan. Periksa error di atas.
  pause
  exit /b 1
)
pause
