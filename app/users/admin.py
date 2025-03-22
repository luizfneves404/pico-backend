from typing import Any, ClassVar, Sequence, Union

from fastapi import Request
from sqladmin import ModelView
from sqlalchemy import Select, select
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from users import service as user_service
from users.models import User


class UserAdmin(ModelView, model=User):
    column_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        User.id,
        User.username,
        User.email,
        User.phone_number,
        User.education_level,
        User.is_premium,
        User.commitment,
        User.balance,
        User.is_bot,
        "referral_count",
    ]
    column_searchable_list = [User.id, User.username, User.email, User.phone_number]
    column_sortable_list = [
        User.id,
        User.username,
        User.email,
        User.is_premium,
        User.commitment,
        User.balance,
        User.is_bot,
    ]
    column_details_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        User.id,
        User.created_at,
        User.username,
        User.email,
        User.phone_number,
        User.school_id,
        User.education_level,
        User.chosen_college_id,
        User.chosen_course_id,
        User.is_premium,
        User.referred_by_id,
        User.commitment,
        User.balance,
        User.is_bot,
        User.bot_difficulty,
        "referral_count",
    ]
    column_labels: ClassVar[dict[str | InstrumentedAttribute[Any], str]] = {
        "hashed_password": "password"
    }
    form_widget_args = {
        "created_at": {
            "readonly": True,
        },
    }

    def list_query(self, request: Request) -> Select[tuple[User]]:
        return select(User).options(selectinload(User.referrals))

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = (
            select(User).options(selectinload(User.referrals)).where(User.id == value)
        )
        return await self._get_object_by_pk(stmt)

    async def on_model_change(
        self, data: dict[str, Any], model: User, is_created: bool, request: Request
    ) -> None:
        data["hashed_password"] = user_service.get_password_hash(
            data["hashed_password"]
        )
