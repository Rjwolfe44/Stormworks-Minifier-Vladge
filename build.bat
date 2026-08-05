@echo off
setlocal enabledelayedexpansion

echo.
echo  =========================================
echo   VladgeMinifier Build Script
echo   Stormworks Lua Minifier
echo  =========================================
echo.

:: ── Clean previous builds ───────────────────────────────────────────────────
echo [1/5] Cleaning previous builds...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist VladgeMinifier.spec del /q VladgeMinifier.spec
:: Clean Python caches
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d"
)
for /r . %%f in (*.pyc) do del /q "%%f"
echo       Done.

:: ── Check Python ────────────────────────────────────────────────────────────
echo [2/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+ and add to PATH.
    exit /b 1
)
python --version

:: ── Install dependencies ─────────────────────────────────────────────────────
echo [3/5] Installing dependencies...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    exit /b 1
)
echo       Done.

:: ── Run tests ────────────────────────────────────────────────────────────────
echo [4/5] Running tests...
python -m pytest tests/test_lexer.py tests/test_minifier.py tests/test_renamer.py -v --tb=short -q
if errorlevel 1 (
    echo.
    echo WARNING: Some tests failed. Build will continue but check the output above.
    echo.
)

:: ── Build Everything (Shared Environment) ──────────────────────────────────
echo [5/5] Building Executables via build.spec...
python -m PyInstaller build.spec --clean
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

echo.
echo [6/6] Creating Export Directory...
if exist _export rmdir /s /q _export
mkdir _export

:: Copy the shared distribution folder
xcopy /s /q /i "dist\VladgeMinifier_Export" "_export\VladgeMinifier"

echo.
echo  =========================================
echo   Build Complete!
echo  =========================================
echo.
echo   Your distributable app is ready in:
echo   📁 _export\VladgeMinifier\
echo.
echo   To share with friends, simply right-click the
echo   VladgeMinifier folder and click "Compress to ZIP file".
echo.

:: Clean build artifacts (keep dist/ and _export/)
if exist build rmdir /s /q build

endlocal
