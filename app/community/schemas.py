from pydantic import BaseModel

from app.community.models import Community


class CommunityOut(BaseModel):
    id: int
    name: str
    subtitle: str

    @classmethod
    def from_orm_model(cls, community: Community) -> "CommunityOut":
        return cls(
            id=community.id,
            name=community.name,
            subtitle=community.subtitle,
        )
