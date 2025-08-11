import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm

import app.users.jwt_token as jwt_token
import app.ws.service as ws_service
from app.deps import CurrentUserAnnotated, CurrentUserDep, DBSessionAnnotated
from app.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
    paginate,
)
from app.shared.validation import PasswordStr
from app.templating import templates
from app.users import service
from app.users.jwt_token import TokenError
from app.users.schemas import (
    AppleAuthRequest,
    EducationInfoOut,
    GoogleAuthRequest,
    OnlineInfo,
    OtherUserOut,
    PasswordRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    RawPhoneNumbersIn,
    RefreshRequest,
    SentinelUserOut,
    TokenResponse,
    UserFieldValidationRequest,
    UserFieldValidationResponse,
    UserIdsIn,
    UserIn,
    UserInRanking,
    UserOut,
    UserPartialUpdateResponse,
    UserUpdateRequest,
    VerifyRequest,
)

logger = logging.getLogger(__name__)

token_router = APIRouter(prefix="/token", tags=["token"])
user_router = APIRouter(prefix="/users", tags=["users"])
user_authenticated_router = APIRouter(dependencies=[CurrentUserDep])


@token_router.post("/pair", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db_session: DBSessionAnnotated,
) -> TokenResponse:
    """
    Login with email and password, passed as form data
    - username: it's actually the email of the user
    - password: the password of the user
    """
    user = await service.authenticate_user_by_password(
        db_session, form_data.username, form_data.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token, refresh_token = jwt_token.generate_tokens(user)
    return TokenResponse(
        access_token=access_token, refresh_token=refresh_token, token_type="bearer"
    )


@token_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_request: RefreshRequest, db_session: DBSessionAnnotated
) -> TokenResponse:
    try:
        user = await jwt_token.process_token(
            db_session, refresh_request.refresh_token, "refresh"
        )
        access_token, refresh_token = jwt_token.generate_tokens(user)
        return TokenResponse(
            access_token=access_token, refresh_token=refresh_token, token_type="bearer"
        )
    except TokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)
    except service.UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )


@token_router.post("/verify")
async def verify_token(
    verify_request: VerifyRequest, db_session: DBSessionAnnotated
) -> None:
    try:
        await jwt_token.process_token(db_session, verify_request.token)
    except TokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)


@token_router.post("/social/google", response_model=TokenResponse)
async def google_auth(
    google_request: GoogleAuthRequest, db_session: DBSessionAnnotated
) -> TokenResponse:
    """
    Authenticate with Google ID token

    Verifies the Google ID token and either logs in existing user or creates new account.
    """
    try:
        user = await service.authenticate_user_by_google(
            db_session,
            id_token=google_request.id_token,
            signup_source=google_request.signup_source,
            referred_by_username=google_request.referred_by_username,
        )
        access_token, refresh_token = jwt_token.generate_tokens(
            user, auth_provider="google"
        )
        return TokenResponse(
            access_token=access_token, refresh_token=refresh_token, token_type="bearer"
        )
    except service.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID token"
        )
    except service.AccountExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account already exists. Please log in using email and password.",
        )
    except service.UsernameAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already exists"
        )
    except service.EmailAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already exists"
        )


@token_router.post("/social/apple", response_model=TokenResponse)
async def apple_auth(
    apple_request: AppleAuthRequest, db_session: DBSessionAnnotated
) -> TokenResponse:
    """
    Authenticate with Apple ID token

    Verifies the Apple ID token and either logs in existing user or creates new account.
    """
    try:
        user = await service.authenticate_user_by_apple(
            db_session,
            id_token=apple_request.id_token,
            name=apple_request.name,
            signup_source=apple_request.signup_source,
            referred_by_username=apple_request.referred_by_username,
        )
        access_token, refresh_token = jwt_token.generate_tokens(
            user, auth_provider="apple"
        )
        return TokenResponse(
            access_token=access_token, refresh_token=refresh_token, token_type="bearer"
        )
    except service.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID token"
        )
    except service.AccountExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account already exists. Please log in using email and password.",
        )
    except service.UsernameAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already exists"
        )
    except service.EmailAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already exists"
        )


