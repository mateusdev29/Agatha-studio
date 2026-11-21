from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, TextAreaField
from wtforms.validators import InputRequired, Length, NumberRange, Optional, ValidationError

from app.extensions import db
from app.forms.choices import client_choices
from app.models import Appointment, Evaluation
from app.models.enums import AppointmentStatus
from app.utils.dates import today_local


class EvaluationForm(FlaskForm):
    client_id = SelectField("Cliente", coerce=int, validate_choice=True)
    appointment_id = SelectField("Atendimento", coerce=int, validate_choice=True)
    score = IntegerField("Nota (0 a 10)", validators=[InputRequired(message="Informe a nota."), NumberRange(min=0, max=10, message="Use uma nota de 0 a 10.")])
    comment = TextAreaField("Comentário", filters=[lambda v: v.strip() if isinstance(v, str) else v], validators=[Optional(), Length(max=3000)])
    evaluated_on = DateField("Data", format="%Y-%m-%d", validators=[InputRequired(message="Informe a data.")])

    def __init__(self, *args, current: Evaluation | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current = current
        self.client_id.choices = client_choices(current.client_id if current else None)
        taken = {a for (a,) in db.session.query(Evaluation.appointment_id).filter(Evaluation.appointment_id.isnot(None))}
        if current and current.appointment_id:
            taken.discard(current.appointment_id)
        appts = (Appointment.query.filter(Appointment.status == AppointmentStatus.DONE).order_by(Appointment.starts_at.desc()).limit(300).all())
        self.appointment_id.choices = [(0, "Sem atendimento específico", {})] + [
            (a.id, f"{a.starts_at:%d/%m/%Y} · {a.service or 'Atendimento'} ({a.client.name})", {"data-group": str(a.client_id)})
            for a in appts if a.id not in taken]

    def validate_evaluated_on(self, field):
        if field.data and not (2000 <= field.data.year <= 2100 and field.data <= today_local()):
            raise ValidationError("A data não pode ser futura.")

    def validate_appointment_id(self, field):
        if field.data:
            appt = db.session.get(Appointment, field.data)
            if appt and appt.client_id != self.client_id.data:
                raise ValidationError("O atendimento não pertence ao cliente escolhido.")

    def cleaned(self):
        d = self.data
        return {"client_id": d["client_id"], "appointment_id": d.get("appointment_id") or None, "score": d["score"],
                "comment": d.get("comment") or None, "evaluated_on": d["evaluated_on"]}
