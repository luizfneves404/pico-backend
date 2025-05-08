from fastapi import Request
from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend

from app.config import settings
from app.database import db_manager
from app.essays.admin import (
    EssayAdmin,
    EssayTopicAdmin,
    EssayTypeAdmin,
    FeedbackAdmin,
    FeedbackCategoryAdmin,
)
from app.files.admin import FileAdmin
from app.quiz.admin import (
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
from app.schools.admin import SchoolAdmin
from app.users import service as user_service
from app.users.admin import CollegeAdmin, CourseAdmin, UserAdmin
from app.users.jwt_token import TokenError, generate_tokens, process_token

admin_views: list[type[ModelView]] = []

admin_views.append(UserAdmin)
admin_views.append(CollegeAdmin)
admin_views.append(CourseAdmin)
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
admin_views.append(EssayTopicAdmin)
admin_views.append(EssayAdmin)
admin_views.append(EssayTypeAdmin)
admin_views.append(FeedbackCategoryAdmin)
admin_views.append(FeedbackAdmin)
admin_views.append(FileAdmin)


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]

        # Create a database session
        async with db_manager.session_with_transaction() as db_session:
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
            async with db_manager.session_with_transaction() as db_session:
                user = await process_token(db_session, token, "access")
                return bool(user and user.is_superuser)
        except TokenError:
            return False


authentication_backend = AdminAuth(secret_key=settings.secret_key)