@token_router.post("/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset_endpoint(
    request: Request,
    password_reset_request: PasswordResetRequest,
    db_session: DBSessionAnnotated,
) -> PasswordResetResponse:
    """
    Request password reset email

    Sends a password reset email to the user if the email exists.
    Always returns success for security reasons.
    """
    await service.request_password_reset(
        request, db_session, password_reset_request.email
    )

    return PasswordResetResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@token_router.get(
    "/password-reset/page/{token}",
    response_class=HTMLResponse,
    name="password_reset_page",
)
async def password_reset_page(request: Request, token: str) -> HTMLResponse:
    """Show password reset form"""
    # Validate token exists and isn't expired (optional - for better UX)
    try:
        await service.get_valid_reset_token(token)

    except service.InvalidResetTokenError:
        return templates.TemplateResponse(
            "password_reset_error.html",
            {"request": request, "error": "Invalid reset link"},
        )

    return templates.TemplateResponse(
        "password_reset.html", {"request": request, "token": token}
    )


@token_router.post(
    "/password-reset/page/{token}",
    response_class=HTMLResponse,
    name="password_reset_page",
)
async def password_reset_submit(
    request: Request,
    db_session: DBSessionAnnotated,
    token: str,
    new_password: PasswordStr = Form(),
    confirm_password: PasswordStr = Form(),
) -> HTMLResponse:
    """Handle password reset form submission"""

    # Validate passwords match
    if new_password != confirm_password:
        return templates.TemplateResponse(
            "password_reset.html",
            {"request": request, "token": token, "error": "Passwords do not match"},
        )

    try:
        # Reset the password
        await service.reset_password(db_session, token, new_password.get_secret_value())

        return templates.TemplateResponse(
            "password_reset_success.html", {"request": request}
        )

    except service.InvalidTokenError as e:
        return templates.TemplateResponse(
            "password_reset_error.html", {"request": request, "error": str(e)}
        )
    except service.UserNotFoundError:
        return templates.TemplateResponse(
            "password_reset_error.html",
            {
                "request": request,
                "token": token,
                "error": "User not found.",
            },
        )


@user_router.post("/validate")
async def validate_user_field(
    request: UserFieldValidationRequest,
    db_session: DBSessionAnnotated,
) -> UserFieldValidationResponse:
    result = await service.validate_user_field(
        db_session, request.field_name, request.field_value
    )
    return UserFieldValidationResponse(
        is_valid=result[0],
        validated_value=result[1],
    )


@user_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    db_session: DBSessionAnnotated,
    user_in: UserIn,
) -> UserOut:
    logger.info("Starting create_user")
    try:
        db_user = await service.create_user_by_password(
            db_session,
            name=user_in.name.strip(),
            password=user_in.password.get_secret_value(),
            email=user_in.email,
            referred_by_username=user_in.referred_by_username.strip() or None,
            signup_source=user_in.signup_source,
        )
        # Refresh relationships for UserOut response
        await db_session.refresh(
            db_user,
            ["current_education", "intended_education"],
        )
    except service.UsernameAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already exists"
        )
    except service.PhoneNumberAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already exists",
        )
    except service.EmailAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )
    except service.ReferredByNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referred by not found",
        )
    logger.info(f"User with username {db_user.username} created successfully")
    return UserOut.from_orm_model(db_user)


@user_authenticated_router.get(
    "/me", response_model=UserOut, status_code=status.HTTP_200_OK
)
async def read_users_me(
    current_user: CurrentUserAnnotated, db_session: DBSessionAnnotated
) -> UserOut:
    await db_session.refresh(
        current_user,
        ["current_education", "intended_education"],
    )
    return UserOut.from_orm_model(current_user)


