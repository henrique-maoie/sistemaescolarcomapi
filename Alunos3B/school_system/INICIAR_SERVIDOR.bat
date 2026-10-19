@echo off
setlocal
cd /d "%~dp0"
title Sistema Escolar - Servidor

set "PORTA=5000"
if not "%~1"=="" set "PORTA=%~1"

set "PYTHON_CMD="
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo Python nao encontrado.
    echo Instale o Python 3 e marque a opcao "Add Python to PATH".
    echo Link: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Conferindo dependencias do sistema...
%PYTHON_CMD% -c "import flask, werkzeug" >nul 2>nul
if errorlevel 1 (
    echo Instalando dependencias do sistema...
    %PYTHON_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Nao foi possivel instalar as dependencias automaticamente.
        echo Tente rodar: %PYTHON_CMD% -m pip install -r requirements.txt
        pause
        exit /b 1
    )
) else (
    %PYTHON_CMD% -c "from importlib.metadata import version; import sys; major=int(version('Flask').split('.')[0]); sys.exit(0 if major >= 3 else 1)" >nul 2>nul
    if errorlevel 1 (
        echo Flask antigo detectado. Tentando atualizar...
        %PYTHON_CMD% -m pip install --upgrade -r requirements.txt
        if errorlevel 1 (
            echo Nao consegui atualizar agora. Vou tentar iniciar mesmo assim.
        )
    )
)

%PYTHON_CMD% -c "import sqlite3, sys, database; database.criar_banco_dados(); con=sqlite3.connect(database.DB_PATH); total=con.execute('select count(*) from usuarios').fetchone()[0]; con.close(); sys.exit(0 if total else 1)" >nul 2>nul
if errorlevel 1 (
    echo Banco sem usuarios. Criando logins de teste...
    %PYTHON_CMD% populate_db.py
    if errorlevel 1 (
        echo.
        echo Nao foi possivel criar os logins de teste automaticamente.
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo Sistema Escolar iniciado na porta %PORTA%
echo ============================================================
echo Neste computador:
echo   http://localhost:%PORTA%
echo.
echo Em outro computador na mesma rede/Wi-Fi, tente um destes enderecos:
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ips=Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway -and $_.IPv4Address} | ForEach-Object {$_.IPv4Address.IPAddress} | Sort-Object -Unique; if($ips){$ips | ForEach-Object {Write-Host ('  http://' + $_ + ':%PORTA%')}} else {Write-Host '  Nao encontrei IP com gateway. Use ipconfig e procure por IPv4.'}"
echo.
echo Se outro computador nao abrir, execute LIBERAR_ACESSO_REDE_WINDOWS.bat como administrador.
echo Para parar o servidor, feche esta janela ou pressione Ctrl+C.
echo ============================================================
echo.

start "" "http://localhost:%PORTA%"
set "HOST=0.0.0.0"
set "PORT=%PORTA%"
%PYTHON_CMD% app.py

echo.
echo Servidor encerrado.
pause
