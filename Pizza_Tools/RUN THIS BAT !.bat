@echo off
title Pip Requirements Installer
cd /d "%~dp0"

echo Start the Installation
echo.

:: Run
python -m pip install -r requirements.txt

:: Errors
if %errorlevel% equ 0 (
    echo.
    echo ==========================================
    echo Installation successful!
    echo ==========================================
) else (
    echo.
    echo ==========================================
    echo Installation failed.
    echo Please check if Python/pip is installed and in PATH.
    echo ==========================================
)

echo.
pause