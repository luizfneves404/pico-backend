from typing import TypeVar

from config import settings
from database import get_db_session
from fastapi import Request
from quiz.admin import (
    ChallengeAdmin,
    ChoiceAdmin,
    DuelAdmin,
    QuestionAdmin,
    QuizAdmin,
    RoundAdmin,
    SessionAdmin,
    SessionParticipationAdmin,
    TurnAdmin,
    UserInfoAdmin,
)
from schools.admin import SchoolAdmin
from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend
from users import service as user_service
from users.admin import UserAdmin
from users.token import TokenError, generate_tokens, process_token

admin_views: list[type[ModelView]] = []

T = TypeVar("T", bound=type[ModelView])


admin_views.append(UserAdmin)
admin_views.append(SchoolAdmin)
admin_views.append(QuizAdmin)
admin_views.append(SessionAdmin)
admin_views.append(QuestionAdmin)
admin_views.append(ChoiceAdmin)
admin_views.append(DuelAdmin)
admin_views.append(ChallengeAdmin)
admin_views.append(UserInfoAdmin)
admin_views.append(RoundAdmin)
admin_views.append(TurnAdmin)
admin_views.append(SessionParticipationAdmin)


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]

        # Create a database session
        async for db_session in get_db_session():
            # Authenticate the user using the existing authentication system
            user = await user_service.authenticate_user(
                db_session, str(username), str(password)
            )

            # Check if user exists and is a superuser
            if not user:
                return False

            if not user.is_superuser:
                return False

            # Generate tokens and store in session
            access_token, _ = generate_tokens(user)
            request.session.update({"token": access_token, "user_id": user.id})

            return True
        return False

    async def logout(self, request: Request) -> bool:
        # Clear the session
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")

        if not token:
            return False

        try:
            # Verify the token and check if the user is a superuser
            async for db_session in get_db_session():
                user = await process_token(db_session, token, "access")
                return bool(user and user.is_superuser)
        except TokenError:
            return False
        return False


authentication_backend = AdminAuth(secret_key=settings.secret_key)
