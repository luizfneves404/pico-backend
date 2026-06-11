from typing import ClassVar

from pydantic import BaseModel
from wtforms import Form, IntegerField

from app.community.models import Community, CommunityUser
from app.shared.admin import CustomModelView


class CommunityAdmin(CustomModelView, model=Community):
    icon = "fa-solid fa-users"

    column_list = (
        Community.id,
        Community.name,
        Community.subtitle,
        Community.created_at,
    )
    column_searchable_list = (
        Community.name,
        Community.subtitle,
    )
    column_sortable_list = (
        Community.id,
        Community.name,
        Community.subtitle,
        Community.created_at,
    )
    column_details_list = (
        Community.id,
        Community.name,
        Community.subtitle,
        Community.created_at,
    )

    form_columns = (
        "name",
        "subtitle",
        "users",
    )


class CommunityUserImportSchema(BaseModel):
    community_id: int
    user_id: int


class CommunityUserAdmin(CustomModelView, model=CommunityUser):
    icon = "fa-solid fa-user-group"

    import_schema = CommunityUserImportSchema
    can_import = True
    import_template_data: ClassVar = {
        "community_id": 1,
        "user_id": 1,
    }

    class CommunityUserForm(Form):
        """Admin form for linking a user to a community.

        Fields:
        - community_id: int, the target community primary key
        - user_id: int, the target user primary key
        """

        community_id = IntegerField("Community ID")
        user_id = IntegerField("User ID")

    column_list = (
        CommunityUser.id,
        CommunityUser.community_id,
        CommunityUser.user_id,
        CommunityUser.created_at,
    )
    column_searchable_list = (
        CommunityUser.community_id,
        CommunityUser.user_id,
    )
    column_sortable_list = (
        CommunityUser.id,
        CommunityUser.community_id,
        CommunityUser.user_id,
        CommunityUser.created_at,
    )
    column_details_list = (
        CommunityUser.id,
        CommunityUser.community_id,
        CommunityUser.user_id,
        CommunityUser.created_at,
    )

    form = CommunityUserForm
