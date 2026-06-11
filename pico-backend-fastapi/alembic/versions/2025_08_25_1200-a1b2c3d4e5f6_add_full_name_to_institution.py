"""add full_name to institution

Revision ID: a1b2c3d4e5f6
Revises: 1816ace8ae2f
Create Date: 2025-08-25 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "1816ace8ae2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add the full_name column to institution table
    op.add_column(
        "institution",
        sa.Column(
            "full_name", sa.String(length=500), nullable=False, server_default=""
        ),
    )

    # Remove the server default after adding the column
    op.alter_column("institution", "full_name", server_default=None)


def downgrade() -> None:
    # Remove the full_name column
    op.drop_column("institution", "full_name")
