@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
title Agatha Souza Studio

echo.
echo  ================================================
echo    AGATHA SOUZA STUDIO  -  Gestao do Estudio
echo  ================================================
echo.

rem ---------- 1. Python 3.11 ou superior ----------
set "PYLAUNCH="
call :trypython "py -3"
if not defined PYLAUNCH call :trypython "python"
if not defined PYLAUNCH goto :nopython

rem ---------- 2. Ambiente virtual (.venv) ----------
set "VPY=.venv\Scripts\python.exe"
if exist "%VPY%" (
    "%VPY%" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo [aviso] O ambiente virtual esta quebrado ^(a pasta foi movida?^). Recriando...
        rmdir /s /q .venv
    )
)
if not exist "%VPY%" (
    echo [1/4] Criando o ambiente virtual...
    %PYLAUNCH% -m venv .venv
    if errorlevel 1 goto :fail
)

rem ---------- 3. Dependencias (so reinstala se requirements.txt mudou) ----------
set "STAMP=.venv\requirements.installed.txt"
"%VPY%" -c "import flask, flask_sqlalchemy, flask_migrate, flask_login, flask_wtf, PIL, dotenv" >nul 2>&1
if errorlevel 1 del /q "%STAMP%" >nul 2>&1
fc /b requirements.txt "%STAMP%" >nul 2>&1
if errorlevel 1 (
    echo [2/4] Instalando dependencias ^(somente na primeira vez^)...
    "%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt
    if errorlevel 1 goto :fail
    copy /y requirements.txt "%STAMP%" >nul
)

rem ---------- 4. .env, banco, migracoes e administradora (seguro e repetivel) ----------
echo [3/4] Preparando o sistema ^(.env, banco, migracoes, administradora^)...
"%VPY%" bootstrap.py
if errorlevel 1 goto :fail
"%VPY%" -m flask --app wsgi setup
if errorlevel 1 goto :fail
if /i "%~1"=="setup" goto :prepared
if /i "%~1"=="login" (
    echo Aplicando o login e a senha do arquivo .env...
    "%VPY%" -m flask --app wsgi set-login
    if errorlevel 1 goto :fail
)

rem ---------- 5. Servidor ----------
set "PORT=5000"
for /f %%p in ('%VPY% bootstrap.py port') do set "PORT=%%p"
set "FLASK_DEBUG=0"
if /i "%~1"=="debug" set "FLASK_DEBUG=1"
echo.
echo  ================================================
echo    Sistema pronto! Abra no navegador:
echo.
echo        http://127.0.0.1:%PORT%
echo.
echo    Para encerrar: pressione Ctrl+C nesta janela.
echo.
"%VPY%" bootstrap.py info
echo  ================================================
echo.
"%VPY%" -m flask --app wsgi run --host 127.0.0.1 --port %PORT%
echo.
echo O servidor foi encerrado.
pause
exit /b 0

:prepared
echo.
echo Preparacao concluida. Para iniciar o servidor, execute start.bat sem argumentos.
exit /b 0

:trypython
%~1 -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
if not errorlevel 1 set "PYLAUNCH=%~1"
exit /b 0

:nopython
echo [ERRO] Python 3.11 ou superior nao foi encontrado.
echo        Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH".
pause
exit /b 1

:fail
echo.
echo [ERRO] Algo falhou. Leia a mensagem acima. O banco e os dados nao foram apagados.
pause
exit /b 1
