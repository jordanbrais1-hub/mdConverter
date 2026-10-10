@echo off
REM Build mdConverter for Windows:
REM   dist\mdConverter\mdConverter.exe          portable app folder
REM   dist\mdConverter-Setup-<version>.exe      installer (needs Inno Setup 6.6+)
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

if not exist assets\icon.ico python tools\make_assets.py

pyinstaller --noconfirm --clean mdConverter.spec || goto :error

REM --- Installer ------------------------------------------------------------
for /f %%v in ('python -c "import mdconverter; print(mdconverter.__version__)"') do set APPVER=%%v

set "ISCC="
for %%p in (
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
) do if exist %%p set "ISCC=%%~p"

if not defined ISCC (
    echo.
    echo Inno Setup not found - skipping the installer.
    echo Install it with:  winget install JRSoftware.InnoSetup
    goto :done
)

"%ISCC%" /Q /DAppVersion=%APPVER% installer\mdConverter.iss || goto :error
echo Installer: dist\mdConverter-Setup-%APPVER%.exe

:done
echo.
echo Build complete: dist\mdConverter\mdConverter.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
