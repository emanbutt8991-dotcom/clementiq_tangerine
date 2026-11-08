"""Snowflake Cortex analysis fields on news_events; widen location_basis

location_basis held up to 83 characters (GDELT basis text) in a VARCHAR(48), which SQLite
ignores but PostgreSQL / Tiger Data rejects.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08 13:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('news_events', schema=None) as batch_op:
        batch_op.alter_column('location_basis', existing_type=sa.String(length=48), type_=sa.String(length=200),
                              existing_nullable=True)
        batch_op.add_column(sa.Column('cortex_topic', sa.String(length=48), nullable=True))
        batch_op.add_column(sa.Column('cortex_confidence', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('cortex_injection_detected', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('cortex_relevant', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('cortex_model', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('cortex_request_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('cortex_analysis', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('news_events', schema=None) as batch_op:
        for c in ('cortex_analysis', 'cortex_request_id', 'cortex_model', 'cortex_relevant',
                  'cortex_injection_detected', 'cortex_confidence', 'cortex_topic'):
            batch_op.drop_column(c)
        batch_op.alter_column('location_basis', existing_type=sa.String(length=200), type_=sa.String(length=48),
                              existing_nullable=True)
