from typing import Any, ClassVar, Sequence, Union

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from wtforms import PasswordField

from app.education.models import EducationInfo
from app.shared.admin import CustomModelView
from app.users import service as user_service
from app.users.models import SignupSource, User


def format_string(value: Any) -> Any:
    """Format string values for admin display, showing a special indicator for empty values."""
    return value if value else "[EMPTY STRING]"


class UserImportSchema(BaseModel):
    name: str
    username: str
    email: str
    phone_number: str
    password: str
    is_superuser: bool
    is_bot: bool
    bot_difficulty: float
    signup_source: str
    current_education: int
    intended_education: int
    referred_by: int


class UserAdmin(CustomModelView, model=User):
    icon = "fa-solid fa-users"

    column_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        User.id,
        User.name,
        User.username,
        User.email,
        User.phone_number,
        User.is_superuser,
        User.is_bot,
        User.signup_source,
        User.social_score,
        User.xp_score,
        "referral_count",
    ]
    column_searchable_list = [
        User.id,
        User.username,
        User.email,
        User.phone_number,
        User.name,
    ]
    column_sortable_list = [
        User.id,
        User.name,
        User.username,
        User.email,
        User.is_superuser,
        User.is_bot,
        User.signup_source,
        User.current_education,
        User.intended_education,
        User.social_score,
        User.xp_score,
    ]
    column_details_list: ClassVar[
        Union[str, Sequence[Union[str, InstrumentedAttribute[Any]]]]
    ] = [
        User.id,
        User.created_at,
        User.name,
        User.username,
        User.email,
        User.phone_number,
        User.is_superuser,
        User.current_education_id,
        User.intended_education_id,
        User.referred_by_id,
        User.is_bot,
        User.bot_difficulty,
        User.signup_source,
        User.social_score,
        User.xp_score,
        "referral_count",
    ]
    column_labels: ClassVar[dict[str | InstrumentedAttribute[Any], str]] = {
        "hashed_password": "Password",
        "is_superuser": "Admin?",
        "is_bot": "Bot?",
        "referral_count": "Number of Referrals",
        "signup_source": "Signup Source",
    }
    form_widget_args = {
        "created_at": {
            "readonly": True,
        },
        "referral_count": {
            "readonly": True,
        },
    }

    form_overrides = {
        "hashed_password": PasswordField,
    }

    form_columns = [
        "name",
        "username",
        "email",
        "phone_number",
        "hashed_password",
        "is_superuser",
        "is_bot",
        "bot_difficulty",
        "signup_source",
        "current_education",
        "intended_education",
        "referred_by",
        "social_score",
        "xp_score",
    ]

    def list_query(self, request: Request) -> Select[tuple[User]]:
        return select(User).options(
            selectinload(User.referrals),
            selectinload(User.current_education),
            selectinload(User.intended_education),
            selectinload(User.referred_by),
        )

    def form_edit_query(self, request: Request) -> Select[tuple[User]]:
        return select(User).options(
            selectinload(User.referrals),
            selectinload(User.current_education),
            selectinload(User.intended_education),
            selectinload(User.referred_by),
        )

    async def get_object_for_details(self, value: Any) -> Any:
        stmt = (
            select(User)
            .options(
                selectinload(User.referrals),
                selectinload(User.current_education).options(
                    selectinload(EducationInfo.level),
                    selectinload(EducationInfo.institution),
                    selectinload(EducationInfo.stage),
                    selectinload(EducationInfo.course),
                ),
                selectinload(User.intended_education).options(
                    selectinload(EducationInfo.level),
                    selectinload(EducationInfo.institution),
                    selectinload(EducationInfo.stage),
                    selectinload(EducationInfo.course),
                ),
                selectinload(User.referred_by),
            )
            .where(User.id == int(value))
        )
        return await self._get_object_by_pk(stmt)

    async def on_model_change(
        self, data: dict[str, Any], model: User, is_created: bool, request: Request
    ) -> None:
        if "hashed_password" in data and data["hashed_password"]:
            if is_created or (
                not data["hashed_password"].startswith(user_service.HASH_PREFIX)
                and data["hashed_password"] != model.hashed_password
            ):
                data["hashed_password"] = user_service.get_password_hash(
                    data["hashed_password"]
                )

        # Ensure bot_difficulty is set correctly based on is_bot
        if "is_bot" in data:
            if not data["is_bot"] and "bot_difficulty" in data:
                data["bot_difficulty"] = None
            elif data["is_bot"] and (
                "bot_difficulty" not in data or data["bot_difficulty"] is None
            ):
                data["bot_difficulty"] = 0.5  # Default difficulty

    def to_orm_model(self, validated_data: UserImportSchema) -> User:
        return User(
            name=validated_data.name,
            username=validated_data.username,
            email=validated_data.email,
            phone_number=validated_data.phone_number,
            hashed_password=user_service.get_password_hash(validated_data.password),
            is_superuser=validated_data.is_superuser,
            is_bot=validated_data.is_bot,
            bot_difficulty=validated_data.bot_difficulty,
            signup_source=SignupSource(validated_data.signup_source),
            current_education_id=validated_data.current_education,
            intended_education_id=validated_data.intended_education,
            referred_by_id=validated_data.referred_by,
            google_id="",
            apple_id="",
        )
