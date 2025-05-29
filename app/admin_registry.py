from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqladmin import BaseView
from sqladmin.authentication import AuthenticationBackend
from starlette.status import HTTP_401_UNAUTHORIZED

from app.config import settings
from app.database import db_manager
from app.education.admin import CollegeAdmin, CourseAdmin, SchoolAdmin
from app.files.admin import FileAdmin
from app.flows.admin import (
    ChoiceAdmin,
    FlowAdmin,
    FlowElementAdmin,
    FlowQuestionAdmin,
    FlowQuestionUserAdmin,
    QuestionAdmin,
)
from app.logging_admin import (
    GetCurrentLevelsView,
    LoggingControlView,
    SetSqlLoggingLevelView,
)
from app.users import service as user_service
from app.users.admin import UserAdmin, UserProfileAdmin
from app.users.jwt_token import TokenError, generate_tokens, process_token

admin_views: list[type[BaseView]] = []

admin_views.append(SetSqlLoggingLevelView)
admin_views.append(GetCurrentLevelsView)
admin_views.append(LoggingControlView)
admin_views.append(UserAdmin)
admin_views.append(CollegeAdmin)
admin_views.append(CourseAdmin)
admin_views.append(SchoolAdmin)
admin_views.append(FlowAdmin)
admin_views.append(FlowElementAdmin)
admin_views.append(FlowQuestionAdmin)
admin_views.append(FlowQuestionUserAdmin)
admin_views.append(QuestionAdmin)
admin_views.append(ChoiceAdmin)
admin_views.append(UserProfileAdmin)
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


async def require_admin_login(request: Request) -> None | RedirectResponse:
    """
    Dependency to require admin authentication for FastAPI route handlers.

    Args:
        request: The incoming FastAPI request.

    Raises:
        HTTPException: If not authenticated (API clients).
    """
    auth_backend = authentication_backend
    is_authenticated = await auth_backend.authenticate(request)
    if not is_authenticated:
        if request.headers.get("accept", "").startswith("text/html"):
            raise HTTPException(
                status_code=302,
                headers={"Location": str(request.url_for("admin:login"))},
            )
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
