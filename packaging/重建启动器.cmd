@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /codepage:65001 /target:winexe /platform:x64 /reference:System.Windows.Forms.dll /win32icon:app.ico /out:..\wwh专属语音助手.exe Launcher.cs
pause
