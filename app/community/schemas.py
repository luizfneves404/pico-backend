from pydantic import BaseModel

from app.community.models import Community
from app.shared.validation import RoundedFloat
from app.users.schemas import OnlineInfo as OnlineInfoOut
from app.ws.service import OnlineInfo


class UserInCommunity(BaseModel):
    id: int
    username: str
    online_info: OnlineInfoOut


class CommunityOut(BaseModel):
    id: int
    name: str
    subtitle: str
    users: list[UserInCommunity]

    @classmethod
    def from_orm_model(
        cls, community: Community, online_info: dict[int, OnlineInfo]
    ) -> "CommunityOut":
        return cls(
            id=community.id,
            name=community.name,
            subtitle=community.subtitle,
            users=[
                UserInCommunity(
                    id=user.id,
                    username=user.username,
                    online_info=OnlineInfoOut(
                        id=user.id,
                        is_online=online_info[user.id]["is_online"],
                        last_online=online_info[user.id]["last_online"],
                    ),
                )
                for user in community.users
            ],
        )


class UserInCommunityRanking(BaseModel):
    id: int
    username: str
    rank: int
    score: RoundedFloat
