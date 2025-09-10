from collections.abc import Sequence
from typing import Any, ClassVar

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from wtforms import Field, PasswordField

from app.config import LowercaseEmailStr
from app.education.models import EducationInfo
from app.shared.admin import MODEL_ATTR, CustomModelView
from app.shared.validation import CustomPhoneNumber, PasswordStr, UsernameStr
from app.users import service as user_service
from app.users.models import SignupSource, User


def format_string(value: Any) -> Any:
    """Format string values for admin display, showing a special
    indicator for empty values."""
    return value if value else "[EMPTY STRING]"


class UserImportSchema(BaseModel):
    name: str
    username: UsernameStr
    email: LowercaseEmailStr
    phone_number: CustomPhoneNumber
    password: PasswordStr
    is_superuser: bool
    is_bot: bool
    bot_difficulty: float
    signup_source: SignupSource
    current_education_id: int | None
    intended_education_id: int | None
    referred_by: int | None


class UserAdmin(CustomModelView, model=User):
    icon = "fa-solid fa-users"

    column_list: ClassVar[str | Sequence[str | InstrumentedAttribute[Any]]] = (
        User.id,
        User.name,
        User.username,
        User.email,
        User.phone_number,
        User.created_at,
        User.is_superuser,
        User.is_bot,
        User.signup_source,
        User.social_score,
        User.xp_score,
        "referral_count",
    )
    column_searchable_list = (
        User.id,
        User.username,
        User.email,
        User.phone_number,
        User.name,
    )
    column_sortable_list = (
        User.id,
        User.name,
        User.username,
        User.email,
        User.created_at,
        User.is_superuser,
        User.is_bot,
        User.signup_source,
        User.current_education,
        User.intended_education,
        User.social_score,
        User.xp_score,
    )
    column_details_list = (
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
    )
    column_labels: ClassVar[dict[MODEL_ATTR, str]] = {
        "created_at": "Created At",
        "hashed_password": "Password",
        "is_superuser": "Admin?",
        "is_bot": "Bot?",
        "referral_count": "Number of Referrals",
        "signup_source": "Signup Source",
    }
    form_widget_args = CustomModelView.form_widget_args | {
        "referral_count": {
            "readonly": True,
        },
    }

    form_overrides: ClassVar[dict[str, type[Field]]] = {
        "hashed_password": PasswordField,
    }

    form_columns: ClassVar[Sequence[MODEL_ATTR]] = [
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
        "created_at",
    ]

    def list_query(self, request: Request) -> Select[tuple[User]]:
        stmt: Select[tuple[User]] = super().list_query(request)  # type: ignore

        return stmt.options(
            selectinload(User.referrals),
            selectinload(User.current_education),
            selectinload(User.intended_education),
            selectinload(User.referred_by),
        )

    def form_edit_query(self, request: Request) -> Select[tuple[User]]:
        # Start with the base query provided by SQLAdmin
        stmt: Select[tuple[User]] = super().form_edit_query(request)  # type: ignore

        # Add eager loads, but keep the WHERE clause intact
        return stmt.options(
            selectinload(User.referrals),
            selectinload(User.current_education),
            selectinload(User.intended_education),
            selectinload(User.referred_by),
        )

    def details_query(self, request: Request) -> Select[tuple[User]]:
        stmt: Select[tuple[User]] = super().details_query(request)  # type: ignore

        return stmt.options(
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

    async def on_model_change(
        self, data: dict[str, Any], model: User, is_created: bool, _: Request
    ) -> None:
        if data.get("hashed_password") and (
            is_created
            or (
                not data["hashed_password"].startswith(user_service.HASH_PREFIX)
                and data["hashed_password"] != model.hashed_password
            )
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

    async def to_orm_model(
        self, validated_data_list: list[UserImportSchema]
    ) -> list[User]:
        return [
            User(
                name=validated_data.name,
                username=validated_data.username,
                email=validated_data.email,
                phone_number=validated_data.phone_number,
                hashed_password=user_service.get_password_hash(
                    validated_data.password.get_secret_value()
                ),
                is_superuser=validated_data.is_superuser,
                is_bot=validated_data.is_bot,
                bot_difficulty=validated_data.bot_difficulty,
                signup_source=validated_data.signup_source,
                current_education_id=validated_data.current_education_id,
                intended_education_id=validated_data.intended_education_id,
                referred_by_id=validated_data.referred_by,
                google_id="",
                apple_id="",
                instagram_account="",
            )
            for validated_data in validated_data_list
        ]
