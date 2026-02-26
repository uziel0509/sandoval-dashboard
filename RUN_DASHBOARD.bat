@echo off
title SANDOVAL Dashboard v2.0
cd /d "%~dp0"
echo.
echo ==========================================
echo     SANDOVAL Dashboard v2.0
echo     MECANICA Y REPUESTOS SANDOVAL EIRL
echo ==========================================
echo Cerrando instancias anteriores...
taskkill /IM python.exe /F >nul 2>&1
taskkill /IM pythonw.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo Iniciando servidor...
echo.
python main.py
