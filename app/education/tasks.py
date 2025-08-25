"""
ARQ tasks for education-related operations.
"""

import logging
from typing import Any

from sqlalchemy import select

from app.database import get_db_session_for_worker
from app.education.models import Institution
from app.shared import openai_utils

logger = logging.getLogger(__name__)


async def task_determine_institution_display_name(
    ctx: dict[str, Any],
    institution_id: int,
) -> None:
    """
    Update a single Institution's display name.

    Args:
        ctx: ARQ worker context.
        institution_id: Identifier of the Institution to update.

    Side Effects:
        Persists an updated "name" for the Institution when applicable.
    """
    async with get_db_session_for_worker(ctx) as session:
        result = await session.execute(
            select(Institution).where(Institution.id == institution_id)
        )
        institution: Institution = result.scalar_one()

        try:
            display_name = await _generate_display_name(institution.full_name)
        except Exception as e:
            logger.error(
                f"Error generating display name for institution id={institution_id}: {e}"
            )
            fn = institution.full_name
            display_name = fn[:80].rsplit(" ", 1)[0] if " " in fn[:80] else fn[:80]

        institution.name = display_name


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
    logger.info("🤖 Calling OpenAI GPT-5-nano for display name generation")
    logger.debug(f"Input full_name: '{full_name}'")

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
        logger.warning(
            f"⚠️ OpenAI returned invalid display name (empty or too long): '{display_name}' (length: {len(display_name) if display_name else 0}). Using fallback."
        )
        # Simple fallback: take first 80 chars and try to end at a word boundary
        display_name = (
            full_name[:80].rsplit(" ", 1)[0]
            if " " in full_name[:80]
            else full_name[:80]
        )
        logger.info(f"🔄 Fallback display name: '{display_name}'")
    else:
        logger.info(
            f"✨ Valid display name generated: '{display_name}' (length: {len(display_name)})"
        )

    return display_name
