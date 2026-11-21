"""limitador persistente de tentativas de login por navegador

Revision ID: b6138d9e2aa1
Revises: a4b7bb239715
Create Date: 2026-11-21 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b6138d9e2aa1"
down_revision = "a4b7bb239715"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_throttles",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("blocked_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key_hash"),
    )
    op.create_index("ix_login_throttles_updated_at", "login_throttles", ["updated_at"], unique=False)


def downgrade():
    op.drop_index("ix_login_throttles_updated_at", table_name="login_throttles")
    op.drop_table("login_throttles")
