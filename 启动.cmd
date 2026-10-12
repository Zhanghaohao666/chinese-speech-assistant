@echo off
chcp 65001 >nul
title wwh专属语音助手
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYTHONIOENCODING=utf-8"
set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%APP_PYTHON%" (
 echo Please run setup.ps1 first.
 pause
 exit /b 1
)
"%APP_PYTHON%" -m transcriber.app %*
if errorlevel 1 pause
