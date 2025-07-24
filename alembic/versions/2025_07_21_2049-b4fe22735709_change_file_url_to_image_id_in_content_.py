"""change_file_url_to_image_id_in_content_blocks

Revision ID: b4fe22735709
Revises: 0c9931af6475
Create Date: 2025-07-21 20:49:06.406169

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4fe22735709"
down_revision: Union[str, None] = "0c9931af6475"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))

    # Migration to convert file_url to image_id in content_blocks and answer_content_blocks
    # This migration handles the conversion from file_url (string) to image_id (integer)
    # Since we can't reliably map URLs to IDs without additional context,
    # we'll update any existing records with file_url to use a default image_id of 1
    # Users will need to manually update these records with the correct image_id values

    # Update content_blocks
    op.execute(
        sa.text(
            """
        UPDATE question
        SET content_blocks = (
            SELECT json_agg(
                CASE 
                    WHEN block->>'block_type' = 'image' AND block::jsonb ? 'file_url'
                    THEN json_build_object(
                        'block_type', block->>'block_type',
                        'image_id', 1,
                        'alt', block->>'alt'
                    )
                    ELSE block
                END
            )
            FROM json_array_elements(content_blocks) AS block
        )
        WHERE content_blocks::text LIKE '%file_url%';
    """
        )
    )

    # Update answer_content_blocks
    op.execute(
        sa.text(
            """
        UPDATE question
        SET answer_content_blocks = (
            SELECT json_agg(
                CASE 
                    WHEN block->>'block_type' = 'image' AND block::jsonb ? 'file_url'
                    THEN json_build_object(
                        'block_type', block->>'block_type',
                        'image_id', 1,
                        'alt', block->>'alt'
                    )
                    ELSE block
                END
            )
            FROM json_array_elements(answer_content_blocks) AS block
        )
        WHERE answer_content_blocks::text LIKE '%file_url%';
    """
        )
    )

    # Only execute this code if it's the first migration
    if not down_revision:
        op.execute(
            """
            INSERT INTO "user" (username, name, email, phone_number, hashed_password, is_superuser, is_bot, bot_difficulty, signup_source, social_score, xp_score)
            VALUES ('deleted', 'deleted', 'deleted@example.com', '21999202124', '', false, false, NULL, 'OTHER', 0, 0);
            """
        )


def downgrade() -> None:
    # Reverting the migration is complex since we don't store the original file_url values
    # This downgrade will convert image_id back to a placeholder file_url
    # Note: Original file URLs are lost and would need to be manually restored

    # Revert content_blocks
    op.execute(
        sa.text(
            """
        UPDATE question
        SET content_blocks = (
            SELECT json_agg(
                CASE 
                    WHEN block->>'block_type' = 'image' AND block::jsonb ? 'image_id'
                    THEN json_build_object(
                        'block_type', block->>'block_type',
                        'file_url', 'https://via.placeholder.com/150',
                        'alt', block->>'alt'
                    )
                    ELSE block
                END
            )
            FROM json_array_elements(content_blocks) AS block
        )
        WHERE content_blocks::text LIKE '%image_id%';
    """
        )
    )

    # Revert answer_content_blocks
    op.execute(
        sa.text(
            """
        UPDATE question
        SET answer_content_blocks = (
            SELECT json_agg(
                CASE 
                    WHEN block->>'block_type' = 'image' AND block::jsonb ? 'image_id'
                    THEN json_build_object(
                        'block_type', block->>'block_type',
                        'file_url', 'https://via.placeholder.com/150',
                        'alt', block->>'alt'
                    )
                    ELSE block
                END
            )
            FROM json_array_elements(answer_content_blocks) AS block
        )
        WHERE answer_content_blocks::text LIKE '%image_id%';
    """
        )
    )
