"""DADOS DE DEMONSTRAÇÃO — só para desenvolvimento. Nunca rodam em produção.

Tudo aqui é fictício e marcado com "[DEMO]" nas observações dos clientes. As datas são
relativas a hoje, para a agenda sempre parecer viva. Execute: flask seed-demo
"""
from datetime import datetime, time, timedelta

from app.extensions import db
from app.models import (Appointment, BodyRegion, Category, Client, Evaluation, FinancialTransaction, InventoryItem,
                        Project, ProjectSession, Quote, StudioSetting)
from app.models.enums import (AppointmentStatus as A, CategoryKind, PaymentMethod as PM, ProjectStatus as P,
                              QuoteStatus as Q, SessionStatus, TransactionStatus as TS, TransactionType as TT)
from app.utils.dates import today_local

MARK = "[DEMO] Dados de demonstração."


class AlreadySeeded(Exception):
    pass


def _at(days, hour, minute=0):
    return datetime.combine(today_local() + timedelta(days=days), time(hour, minute))


def seed_demo() -> dict:
    if db.session.get(StudioSetting, "demo_data"):
        raise AlreadySeeded("Os dados de demonstração já foram criados.")
    today = today_local()
    region = {r.slug: r.id for r in BodyRegion.query}
    cat = {(c.kind, c.name): c.id for c in Category.query}

    clients = [Client(name=n, phone=ph, instagram=ig, email=em, source=src, notes=MARK) for n, ph, ig, em, src in [
        ("Marina Lopes", "(71) 98800-1001", "marina.lopes", "marina@exemplo.com", "Instagram"),
        ("Caio Ferraz", "(71) 98800-1002", "caioferraz.ink", None, "Indicação"),
        ("Beatriz Nunes", "(71) 98800-1003", None, "bia.nunes@exemplo.com", "WhatsApp"),
        ("Rafael Duarte", "(71) 98800-1004", "rafa.duarte", None, "Instagram"),
        ("Helena Prado", "(71) 98800-1005", None, "helena@exemplo.com", "Site")]]
    db.session.add_all(clients)
    db.session.flush()
    marina, caio, bea, rafa, helena = clients

    projects = [
        Project(client_id=marina.id, name="Floral no antebraço", style="Fine line", body_region_id=region["antebraco"], size="15 cm", price_cents=120000, status=P.IN_PROGRESS),
        Project(client_id=caio.id, name="Leão realista", style="Realismo", body_region_id=region["costas"], size="30 cm", price_cents=480000, status=P.APPROVED),
        Project(client_id=bea.id, name="Mandala no ombro", style="Pontilhismo", body_region_id=region["ombro"], size="12 cm", price_cents=90000, status=P.QUOTE),
        Project(client_id=rafa.id, name="Frase manuscrita", style="Lettering", body_region_id=region["costelas"] if "costelas" in region else region["peito"], size="10 cm", price_cents=35000, status=P.DONE),
        Project(client_id=helena.id, name="Fechamento de braço", style="Blackwork", body_region_id=region["braco"], price_cents=220000, status=P.IN_PROGRESS)]
    db.session.add_all(projects)
    db.session.flush()
    floral, leao, mandala, frase, fechamento = projects
    db.session.add_all([
        ProjectSession(project_id=floral.id, scheduled_at=_at(-9, 14), duration_minutes=180, price_cents=60000, status=SessionStatus.DONE, notes="Contorno"),
        ProjectSession(project_id=floral.id, scheduled_at=_at(0, 14), duration_minutes=180, price_cents=60000, status=SessionStatus.SCHEDULED),
        ProjectSession(project_id=fechamento.id, scheduled_at=_at(7, 11), duration_minutes=240, price_cents=110000, status=SessionStatus.SCHEDULED)])

    def appt(client, start, dur, status, service, price, deposit=0, project=None):
        a = Appointment(client_id=client.id, project_id=project.id if project else None, starts_at=start, duration_minutes=dur,
                        status=status, service=service, price_cents=price, deposit_cents=deposit)
        db.session.add(a)
        return a

    appts = [
        appt(marina, _at(0, 14), 180, A.CONFIRMED, "Sessão de tatuagem", 60000, 15000, floral),
        appt(helena, _at(0, 18), 60, A.WAITING, "Consulta / Orçamento", 0),
        appt(bea, _at(1, 10), 60, A.WAITING, "Consulta / Orçamento", 0, project=mandala),
        appt(caio, _at(3, 15), 240, A.CONFIRMED, "Sessão de tatuagem", 160000, 40000, leao),
        appt(helena, _at(7, 11), 240, A.WAITING, "Sessão de tatuagem", 110000, 20000, fechamento),
        appt(rafa, _at(-2, 10), 90, A.DONE, "Sessão de tatuagem", 35000, 10000, frase),
        appt(marina, _at(-9, 14), 180, A.DONE, "Sessão de tatuagem", 60000, 15000, floral),
        appt(bea, _at(-5, 13), 60, A.CANCELED, "Retoque", 15000)]
    db.session.flush()

    db.session.add_all([
        Quote(client_id=bea.id, description="Mandala pontilhista no ombro", style="Pontilhismo", body_region_id=region["ombro"], size="12 cm", price_cents=90000, valid_until=today + timedelta(days=10), status=Q.WAITING),
        Quote(client_id=rafa.id, description="Rosa fine line na panturrilha", style="Fine line", body_region_id=region["panturrilha"], price_cents=45000, valid_until=today + timedelta(days=2), status=Q.SENT),
        Quote(client_id=helena.id, description="Cobertura de tatuagem antiga", style="Cobertura", body_region_id=region["coxa"], price_cents=150000, valid_until=today + timedelta(days=15), status=Q.DRAFT),
        Quote(client_id=caio.id, description="Leão realista nas costas", style="Realismo", body_region_id=region["costas"], size="30 cm", price_cents=480000, valid_until=today + timedelta(days=5), status=Q.APPROVED, project_id=leao.id),
        Quote(client_id=marina.id, description="Pequeno símbolo no pulso", style="Fine line", price_cents=30000, valid_until=today - timedelta(days=12), status=Q.REJECTED)])

    def money(kind, desc, cents, days, category, status=TS.PAID, **kw):
        db.session.add(FinancialTransaction(type=kind, description=desc, amount_cents=cents, date=today + timedelta(days=days),
                                            category_id=cat.get((CategoryKind.INCOME if kind == TT.INCOME else CategoryKind.EXPENSE, category)),
                                            status=status, **kw))
    money(TT.INCOME, "Sinal: Floral", 15000, -20, "Sinal / Entrada", client_id=marina.id, project_id=floral.id, payment_method=PM.PIX)
    money(TT.INCOME, "Sessão 1: Floral", 45000, -9, "Tatuagem", client_id=marina.id, project_id=floral.id, payment_method=PM.CARD)
    money(TT.INCOME, "Frase manuscrita", 35000, -2, "Tatuagem", client_id=rafa.id, project_id=frase.id, payment_method=PM.PIX)
    money(TT.INCOME, "Sinal: Leão", 40000, -4, "Sinal / Entrada", client_id=caio.id, project_id=leao.id, payment_method=PM.TRANSFER)
    money(TT.INCOME, "Restante: Floral", 60000, 0, "Tatuagem", status=TS.PENDING, client_id=marina.id, project_id=floral.id)
    money(TT.EXPENSE, "Agulhas e cartuchos", 28000, -12, "Materiais", supplier="Tattoo Supply", payment_method=PM.PIX)
    money(TT.EXPENSE, "Aluguel do estúdio", 150000, -3, "Aluguel", payment_method=PM.TRANSFER)
    money(TT.EXPENSE, "Impulsionamento Instagram", 20000, -6, "Marketing", payment_method=PM.CARD)

    inv = lambda n, c, q, mn, u, cost, **kw: db.session.add(InventoryItem(name=n, category_id=cat.get((CategoryKind.INVENTORY, c)), quantity=q, min_quantity=mn, unit=u, cost_cents=cost, **kw))
    inv("Agulha 3RL", "Agulhas", 4, 20, "un", 450, supplier="Tattoo Supply")
    inv("Tinta preta 30ml", "Tintas", 6, 3, "un", 6500, supplier="Ink Brasil", expires_on=today + timedelta(days=20))
    inv("Luvas nitrílicas", "Descartáveis", 80, 50, "un", 120, supplier="MedPlus")
    inv("Filme plástico", "Descartáveis", 2, 2, "rolo", 3200)
    inv("Álcool 70%", "Higienização", 9, 4, "un", 1100)

    appts_done = [a for a in appts if a.status == A.DONE]
    for a, (score, comment) in zip(appts_done, [(10, "Atendimento impecável, amei o resultado!"), (9, "Muito cuidado e atenção.")]):
        db.session.add(Evaluation(client_id=a.client_id, appointment_id=a.id, score=score, comment=comment, evaluated_on=a.starts_at.date()))
    db.session.add(Evaluation(client_id=helena.id, score=7, comment="Gostei, mas atrasou um pouco.", evaluated_on=today - timedelta(days=30)))

    db.session.add(StudioSetting(key="demo_data", value="1"))
    db.session.commit()
    return {"clientes": 5, "projetos": 5, "agendamentos": 8, "orçamentos": 5, "receitas": 5, "despesas": 3, "produtos": 5, "avaliações": 3}
