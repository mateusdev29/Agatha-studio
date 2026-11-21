"""Instâncias das extensões, criadas aqui para evitar imports circulares."""
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
# render_as_batch: necessário para ALTER TABLE no SQLite
migrate = Migrate(render_as_batch=True)
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar o sistema."
login_manager.login_message_category = "info"
# "basic": mantém a sessão mesmo se o IP/navegador mudar (Wi-Fi para 4G, proxy, túnel). Com "strong" o
# Flask-Login deslogava a usuária a cada troca de rede, que no celular é comum. O cookie continua
# HttpOnly + SameSite (+ Secure em produção) e o login tem bloqueio contra força bruta.
login_manager.session_protection = "basic"
