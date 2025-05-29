"""update_flowelement_constraint

Revision ID: dae8b1a51cbf
Revises: 52db58e0a015
Create Date: 2025-05-27 06:58:32.428602

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dae8b1a51cbf"
down_revision: Union[str, None] = "52db58e0a015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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

    # Drop the existing constraint
    op.drop_constraint(
        "ck_flowelement_exactly_one_payload", "flow_element", type_="check"
    )

    # Add the updated constraint
    op.create_check_constraint(
        "ck_flowelement_exactly_one_payload",
        "flow_element",
        "(element_type = 'flow_question' AND question_id IS NOT NULL)",
    )

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
    # Drop the new constraint
    op.drop_constraint(
        "ck_flowelement_exactly_one_payload", "flow_element", type_="check"
    )

    # Add back the original constraint
    # Note: You should put the original constraint condition here
    op.create_check_constraint(
        "ck_flowelement_exactly_one_payload",
        "flow_element",
        "(element_type = 'flow_question' AND question_id IS NOT NULL)",
    )

    # Only drop types if it's the first migration
    if not down_revision:
        drop_types()
