@echo off
setlocal
cd /d "%~dp0"
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 -m PyInstaller --noconfirm --clean --onedir --name PandaMirror20 --windowed --collect-all PySide6 main.py
if errorlevel 1 (
  echo BUILD GAGAL.
  pause
  exit /b 1
)
if exist dist\PandaMirror20\ (
  echo.
  echo Build selesai di dist\PandaMirror20\
  echo Pastikan folder tools\platform-tools\adb.exe dan tools\scrcpy\scrcpy.exe tersedia di folder yang sama.
)
pause
