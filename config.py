"""Configuração da aplicação. Segredos vêm SEMPRE de variáveis de ambiente."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Deve rodar ANTES das classes abaixo: elas leem os.environ ao serem definidas.
# Variáveis já definidas no ambiente real têm prioridade sobre o .env.
load_dotenv(BASE_DIR / ".env", encoding="utf-8-sig")   # utf-8-sig: o Bloco de Notas do Windows grava BOM


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")  # validado em create_app()
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        f"sqlite:///{(BASE_DIR / 'instance' / 'studio.db').as_posix()}"   # as_posix: seguro em caminhos do Windows
    )
    ENV_FILE = str(BASE_DIR / ".env")
    MIGRATIONS_DIR = str(BASE_DIR / "migrations")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Sessão / cookies. Nomes próprios: cookies não isolam por porta, então outro app Flask em
    # 127.0.0.1 (ex.: o site público) com o nome padrão "session" invalidaria este login.
    SESSION_COOKIE_NAME = "agatha_studio_session"
    REMEMBER_COOKIE_NAME = "agatha_studio_remember"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 h

    # Uploads (usados a partir da Fase 3)
    UPLOAD_FOLDER = str(BASE_DIR / "uploads")
    MAX_CONTENT_LENGTH = 24 * 1024 * 1024  # 24 MB por requisição (vários arquivos)
    ALLOWED_IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})
    MAX_UPLOAD_FILE_BYTES = 6 * 1024 * 1024   # por imagem
    MAX_IMAGE_PIXELS = 40_000_000             # protege contra "decompression bomb"
    MAX_REFERENCES_PER_PROJECT = 12
    IMAGE_MAX_SIDE = 2400                     # lado maior da imagem guardada
    THUMBNAIL_SIDE = 480

    # Proteção contra força bruta no login
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15
    MAX_DEVICE_FAILED_LOGINS = 5
    DEVICE_LOGIN_WINDOW_MINUTES = 15
    DEVICE_LOCKOUT_MINUTES = 15

    QUOTE_VALIDITY_DAYS = 15                  # validade padrão de um orçamento novo
    STUDIO_NAME = "Agatha Souza Tattoo Studio"

    # Fuso do estúdio (horários de agenda são guardados como horário local)
    STUDIO_TIMEZONE = "America/Bahia"

    REQUIRE_SECRET_KEY = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    REQUIRE_SECRET_KEY = True


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-only-key-not-a-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
