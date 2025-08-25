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

            # Process institutions concurrently within the batch to improve throughput.
            # Limit concurrency so we don't overwhelm OpenAI or the event loop.
            concurrency = 20
            semaphore = asyncio.Semaphore(concurrency)

            async def _gen_for_institution(inst: Institution) -> tuple[int, str | None]:
                if not inst.full_name or inst.full_name.strip() == "":
                    return (inst.id, None)
                async with semaphore:
                    try:
                        display_name = await _generate_display_name(inst.full_name)
                    except Exception:
                        # Safe fallback: simple truncation
                        fn = inst.full_name
                        display_name = fn[:80].rsplit(" ", 1)[0] if " " in fn[:80] else fn[:80]
                    return (inst.id, display_name)

            tasks = [_gen_for_institution(inst) for inst in institutions]
            results = await asyncio.gather(*tasks)

            # Apply updates for the batch and commit once per batch (every ~100 institutions)
            for inst_id, display_name in results:
                if not display_name:
                    continue
                stmt = (
                    update(Institution)
                    .where(Institution.id == inst_id)
                    .values(name=display_name)
                )
                await session.execute(stmt)

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
    system_message = """You are an expert at producing concise, user-friendly display names for Brazilian educational institutions while preserving their core identity and recognition.

CORE PRINCIPLE: Preserve the institution's recognizable identity and meaning while shortening very long formal names into a clearly recognizable label when appropriate.

Heuristics to apply (use these as decision rules):
- If the official name is short (3 words or fewer) or already clearly recognizable, just return it with the right formatting.
- If the official name is long (more than 5 words) or contains long generic phrases such as "Escola de Educação Básica e Profissional", "Centro Universitário das Faculdades", or "Instituto Federal de Educação, Ciência e Tecnologia de ...", extract the most distinctive, recognizable entity (often the sponsoring organization or the unique noun phrase). Example: "Escola de Educação Básica e Profissional da Fundação Bradesco" → "Fundação Bradesco". In some cases, those names might compose recognizable acronyms, like "UFRJ" or "UFMG" - in which case you should return the acronym.
- Preserve personal names and unique identifiers; if the name is primarily a person's name, keep the personal name and shorten surrounding titles (e.g. "Escola Estadual Professor João Silva" → "E.E. Prof. João Silva").
- Avoid producing ambiguous or lossy abbreviations. Prefer clarity over aggressive shortening.
- Keep short, distinctive names intact (e.g. "Escola Parque" should remain "Escola Parque", not "Parque").

Examples:
- "Universidade de São Paulo" → "USP" (universally known)
- "Fundação Getúlio Vargas - São Paulo" → "FGV - SP"
- "Escola de Educação Básica e Profissional da Fundação Bradesco" → "Fundação Bradesco"
- "Escola Parque" → "Escola Parque"
- "Colégio Santo Agostinho" → "Colégio Santo Agostinho" (keep if already short and meaningful)
- "Universidade Católica de Brasília" → "UCB" (if widely known) OR "Univ. Católica de Brasília" (if abbreviation not common)


Formatting:
- Return ONLY the display name as a single string, no explanation, no punctuation or extra characters.
- Aim for under 60 characters, up to 80 only if necessary to preserve identity.
"""

    try:
        logger.info(f"🤖 Calling OpenAI GPT-5-nano for display name generation")
        logger.debug(f"Input full_name: '{full_name}'")
        
        # Use a concrete temperature value; some OpenAI wrappers require it even for 'nano' models.
        response = await openai_utils.get_completion(
            model="gpt-5-nano",
            temperature=1.0,
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
