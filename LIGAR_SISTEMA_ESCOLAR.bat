@echo off
setlocal
title Sistema Escolar 3B - Servidor

set "PASTA_BASE=%~dp0"
set "PASTA_SISTEMA=%PASTA_BASE%Alunos3B\school_system"

if not exist "%PASTA_SISTEMA%\app.py" (
    echo Nao encontrei o sistema em:
    echo %PASTA_SISTEMA%
    echo.
    echo Confira se a pasta Alunos3B\school_system esta junto deste arquivo.
    pause
    exit /b 1
)

cd /d "%PASTA_SISTEMA%"
call INICIAR_SERVIDOR.bat
