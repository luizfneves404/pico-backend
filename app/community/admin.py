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


class CommunityUserAdmin(CustomModelView, model=CommunityUser):
    icon = "fa-solid fa-user-group"

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

    form_columns = (
        "community_id",
        "user_id",
    )
