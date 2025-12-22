"""stub: restore missing revision referenced by remote DB (do not extend scope)

Revision ID: 0754ad7d6c3f
Revises: 0006_yida_sync_jobs
Create Date: 2025-12-22 00:30:00.000000

Why:
- The target environment (47.99.89.206) already has `0754ad7d6c3f` recorded in `alembic_version`,
  but the migration file was not present in this repo, causing `alembic upgrade` to fail with:
  "Can't locate revision identified by '0754ad7d6c3f'".
- This stub is a no-op to make Alembic able to build the revision graph and continue applying new
  migrations (e.g. shipment import MVP) using `alembic upgrade heads`.

Note:
- If you need to recreate a fresh DB from scratch, you must recover the original content of
  `0754ad7d6c3f` (or replace it with a proper merge/linearized migration strategy). This file
  exists only to unblock deployments on environments that already applied that revision.
"""

from __future__ import annotations


revision = "0754ad7d6c3f"
down_revision = "0006_yida_sync_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # no-op
    return None


def downgrade() -> None:
    # no-op
    return None


