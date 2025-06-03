from fastapi import APIRouter

from app.community import service
from app.deps import CurrentUserAnnotated, DBSessionAnnotated

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/my", response_model=CommunityOut)
async def my_community(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
):
    community = await service.get_user_community(db_session, current_user.id)
    return community
