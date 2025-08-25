"""
ARQ tasks for education-related operations.
"""

import asyncio
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

            # Process each institution sequentially within the batch (like embeddings task)
            for institution in institutions:
                if not institution.full_name or institution.full_name.strip() == "":
                    logger.warning(f"Institution {institution.id} has empty full_name, skipping")
                    continue
                
                try:
                    logger.info(f"Processing institution {institution.id}: '{institution.full_name}'")
                    
                    # Generate display name using OpenAI
                    display_name = await _generate_display_name(institution.full_name)
                    
                    # Update the institution
                    old_name = institution.name
                    institution.name = display_name
                    logger.info(f"✅ Updated institution {institution.id}: '{old_name}' -> '{display_name}'")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing institution {institution.id} ('{institution.full_name}'): {e}")
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
    system_message = """You are an expert at creating concise, user-friendly display names for Brazilian educational institutions while preserving their core identity and recognition.

CORE PRINCIPLE: Preserve the institution's recognizable identity and meaning while making it shorter and more user-friendly.

Guidelines:
1. PRESERVE MEANING: Never sacrifice the institution's core identity for brevity
2. Keep display names SHORT but MEANINGFUL (ideally under 60 characters, max 80)
3. Use well-known abbreviations ONLY when they are widely recognized by students/parents
4. Keep important institutional identifiers (Federal, Estadual, Instituto, etc.) when they matter for recognition
5. Preserve professor names, founders, or distinctive identifiers that make the institution unique
6. Remove only truly redundant words like "de Educação", "Ciência e Tecnologia" in long technical names
7. For schools with person names, keep the name but can abbreviate titles (Prof., Dr.)
8. Location can be abbreviated but not removed if it's part of the identity

DECISION PROCESS:
- Ask: "What would students/parents call this institution?"
- Ask: "What makes this institution unique and recognizable?"
- Ask: "Will people still know what institution this is?"

Examples:
- "Universidade Federal do Rio de Janeiro" → "UFRJ" (widely known abbreviation)
- "Universidade Federal de Minas Gerais" → "UFMG" (widely known abbreviation)
- "Instituto Federal de Educação, Ciência e Tecnologia de São Paulo" → "Instituto Federal de SP" (preserve identity, simplify)
- "Escola Estadual Professor João Silva" → "E.E. Prof. João Silva" (preserve person's name)
- "Centro Universitário das Faculdades Metropolitanas Unidas" → "FMU" (known by abbreviation)
- "Universidade de São Paulo" → "USP" (universally known)
- "Fundação Getúlio Vargas - São Paulo" → "FGV - SP" (preserve founder, location)
- "Colégio Santo Agostinho" → "Colégio Santo Agostinho" (keep if already short and meaningful)
- "Universidade Católica de Brasília" → "UCB" (if widely known) OR "Univ. Católica de Brasília" (if abbreviation not common)

AVOID:
- Creating abbreviations that nobody would recognize
- Removing distinctive elements that identify the institution
- Making names so short they become meaningless
- Changing well-established names that are already user-friendly

Return ONLY the display name, nothing else."""

    try:
        logger.info(f"🤖 Calling OpenAI GPT-5-nano for display name generation")
        logger.debug(f"Input full_name: '{full_name}'")
        
        response = await openai_utils.get_completion(
            model="gpt-5-nano",
            temperature=None,  # No temperature for nano
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": full_name},
            ],
            json_mode=False,
            timeout=15,  # Shorter timeout for nano
        )
        
        logger.info(f"✅ OpenAI response received - Tokens used: {response.tokens_used}")
        logger.info(f"🎯 Raw OpenAI output: '{response.content}'")
        
        display_name = response.content.strip()
        logger.info(f"📝 After strip(): '{display_name}'")
        
        # Fallback: if OpenAI returns something too long or empty, use a simple truncation
        if not display_name or len(display_name) > 120:
            logger.warning(f"⚠️ OpenAI returned invalid display name (empty or too long): '{display_name}' (length: {len(display_name) if display_name else 0}). Using fallback.")
            # Simple fallback: take first 80 chars and try to end at a word boundary
            display_name = full_name[:80].rsplit(' ', 1)[0] if ' ' in full_name[:80] else full_name[:80]
            logger.info(f"🔄 Fallback display name: '{display_name}'")
        else:
            logger.info(f"✨ Valid display name generated: '{display_name}' (length: {len(display_name)})")
        
        return display_name
        
    except Exception as e:
        logger.error(f"❌ Error calling OpenAI for display name generation: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        # Fallback: simple truncation
        display_name = full_name[:80].rsplit(' ', 1)[0] if ' ' in full_name[:80] else full_name[:80]
        logger.info(f"🔄 Exception fallback display name: '{display_name}'")
        return display_name
