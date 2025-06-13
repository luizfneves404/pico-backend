from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqladmin import BaseView
from sqladmin.authentication import AuthenticationBackend
from starlette.status import HTTP_401_UNAUTHORIZED

from app.community.admin import CommunityAdmin, CommunityUserAdmin
from app.config import settings
from app.countries.admin import CountryAdmin
from app.database import db_manager
from app.education.admin import (
    CourseModelAdmin,
    EducationInfoAdmin,
    EducationLevelAdmin,
    InstitutionAdmin,
    LevelStageAdmin,
)
from app.fcm.admin import FCMDeviceAdmin
from app.files.admin import FileAdmin
from app.flows.admin import (
    CampaignAdmin,
    ChoiceAdmin,
    ExamAdmin,
    FlowAdmin,
    FlowElementAdmin,
    FlowQuestionAdmin,
    FlowQuestionUserAdmin,
    FlowTranscriptionBlockAdmin,
    FlowUserFeedAdmin,
    OfficialQuestionSourceAdmin,
    QuestionAdmin,
    QuestionAreaAdmin,
)
from app.in_app_notifications.admin import (
    ExternalInAppNotificationAdmin,
    FlowInAppNotificationAdmin,
    InAppNotificationAdmin,
)
from app.logging_admin import (
    GetCurrentLevelsView,
    LoggingControlView,
    SetSqlLoggingLevelView,
)
from app.users import service as user_service
from app.users.admin import UserAdmin
from app.users.jwt_token import TokenError, generate_tokens, process_token
from app.ws.admin import UserOnlineInfoAdmin

admin_views: list[type[BaseView]] = []

# System & Logging
admin_views.append(SetSqlLoggingLevelView)
admin_views.append(GetCurrentLevelsView)
admin_views.append(LoggingControlView)

# Users & Authentication
admin_views.append(UserAdmin)
admin_views.append(UserOnlineInfoAdmin)
admin_views.append(FCMDeviceAdmin)

# Countries
admin_views.append(CountryAdmin)

# Education
admin_views.append(EducationLevelAdmin)
admin_views.append(LevelStageAdmin)
admin_views.append(CourseModelAdmin)
admin_views.append(InstitutionAdmin)
admin_views.append(EducationInfoAdmin)

# Community
admin_views.append(CommunityAdmin)
admin_views.append(CommunityUserAdmin)

# Files
admin_views.append(FileAdmin)

# Flows & Questions
admin_views.append(FlowAdmin)
admin_views.append(FlowTranscriptionBlockAdmin)
admin_views.append(FlowElementAdmin)
admin_views.append(FlowQuestionAdmin)
admin_views.append(FlowQuestionUserAdmin)
admin_views.append(FlowUserFeedAdmin)
admin_views.append(QuestionAdmin)
admin_views.append(QuestionAreaAdmin)
admin_views.append(ChoiceAdmin)
admin_views.append(ExamAdmin)
admin_views.append(OfficialQuestionSourceAdmin)
admin_views.append(CampaignAdmin)
# Notifications
admin_views.append(InAppNotificationAdmin)
admin_views.append(ExternalInAppNotificationAdmin)
admin_views.append(FlowInAppNotificationAdmin)


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        email, password = form["email"], form["password"]

        # Create a database session
        async with db_manager.session_with_transaction() as db_session:
            # Authenticate the user using the existing authentication system
            user = await user_service.authenticate_user_by_password(
                db_session, str(email), str(password)
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
