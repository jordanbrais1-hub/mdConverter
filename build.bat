@echo off
REM Build a standalone Windows build of mdConverter into dist\mdConverter\
REM Run from the project folder: build.bat

setlocal
cd /d "%~dp0"

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv || goto :error
)

call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt || goto :error

if not exist assets\icon.ico python tools\make_icon.py

pyinstaller --noconfirm --clean mdConverter.spec || goto :error

echo.
echo Build complete: dist\mdConverter\mdConverter.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
