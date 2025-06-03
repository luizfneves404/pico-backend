"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.base
import pgvector.sqlalchemy
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

def upgrade() -> None:
    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    ${upgrades if upgrades else "pass"}
    
    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(
            """
            INSERT INTO "user" (username, name, email, phone_number, hashed_password, is_superuser, is_bot, bot_difficulty, signup_source)
            VALUES ('deleted', 'deleted', 'deleted@example.com', '21999202124', '', false, false, NULL, 'OTHER');
            """
        )


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
