"""update_flowquestionuser_constraint

Revision ID: c78668fc2756
Revises: dae8b1a51cbf
Create Date: 2025-05-27 10:38:33.240861

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c78668fc2756"
down_revision: Union[str, None] = "dae8b1a51cbf"
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
        op.f("ck__flow_question_user__check_flow_question_user_answer_valid_states"),
        "flow_question_user",
        type_="check",
    )

    # Add the updated constraint
    op.create_check_constraint(
        op.f("ck__flow_question_user__check_flow_question_user_answer_valid_states"),
        "flow_question_user",
        """
            (choice_id IS NOT NULL AND submitted_text = '') OR
            (choice_id IS NULL AND submitted_text != '') OR
            (choice_id IS NULL AND submitted_text = '')
            """,
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
    op.drop_constraint(
        op.f("ck__flow_question_user__check_flow_question_user_answer_valid_states"),
        "flow_question_user",
        type_="check",
    )

    # Add back the original constraint
    # Note: You should put the original constraint condition here
    op.create_check_constraint(
        op.f("ck__flow_question_user__check_flow_question_user_answer_valid_states"),
        "flow_question_user",
        """
            (choice_id IS NOT NULL AND submitted_text = '') OR
            (choice_id IS NULL AND submitted_text != '') OR
            (choice_id IS NULL AND submitted_text = '')
            """,
    )

    # Only drop types if it's the first migration
    if not down_revision:
        drop_types()
