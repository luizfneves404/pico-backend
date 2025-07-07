from typing import Literal

from fastapi import APIRouter

import app.ws.service as ws_service
from app.community import service
from app.community.schemas import CommunityOut, UserInCommunityRanking
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
    online_info = await ws_service.get_online_info(
        db_session, [user.id for community in communities for user in community.users]
    )
    return [
        CommunityOut.from_orm_model(community, online_info) for community in communities
    ]


@router.get("/{id}/ranking")
async def get_community_ranking(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    id: int,
    score_type: Literal["xp", "social"],
) -> list[UserInCommunityRanking]:
    users = await service.get_community_ranking(
        db_session,
        asking_user_id=current_user.id,
        community_id=id,
        score_type=score_type,
    )
    return [
        UserInCommunityRanking(
            id=user.id,
            username=user.username,
            rank=user.rank,
            score=user.score,
        )
        for user in users
    ]
