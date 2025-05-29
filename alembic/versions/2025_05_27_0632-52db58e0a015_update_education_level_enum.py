"""
update_education_level_enum

Revision ID: 52db58e0a015
Revises: 26a31b8bb795
Create Date: 2025-05-27 06:32:31.175978
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "52db58e0a015"
down_revision = "26a31b8bb795"
branch_labels = None
depends_on = None


def drop_types() -> None:
    # keep your orphan-type cleanup helper
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


def _drop_existing_level_check(schema: str | None = None) -> None:
    # dynamically find and drop the existing CHECK constraint on level
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    checks = inspector.get_check_constraints("education", schema)
    for ck in checks:
        # match your naming convention or the text
        if "level" in ck["sqltext"]:
            op.drop_constraint(
                "education_level_check", "education", type_="check", schema=schema
            )
            break


def _create_level_check(schema: str | None = None) -> None:
    # create a new CHECK constraint using naming conventions
    # leave name=None to let the configured naming convention pick it up
    op.create_check_constraint(
        constraint_name="education_level_check",
        table_name="education",
        condition=sa.text(
            "level IN ('MIDDLE_SCHOOL', 'FIRST_GRADE_HIGH_SCHOOL', 'SECOND_GRADE_HIGH_SCHOOL', 'THIRD_GRADE_HIGH_SCHOOL', 'HIGH_SCHOOL_COMPLETE', 'COLLEGE', 'UNKNOWN')"
        ),
        schema=schema,
    )


def upgrade() -> None:
    # 2) drop the existing CHECK constraint
    _drop_existing_level_check()

    # 3) rename old enum, create new enum
    op.execute("ALTER TYPE educationlevel RENAME TO educationlevel_old")
    op.execute(
        "CREATE TYPE educationlevel AS ENUM ('MIDDLE_SCHOOL', 'FIRST_GRADE_HIGH_SCHOOL', 'SECOND_GRADE_HIGH_SCHOOL', 'THIRD_GRADE_HIGH_SCHOOL', 'HIGH_SCHOOL_COMPLETE', 'COLLEGE', 'UNKNOWN')"
    )

    # 4) conversion function
    op.execute("""
    CREATE OR REPLACE FUNCTION convert_education_level(old_level educationlevel_old) RETURNS educationlevel AS $$
    BEGIN
        IF old_level = 'FIRST_YEAR_HIGH_SCHOOL'::educationlevel_old THEN
            RETURN 'FIRST_GRADE_HIGH_SCHOOL'::educationlevel;
        ELSIF old_level = 'SECOND_YEAR_HIGH_SCHOOL'::educationlevel_old THEN
            RETURN 'SECOND_GRADE_HIGH_SCHOOL'::educationlevel;
        ELSIF old_level = 'THIRD_YEAR_HIGH_SCHOOL'::educationlevel_old THEN
            RETURN 'THIRD_GRADE_HIGH_SCHOOL'::educationlevel;
        ELSE
            RETURN old_level::text::educationlevel;
        END IF;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # 5) swap column
    op.add_column("education", sa.Column("level_new", sa.Enum(name="educationlevel")))
    op.execute(
        "UPDATE education SET level_new = convert_education_level(level::educationlevel_old)"
    )
    op.drop_column("education", "level")
    op.alter_column("education", "level_new", new_column_name="level")

    # 6) enforce NOT NULL
    op.alter_column("education", "level", nullable=False)

    # 7) recreate check constraint under naming convention
    _create_level_check()

    # 8) cleanup
    op.execute("DROP FUNCTION convert_education_level")
    op.execute("DROP TYPE educationlevel_old")


def downgrade() -> None:
    # drop check
    _drop_existing_level_check()

    # rename and recreate old enum
    op.execute("ALTER TYPE educationlevel RENAME TO educationlevel_old")
    op.execute(
        "CREATE TYPE educationlevel AS ENUM ('MIDDLE_SCHOOL', 'FIRST_YEAR_HIGH_SCHOOL', 'SECOND_YEAR_HIGH_SCHOOL', 'THIRD_YEAR_HIGH_SCHOOL', 'HIGH_SCHOOL_COMPLETE', 'COLLEGE', 'UNKNOWN')"
    )

    # conversion back
    op.execute("""
    CREATE OR REPLACE FUNCTION convert_education_level(old_level educationlevel_old) RETURNS educationlevel AS $$
    BEGIN
        IF old_level = 'FIRST_GRADE_HIGH_SCHOOL'::educationlevel_old THEN
            RETURN 'FIRST_YEAR_HIGH_SCHOOL'::educationlevel;
        ELSIF old_level = 'SECOND_GRADE_HIGH_SCHOOL'::educationlevel_old THEN
            RETURN 'SECOND_YEAR_HIGH_SCHOOL'::educationlevel;
        ELSIF old_level = 'THIRD_GRADE_HIGH_SCHOOL'::educationlevel_old THEN
            RETURN 'THIRD_YEAR_HIGH_SCHOOL'::educationlevel;
        ELSE
            RETURN old_level::text::educationlevel;
        END IF;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # swap back
    op.add_column("education", sa.Column("level_new", sa.Enum(name="educationlevel")))
    op.execute(
        "UPDATE education SET level_new = convert_education_level(level::educationlevel_old)"
    )
    op.drop_column("education", "level")
    op.alter_column("education", "level_new", new_column_name="level")

    # not null
    op.alter_column("education", "level", nullable=False)

    # recreate check
    _create_level_check()

    # cleanup
    op.execute("DROP FUNCTION convert_education_level")
    op.execute("DROP TYPE educationlevel_old")
