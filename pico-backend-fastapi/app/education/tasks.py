"""
ARQ tasks for education-related operations.
"""

import logging
from typing import Any

from sqlalchemy import select

from app.database import get_db_session_for_worker
from app.education.models import Institution
from app.flows.prompts import GenerateInstitutionDisplayName

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
        except Exception:
            logger.exception(
                f"Error generating display name for institution id={institution_id}"
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

    logger.info("🤖 Calling OpenAI GPT-5-nano for display name generation")
    logger.debug(f"Input full_name: '{full_name}'")

    response = await GenerateInstitutionDisplayName().text(
        full_name=full_name,
    )

    logger.info(f"🎯 Raw OpenAI output: '{response}'")

    display_name = response.strip()
    logger.info(f"📝 After strip(): '{display_name}'")

    # Fallback: if OpenAI returns something too long or empty, use a simple truncation
    if not display_name or len(display_name) > 120:
        logger.warning(
            "⚠️ OpenAI returned invalid display name (empty or too long): "
            f"{display_name}' (length: {len(display_name) if display_name else 0}). "
            "Using fallback."
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
            f"✨ Valid display name generated: '{display_name}' "
            f"(length: {len(display_name)})"
        )

    return display_name