@user_authenticated_router.get("/other/{user_id}", response_model=UserOut)
async def read_other_user(
    user_id: int, current_user: CurrentUserAnnotated, db_session: DBSessionAnnotated
) -> OtherUserOut:
    user = await service.get_user(db_session, id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    await db_session.refresh(
        user,
        ["current_education", "intended_education"],
    )
    return OtherUserOut.from_orm_model(user)


@user_authenticated_router.patch(
    "/me", response_model=UserPartialUpdateResponse, status_code=status.HTTP_200_OK
)
async def update_user(
    request: UserUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
) -> UserPartialUpdateResponse:
    """Update multiple user fields in a single request.

    This endpoint allows updating multiple user fields atomically.
    Sensitive fields (username, password, phone_number, email) require password verification.
    Non-sensitive fields can be updated without password.

    Only fields included in the request will be updated.
    """
    try:
        # Get current password if provided
        current_password = None
        if request.current_password:
            current_password = request.current_password.get_secret_value()

        # Validate that we have update data
        if not request.updates:
            await db_session.refresh(
                current_user,
                ["current_education", "intended_education"],
            )
            return UserPartialUpdateResponse(
                updated_fields=[], user=UserOut.from_orm_model(current_user)
            )
        else:
            # Load education relationships before updating
            await db_session.refresh(
                current_user,
                ["current_education", "intended_education"],
            )

        updated_user, updated_fields = await service.update_user_fields(
            db_session,
            user=current_user,
            updates=request.updates,
            current_password=current_password,
        )

        # Refresh relationships for response
        await db_session.refresh(
            updated_user,
            ["current_education", "intended_education", "referrals"],
        )

        return UserPartialUpdateResponse(
            updated_fields=updated_fields,
            user=UserOut.from_orm_model(updated_user),
        )

    except service.InvalidCredentialsError as e:
        if "Password required" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required for sensitive field updates",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
            )
    except service.UsernameAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )
    except service.EmailAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )
    except service.InvalidLevelIdError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid level id",
        )
    except service.InvalidStageIdError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid stage id",
        )
    except service.InvalidInstitutionIdError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid institution id",
        )
    except service.InvalidCourseIdError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid course id",
        )
    except service.InvalidCountryCodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid country code",
        )


@user_authenticated_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    request: PasswordRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
) -> None:
    try:
        await service.delete_user(
            db_session,
            current_user,
            request.current_password.get_secret_value(),
        )
    except service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )


@user_authenticated_router.post(
    "/check-contacts",
    response_model=PaginatedResponse[OtherUserOut],
)
async def check_contacts(
    raw_phone_numbers_schema: RawPhoneNumbersIn,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
    db_session: DBSessionAnnotated,
) -> PaginatedResponse[OtherUserOut]:
    raw_phone_numbers = raw_phone_numbers_schema.phone_numbers
    users = await service.check_contacts(db_session, raw_phone_numbers, pagination)
    user_outs = await service.to_other_user_out(db_session, [user.id for user in users])
    other_user_outs = [OtherUserOut.from_orm_model(user) for user in user_outs]
    return paginate(other_user_outs, pagination)


@user_router.get(
    "/search-username",
    response_model=PaginatedResponse[OtherUserOut],
)
async def search_username(
    username: str,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
    db_session: DBSessionAnnotated,
) -> PaginatedResponse[OtherUserOut]:
    users = await service.search_username(db_session, username, pagination)
    user_outs = await service.to_other_user_out(db_session, [user.id for user in users])
    other_user_outs = [OtherUserOut.from_orm_model(user) for user in user_outs]
    return paginate(other_user_outs, pagination)


@user_router.get(
    "/sentinel",
    response_model=list[SentinelUserOut],
)
async def sentinel_users(
    db_session: DBSessionAnnotated,
) -> list[SentinelUserOut]:
    users = await service.get_sentinel_users(db_session)
    return [
        SentinelUserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            phone_number=user.phone_number,
        )
        for user in users
    ]


@user_authenticated_router.get(
    "/ranking",
    response_model=list[UserInRanking],
)
async def user_ranking(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    score_type: Literal["xp", "social"],
    institution_id: int | None = None,
    course_id: int | None = None,
    education_level_id: int | None = None,
    stage_id: int | None = None,
) -> list[UserInRanking]:
    """Get user ranking based on various filters. If you pass null, it is not filtered by that criteria."""
    users = await service.get_ranking(
        db_session,
        asking_user_id=current_user.id,
        score_type=score_type,
        institution_id=institution_id,
        education_level_id=education_level_id,
        course_id=course_id,
        stage_id=stage_id,
    )
    return [
        UserInRanking(
            id=user.id,
            username=user.username,
            rank=user.rank,
            score=user.score,
            current_education=EducationInfoOut(
                level_id=user.current_education.level_id,
                stage_id=user.current_education.stage_id,
                institution_id=user.current_education.institution_id,
                course_id=user.current_education.course_id,
            )
            if user.current_education
            else None,
        )
        for user in users
    ]


@user_authenticated_router.post(
    "/online-info",
    response_model=list[OnlineInfo],
)
async def get_online_info(
    user_ids_in: UserIdsIn,
    db_session: DBSessionAnnotated,
) -> list[OnlineInfo]:
    online_info = await ws_service.get_online_info(db_session, user_ids_in.user_ids)
    return [
        OnlineInfo(
            id=info["id"],
            is_online=info["is_online"],
            last_online=info["last_online"],
        )
        for info in online_info.values()
    ]


user_router.include_router(user_authenticated_router)
