"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}
    
    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(
            """
            INSERT INTO "user" (username, email, phone_number, hashed_password, is_superuser, 
                               education_level, is_premium, commitment, balance, is_bot, 
                               bot_difficulty, signup_source)
            VALUES ('system', 'system@example.com', '21999202122', '', 
                    false, 'UNKNOWN', false, 0, 0, false,
                    NULL, 'OTHER'),
                    ('pico', 'pico@example.com', '21999202123', '', 
                    false, 'UNKNOWN', false, 0, 0, false,
                    NULL, 'OTHER'),
                    ('deleted', 'deleted@example.com', '21999202124', '', 
                    false, 'UNKNOWN', false, 0, 0, false,
                    NULL, 'OTHER');
            """
        )


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
    
    # Only drop types if it's the first migration
    if not down_revision:
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
