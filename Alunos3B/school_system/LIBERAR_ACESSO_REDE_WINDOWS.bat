@echo off
setlocal
title Liberar Sistema Escolar no Firewall

net session >nul 2>nul
if not "%errorlevel%"=="0" (
    echo Este arquivo precisa ser executado como administrador.
    echo Vou tentar abrir novamente com permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "REGRA=Sistema Escolar Flask 5000"

netsh advfirewall firewall show rule name="%REGRA%" >nul 2>nul
if "%errorlevel%"=="0" (
    echo A regra "%REGRA%" ja existe no Firewall.
) else (
    netsh advfirewall firewall add rule name="%REGRA%" dir=in action=allow protocol=TCP localport=5000
    if errorlevel 1 (
        echo Nao foi possivel criar a regra do Firewall.
        pause
        exit /b 1
    )
    echo Regra criada com sucesso.
)

echo.
echo Agora outros computadores da mesma rede devem conseguir acessar:
echo   http://IP_DO_SEU_COMPUTADOR:5000
echo.
pause
