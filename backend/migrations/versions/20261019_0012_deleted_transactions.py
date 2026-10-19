"""deleted transactions

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19 18:00:00

Broker rows the user deleted by hand, remembered so re-importing a statement or the next sync doesn't bring them back.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.db.types


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('deleted_transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('buy', 'sell', 'dividend', 'interest', 'fee', 'tax', 'deposit', 'withdrawal', 'fx_conversion', 'transfer_in', 'transfer_out', name='transactiontype', native_enum=False, length=32), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('external_id', sa.String(length=128), nullable=True),
    sa.Column('dedup_hash', sa.String(length=64), nullable=False),
    sa.Column('deleted_at', app.db.types.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_deleted_transactions_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_deleted_transactions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deleted_transactions')),
    sa.UniqueConstraint('account_id', 'dedup_hash', name=op.f('uq_deleted_transactions_account_id_dedup_hash'))
    )
    with op.batch_alter_table('deleted_transactions', schema=None) as batch_op:
        batch_op.create_index('ix_deleted_transactions_account_external_id', ['account_id', 'external_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_deleted_transactions_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('deleted_transactions')
