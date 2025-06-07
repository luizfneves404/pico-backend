from fastapi import APIRouter

from app.community import service
from app.community.schemas import CommunityOut
from app.deps import CurrentUserAnnotated, DBSessionAnnotated

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/me", response_model=list[CommunityOut])
async def my_communities(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
) -> list[CommunityOut]:
    communities = await service.get_user_communities(
        db_session, user_id=current_user.id
    )
    return [CommunityOut.from_orm_model(community) for community in communities]
