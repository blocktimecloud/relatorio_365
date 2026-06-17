"""create_customers_table

Revision ID: e23b4fff1264
Revises: 
Create Date: 2026-06-03 12:34:29.943474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'e23b4fff1264'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'customers',
        sa.Column('id',            mysql.CHAR(length=36),  nullable=False),
        sa.Column('name',          sa.String(length=255),  nullable=False),
        sa.Column('contact_email', sa.String(length=255),  nullable=True),
        sa.Column('active',        sa.Boolean(),           nullable=False, server_default='1'),
        sa.Column('created_at',    sa.DateTime(),          nullable=False, server_default=sa.func.now()),
        sa.Column('tenant_id',     mysql.CHAR(length=36),  nullable=False),
        sa.Column('client_id',     mysql.CHAR(length=36),  nullable=False),
        sa.Column('client_secret', sa.Text(),              nullable=False,
                  comment='Valor criptografado com Fernet — nunca armazenado em texto claro'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_customers_id'), 'customers', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_customers_id'), table_name='customers')
    op.drop_table('customers')