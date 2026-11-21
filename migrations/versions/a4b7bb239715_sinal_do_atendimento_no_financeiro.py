"""sinal do atendimento no financeiro

Revision ID: a4b7bb239715
Revises: 9a714bbdb957
Create Date: 2026-10-04 18:38:53.877277

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b7bb239715'
down_revision = '9a714bbdb957'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('financial_transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('appointment_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('is_deposit', sa.Boolean(), server_default=sa.text('0'), nullable=False))
        batch_op.create_index(batch_op.f('ix_financial_transactions_appointment_id'), ['appointment_id'], unique=False)
        batch_op.create_index('uq_deposit_per_appointment', ['appointment_id'], unique=True, sqlite_where=sa.text('is_deposit = 1'))
        batch_op.create_foreign_key('fk_financial_transactions_appointment', 'appointments', ['appointment_id'], ['id'])



def downgrade():
    with op.batch_alter_table('financial_transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_financial_transactions_appointment', type_='foreignkey')
        batch_op.drop_index('uq_deposit_per_appointment', sqlite_where=sa.text('is_deposit = 1'))
        batch_op.drop_index(batch_op.f('ix_financial_transactions_appointment_id'))
        batch_op.drop_column('is_deposit')
        batch_op.drop_column('appointment_id')

