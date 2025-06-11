import random

from sqlalchemy import and_, case, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.education.models import EducationInfo
from app.flows.models import Campaign, CampaignType, Flow
from app.users.models import User


async def _get_eligible_campaigns(
    db_session: AsyncSession, *, user_id: int
) -> list[Campaign]:
    """
    Get campaigns that a user is eligible to receive based on campaign type rules.

    Rules:
    - EXTERNAL: Always eligible
    - INSTITUTION: User must not have an institution in current_education
    - INTENDED_EDUCATION: User must have no intended_education
    - REFERRALS: User must have 0 referrals
    - FLOW: User must have never created a flow
    - ADD_PHONE_NUMBER: User must have no phone number (empty string)

    Args:
        db_session: Database session
        user_id: ID of the user to check eligibility for

    Returns:
        List of campaigns the user is eligible for
    """
    # Subquery to check if user has an institution in current education
    has_current_institution = exists().where(
        and_(
            EducationInfo.id == User.current_education_id,
            EducationInfo.institution_id.is_not(None),
        )
    )

    # Subquery to check if user has created any flows
    has_created_flows = exists().where(Flow.created_by_id == User.id)

    # Build eligibility conditions for each campaign type
    eligibility_conditions = case(
        (
            Campaign.campaign_type == CampaignType.EXTERNAL,
            True,  # Always eligible
        ),
        (
            Campaign.campaign_type == CampaignType.INSTITUTION,
            # Eligible if no current education OR current education has no institution
            (User.current_education_id.is_(None)) | (~has_current_institution),
        ),
        (
            Campaign.campaign_type == CampaignType.INTENDED_EDUCATION,
            # Eligible if no intended education
            User.intended_education_id.is_(None),
        ),
        (
            Campaign.campaign_type == CampaignType.REFERRALS,
            # Eligible if referral count is 0
            User.referral_count == 0,
        ),
        (
            Campaign.campaign_type == CampaignType.FLOW,
            # Eligible if never created any flows
            ~has_created_flows,
        ),
        (
            Campaign.campaign_type == CampaignType.ADD_PHONE_NUMBER,
            # Eligible if phone number is empty
            User.phone_number == "",
        ),
        else_=False,  # Default to not eligible for unknown types
    )

    # Query campaigns with eligibility check
    stmt = (
        select(Campaign)
        .select_from(Campaign)
        .join(User, User.id == user_id)
        .options(
            selectinload(Campaign.image1),
            selectinload(Campaign.image2),
        )
        .where(eligibility_conditions)
    )

    result = await db_session.scalars(stmt)
    return list(result)


async def select_one_campaign(
    db_session: "AsyncSession", *, user_id: int
) -> Campaign | None:
    """
    Selects a single campaign that a user is eligible for, based on probability.

    Uses weighted random sampling to select exactly one campaign. Campaigns with
    a higher probability value are more likely to be chosen. If the sum of
    probabilities is greater than 1.0, they are treated as relative weights.

    Args:
        db_session: The database session for querying campaigns.
        user_id: The ID of the user to get a campaign for.

    Returns:
        A single sampled campaign object, or None if no eligible campaigns are found.
    """
    eligible_campaigns = await _get_eligible_campaigns(db_session, user_id=user_id)

    if not eligible_campaigns:
        return None

    # Extract the list of probabilities to use as weights for the selection.
    probabilities = [campaign.probability for campaign in eligible_campaigns]

    # Use random.choices to perform a weighted random selection.
    # k=1 ensures that we get a list containing exactly one chosen campaign.
    # The function handles normalization, so probabilities don't need to sum to 1.
    selected_campaign_list = random.choices(
        population=eligible_campaigns, weights=probabilities, k=1
    )

    # The result is a list, so we return the single element it contains.
    return selected_campaign_list[0]
