"""unaccent

Revision ID: 64e9b75604a9
Revises: 969f75920087
Create Date: 2025-09-01 13:25:54.696353

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "64e9b75604a9"
down_revision: str | None = "969f75920087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))

    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS unaccent"))

    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(
            """
            INSERT INTO "user" (username, name, email, phone_number, hashed_password, is_superuser, is_bot, bot_difficulty, signup_source, social_score, xp_score)
            VALUES ('deleted', 'deleted', 'deleted@example.com', '21999202124', '', false, false, NULL, 'OTHER', 0, 0);
            """
        )


def downgrade() -> None:
    op.execute(sa.text("DROP EXTENSION IF EXISTS unaccent"))
