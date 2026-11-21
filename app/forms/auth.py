from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    # Sem validador de formato de e-mail aqui: erro de login é sempre genérico.
    email = StringField("E-mail", validators=[DataRequired(message="Informe o e-mail."), Length(max=254)])
    password = PasswordField("Senha", validators=[DataRequired(message="Informe a senha."), Length(max=256)])
    remember = BooleanField("Manter conectada")
