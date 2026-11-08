"""encrypted integration secrets editable from Settings

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('integration_secrets',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('ciphertext', sa.Text(), nullable=False),
    sa.Column('updated_by', sa.String(length=64), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )


def downgrade() -> None:
    op.drop_table('integration_secrets')
