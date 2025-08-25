"""
ARQ tasks for education-related operations.
"""

import logging
from typing import Any

from sqlalchemy import select, update

from app.database import get_db_session_for_worker
from app.education.models import Institution
from app.shared import openai_utils

logger = logging.getLogger(__name__)

INSTITUTION_BATCH_SIZE = 100


async def task_migrate_institutions_to_full_name(
    ctx: dict[str, Any],
    institution_ids: list[int] | None,
) -> None:
    """
    Copy current 'name' field to 'full_name' field for institutions.
    
    Args:
        ctx: ARQ worker context
        institution_ids: List of institution IDs to process, None means all institutions
    """
    async with get_db_session_for_worker(ctx) as session:
        if institution_ids is None:
            # Admin case: process all institutions
            condition = Institution.id.isnot(None)
            logger.info("Migrating all institutions to full_name format")
        else:
            # Specific institutions case
            condition = Institution.id.in_(institution_ids)
            logger.info(f"Migrating {len(institution_ids)} specific institutions to full_name format")

        # Update full_name = name for all matching institutions where full_name is empty
        stmt = (
            update(Institution)
            .where(condition & (Institution.full_name == ""))
            .values(full_name=Institution.name)
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        updated_count = result.rowcount
        logger.info(f"Successfully migrated {updated_count} institutions to full_name format")


async def task_determine_institution_display_names(
    ctx: dict[str, Any],
    institution_ids: list[int] | None,
) -> None:
    """
    Generate display names using OpenAI GPT-5-nano for institutions.
    
    Args:
        ctx: ARQ worker context
        institution_ids: List of institution IDs to process, None means all institutions
    """
    async with get_db_session_for_worker(ctx) as session:
        if institution_ids is None:
            # Admin case: process all institutions with non-empty full_name
            condition = (Institution.full_name != "") & (Institution.full_name.isnot(None))
        else:
            # Specific institutions case
            condition = Institution.id.in_(institution_ids)

        # First: fetch all matching IDs
        result = await session.execute(select(Institution.id).where(condition))
        all_ids: list[int] = list(result.scalars())

    num_institutions = len(all_ids)
    logger.info(f"Determining display names for {num_institutions} institutions using OpenAI")

    processed_count = 0
    
    # Process in batches to avoid overwhelming OpenAI API
    for batch_start in range(0, num_institutions, INSTITUTION_BATCH_SIZE):
        batch_ids = all_ids[batch_start : batch_start + INSTITUTION_BATCH_SIZE]

        async with get_db_session_for_worker(ctx) as session:
            stmt = (
                select(Institution)
                .where(Institution.id.in_(batch_ids))
            )
            result = await session.execute(stmt)
            institutions: list[Institution] = list(result.scalars())

            logger.info(
                f"Processing institution display names batch {batch_start // INSTITUTION_BATCH_SIZE + 1}. "
                f"We are at institution {batch_start + 1}."
            )

            # Process each institution individually to get better results
            for institution in institutions:
                if not institution.full_name or institution.full_name.strip() == "":
                    logger.warning(f"Institution {institution.id} has empty full_name, skipping")
                    continue
                
                try:
                    # Generate display name using OpenAI
                    display_name = await _generate_display_name(institution.full_name)
                    
                    # Update the institution
                    institution.name = display_name
                    logger.info(f"Updated institution {institution.id}: '{institution.full_name}' -> '{display_name}'")
                    
                except Exception as e:
                    logger.error(f"Error generating display name for institution {institution.id} ('{institution.full_name}'): {e}")
                    # Continue processing other institutions
                    continue

            await session.commit()
            processed_count += len(institutions)

    logger.info(f"Completed display name generation for {processed_count} institutions")


async def _generate_display_name(full_name: str) -> str:
    """
    Generate a shorter display name from the full institution name using OpenAI.
    
    Args:
        full_name: The full official name of the institution
        
    Returns:
        A shorter, more user-friendly display name
    """
    system_message = """You are an expert at creating concise, user-friendly display names for educational institutions.

Guidelines:
1. Keep display names SHORT (ideally under 50 characters)
2. Keep the most recognizable/important part of the name
3. Remove location details unless they're part of the institution's identity (e.g., "USP" not "Universidade de São Paulo")
4. Use common abbreviations when widely recognized (e.g., "UFRJ" instead of "Universidade Federal do Rio de Janeiro")
5. Maintain proper capitalization
6. Remove redundant words and legal terms
7. Focus on what users would commonly call the institution

Examples:
- "Universidade Federal do Rio de Janeiro" → "UFRJ"
- "Instituto Federal de Educação, Ciência e Tecnologia de São Paulo" → "IFSP"
- "Escola Estadual Professor João Silva" → "E.E. Prof. João Silva"
- "Centro Universitário das Faculdades Metropolitanas Unidas" → "FMU"
- "Universidade de São Paulo" → "USP"
- "Fundação Getúlio Vargas - São Paulo" → "FGV - SP"

Return ONLY the display name, nothing else."""

    try:
        response = await openai_utils.get_completion(
            model="gpt-5-nano",
            temperature=None,  # Use default for gpt-5-nano
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": full_name},
            ],
            json_mode=False,
            timeout=30,
        )
        
        display_name = response.strip()
        
        # Fallback: if OpenAI returns something too long or empty, use a simple truncation
        if not display_name or len(display_name) > 120:
            logger.warning(f"OpenAI returned invalid display name for '{full_name}': '{display_name}'. Using fallback.")
            # Simple fallback: take first 50 chars and try to end at a word boundary
            display_name = full_name[:50].rsplit(' ', 1)[0] if ' ' in full_name[:50] else full_name[:50]
        
        return display_name
        
    except Exception as e:
        logger.error(f"Error calling OpenAI for display name generation: {e}")
        # Fallback: simple truncation
        display_name = full_name[:50].rsplit(' ', 1)[0] if ' ' in full_name[:50] else full_name[:50]
        return display_name
