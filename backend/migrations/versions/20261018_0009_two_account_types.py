"""two account types: standard and tbsz

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-18 18:00:00

Swiss, pension, savings, crypto and other were labels without behaviour; they all become standard.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE accounts SET account_type = 'standard' WHERE account_type NOT IN ('standard', 'tbsz')")


def downgrade() -> None:
    """Downgrade schema: the old labels are gone; standard is valid in the old schema too."""
