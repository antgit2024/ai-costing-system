"""merge heads: 0019_taxonomy_management + 0754ad7d6c3f

Revision ID: 0020_merge_heads_0019_and_stub
Revises: 0019_taxonomy_management, 0754ad7d6c3f
Create Date: 2025-12-27 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "0020_merge_heads_0019_and_stub"
down_revision = ("0019_taxonomy_management", "0754ad7d6c3f")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge revision: no-op
    pass


def downgrade() -> None:
    # Merge revision: no-op
    pass


