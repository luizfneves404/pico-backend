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

def drop_types() -> None:
    op.execute("DROP TYPE IF EXISTS educationlevel")
    op.execute("DROP TYPE IF EXISTS questiontype")
    op.execute("DROP TYPE IF EXISTS quiztype")
    op.execute("DROP TYPE IF EXISTS questionselectionmethod")
    op.execute("DROP TYPE IF EXISTS duelstatus")
    op.execute("DROP TYPE IF EXISTS duelturnphase")
    op.execute("DROP TYPE IF EXISTS tournamentstatus")
    op.execute("DROP TYPE IF EXISTS currencyaction")
    op.execute("DROP TYPE IF EXISTS currencytype")
    op.execute("DROP TYPE IF EXISTS signupsource")
    op.execute("DROP TYPE IF EXISTS devicetype")
    op.execute("DROP TYPE IF EXISTS flowinputtype")
    op.execute("DROP TYPE IF EXISTS questionsourcetype")
    op.execute("DROP TYPE IF EXISTS questionanswertype")
    op.execute("DROP TYPE IF EXISTS flowdifficulty")
    op.execute("DROP TYPE IF EXISTS questiondifficulty")

def upgrade() -> None:
    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        drop_types()

    ${upgrades if upgrades else "pass"}
    
    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(
            """
            INSERT INTO "user" (username, email, phone_number, hashed_password, is_superuser, 
                               is_premium, balance, is_bot, 
                               bot_difficulty, signup_source)
            VALUES ('system', 'system@example.com', '21999202122', '', 
                    false, false, 0, false,
                    NULL, 'OTHER'),
                    ('pico', 'pico@example.com', '21999202123', '', 
                    false, false, 0, false,
                    NULL, 'OTHER'),
                    ('deleted', 'deleted@example.com', '21999202124', '', 
                    false, false, 0, false,
                    NULL, 'OTHER');
            """
        )


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
    
    # Only drop types if it's the first migration
    if not down_revision:
        drop_types()
