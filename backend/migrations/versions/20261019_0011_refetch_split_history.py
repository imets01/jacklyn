"""refetch split history

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-19 12:00:00

0010 fetched splits only from each asset's first trade then known, so splits before later-imported older trades
(GOOGL and TSLA in 2022 for a Revolut history from 2021) were missed. Clearing the marker makes the next price
refresh fetch every asset's complete split history once.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE assets SET splits_through = NULL")


def downgrade() -> None:
    """Downgrade schema: nothing to undo; the next refresh simply fetched the history again."""
