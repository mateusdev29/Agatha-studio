"""Prepara o ambiente local ANTES do Flask existir. Usa apenas a biblioteca padrão.

    python bootstrap.py          garante o .env (cria, gera SECRET_KEY e senha do admin uma única vez)
    python bootstrap.py port     imprime a primeira porta livre a partir de 5000
    python bootstrap.py info     mostra qual e-mail usar no login

Regras: nunca sobrescreve um valor já preenchido; só gera o que estiver em branco; só age em
desenvolvimento (APP_ENV ausente ou "development"). Em produção você mesma define tudo no .env.
"""
import os
import secrets
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_PASSWORD = 10
DEFAULTS = {"DEV_ADMIN_NAME": "Agatha Souza", "DEV_ADMIN_EMAIL": "agatha@example.com"}


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def get_value(text: str, key: str) -> str | None:
    """Valor de KEY no texto de um .env (None se a chave não existir). Ignora comentários."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, _, value = stripped.partition("=")
            if name.strip() == key:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                return value
    return None


def set_value(text: str, key: str, value: str) -> str:
    """Define KEY=value preservando o resto do arquivo (e o tipo de quebra de linha)."""
    nl, out, done = _newline(text), [], False
    for line in text.splitlines():
        stripped = line.strip()
        if not done and stripped and not stripped.startswith("#") and stripped.partition("=")[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    return nl.join(out) + nl


def _read(path: Path) -> str:
    """Lê preservando \r\n (read_text converteria) e tolerando o BOM do Bloco de Notas."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return fh.read()


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")       # sem BOM; newline="" preserva \r\n
    os.replace(tmp, path)


def ensure_env(env_path: Path | None = None, example_path: Path | None = None) -> dict:
    """Cria/completa o .env. Retorna o que foi feito (para o chamador informar a usuária)."""
    env_path = Path(env_path or ROOT / ".env")
    example_path = Path(example_path or ROOT / ".env.example")
    report = {"created_env": False, "secret_key_created": False, "password_created": None,
              "updated": {}, "development": True}

    if env_path.exists():
        text = _read(env_path)
    elif example_path.exists():
        text = _read(example_path)
        report["created_env"] = True
    else:
        text = "APP_ENV=development\nSECRET_KEY=\nDEV_ADMIN_NAME=\nDEV_ADMIN_EMAIL=\nDEV_ADMIN_PASSWORD=\n"
        report["created_env"] = True

    env = (get_value(text, "APP_ENV") or os.environ.get("APP_ENV") or "development").lower()
    if env != "development":
        report["development"] = False
        if report["created_env"]:
            _atomic_write(env_path, text)
        return report

    changed = report["created_env"]

    def fill(key, value):
        nonlocal text, changed
        text = set_value(text, key, value)
        report["updated"][key] = value
        changed = True

    if not (get_value(text, "SECRET_KEY") or "").strip():
        fill("SECRET_KEY", secrets.token_hex(32))
        report["secret_key_created"] = True
    for key, default in DEFAULTS.items():
        if not (get_value(text, key) or "").strip():
            fill(key, default)
    if not (get_value(text, "DEV_ADMIN_PASSWORD") or "").strip():
        password = secrets.token_urlsafe(12)                    # 16 caracteres, só A-Z a-z 0-9 - _
        fill("DEV_ADMIN_PASSWORD", password)
        report["password_created"] = password

    if changed:
        _atomic_write(env_path, text)
    return report


def find_free_port(start: int = 5000, host: str = "127.0.0.1", tries: int = 20) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) != 0:                 # ninguém escutando: porta livre
                return port
    return start


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "port":
        print(find_free_port())
        return 0
    if len(argv) > 1 and argv[1] == "info":
        text = _read(ROOT / ".env") if (ROOT / ".env").exists() else ""
        print(f"   Login (e-mail): {get_value(text, 'DEV_ADMIN_EMAIL') or '(veja o .env)'}")
        print("   Senha         : a definida em DEV_ADMIN_PASSWORD no arquivo .env")
        print("   Nao consegue entrar? Execute:  start.bat login   (aplica o login do .env)")
        return 0
    report = ensure_env()
    if report["created_env"]:
        print("[OK] Arquivo .env criado.")
    if report["secret_key_created"]:
        print("[OK] SECRET_KEY gerada e salva no .env (nao muda mais entre reinicios).")
    if report["password_created"]:
        print("[OK] Senha do administrador gerada e salva no .env (DEV_ADMIN_PASSWORD).")
        print(f"     E-mail: {get_value(_read(ROOT / '.env'), 'DEV_ADMIN_EMAIL')}")
        print(f"     Senha : {report['password_created']}")
        print("     Guarde esta senha; ela so e exibida agora (mas continua no .env).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
