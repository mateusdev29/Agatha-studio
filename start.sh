#!/usr/bin/env bash
# Equivalente do start.bat para Mac/Linux:  ./start.sh   (ou ./start.sh setup | debug)
set -e
cd "$(dirname "$0")"
export PYTHONUTF8=1

echo; echo " ================================================"; echo "   AGATHA SOUZA STUDIO  -  Gestao do Estudio"; echo " ================================================"; echo

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "[ERRO] Python 3.11 ou superior nao encontrado."; exit 1; }

VPY=".venv/bin/python"
if [ -x "$VPY" ] && ! "$VPY" -c 'import sys' 2>/dev/null; then echo "[aviso] ambiente virtual quebrado; recriando..."; rm -rf .venv; fi
[ -x "$VPY" ] || { echo "[1/4] Criando o ambiente virtual..."; "$PY" -m venv .venv; }

STAMP=".venv/requirements.installed.txt"
"$VPY" -c "import flask, flask_sqlalchemy, flask_migrate, flask_login, flask_wtf, PIL, dotenv" 2>/dev/null || rm -f "$STAMP"
if ! cmp -s requirements.txt "$STAMP" 2>/dev/null; then
  echo "[2/4] Instalando dependencias (somente na primeira vez)..."
  "$VPY" -m pip install --disable-pip-version-check -q -r requirements.txt
  cp requirements.txt "$STAMP"
fi

echo "[3/4] Preparando o sistema (.env, banco, migracoes, administradora)..."
"$VPY" bootstrap.py
"$VPY" -m flask --app wsgi setup
[ "$1" = "setup" ] && { echo; echo "Preparacao concluida."; exit 0; }
if [ "$1" = "login" ]; then echo "Aplicando o login e a senha do arquivo .env..."; "$VPY" -m flask --app wsgi set-login; fi

PORT="$("$VPY" bootstrap.py port)"
export FLASK_DEBUG=0; [ "$1" = "debug" ] && export FLASK_DEBUG=1
echo; echo " ================================================"; echo "   Sistema pronto! Abra no navegador:"; echo; echo "       http://127.0.0.1:$PORT"; echo
echo "   Para encerrar: Ctrl+C"; echo; "$VPY" bootstrap.py info; echo " ================================================"; echo
exec "$VPY" -m flask --app wsgi run --host 127.0.0.1 --port "$PORT"
