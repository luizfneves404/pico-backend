import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

import app.users.jwt_token as jwt_token
from app.deps import CurrentUserAnnotated, CurrentUserDep, DBSessionAnnotated
from app.pagination import (
    PaginatedResponse,
    PaginationParams,
    get_pagination_params,
    paginate,
)
from app.users import service
from app.users.jwt_token import TokenError
from app.users.models import EducationLevel
from app.users.schemas import (
    BalanceOut,
    OnlineInfo,
    OtherUserOut,
    PasswordRequest,
    RawPhoneNumbersIn,
    RefreshRequest,
    TokenResponse,
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
    user = await service.authenticate_user(
        db_session, form_data.username.strip(), form_data.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token, refresh_token = jwt_token.generate_tokens(user)
    return TokenResponse(access=access_token, refresh=refresh_token)


@token_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_request: RefreshRequest, db_session: DBSessionAnnotated
) -> TokenResponse:
    try:
        user = await jwt_token.process_token(
            db_session, refresh_request.refresh, "refresh"
        )
        access, refresh = jwt_token.generate_tokens(user)
        return TokenResponse(access=access, refresh=refresh)
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


@user_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    db_session: DBSessionAnnotated,
    user_in: UserIn,
    request: Request,
) -> UserOut:
    logger.info("Starting create_user")
    try:
        # Convert EducationIn to dict for the service
        current_education_dict = None
        if user_in.current_education:
            current_education_dict = {
                "level": user_in.current_education.level,
                "institution_id": user_in.current_education.institution_id,
                "course_id": user_in.current_education.course_id,
            }

        intended_education_dict = None
        if user_in.intended_education:
            intended_education_dict = {
                "level": user_in.intended_education.level,
                "institution_id": user_in.intended_education.institution_id,
                "course_id": user_in.intended_education.course_id,
            }

        db_user = await service.create_user(
            db_session,
            username=user_in.username.strip(),
            password=user_in.password.get_secret_value(),
            phone_number=user_in.phone_number,
            email=user_in.email,
            referred_by_username=user_in.referred_by_username.strip() or None,
            signup_source=user_in.signup_source,
            current_education=current_education_dict,
            intended_education=intended_education_dict,
        )
        # Refresh relationships for UserOut response
        await db_session.refresh(
            db_user,
            ["current_education", "intended_education", "profile"],
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
    logger.info(f"User with username {user_in.username} created successfully")
    return UserOut.from_orm_model(db_user)


@user_authenticated_router.get(
    "/me", response_model=UserOut, status_code=status.HTTP_200_OK
)
async def read_users_me(
    current_user: CurrentUserAnnotated, db_session: DBSessionAnnotated
) -> UserOut:
    await db_session.refresh(
        current_user,
        ["current_education", "intended_education", "profile"],
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
        ["current_education", "intended_education", "profile"],
    )
    return OtherUserOut.from_orm_model(user)


@user_authenticated_router.patch(
    "/me", response_model=UserPartialUpdateResponse, status_code=status.HTTP_200_OK
)
async def update_user(
    request: UserUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    """Update multiple user fields in a single request.

    This endpoint allows updating multiple user fields atomically.
    Sensitive fields (username, phone_number, email) require password verification.
    Non-sensitive fields (education) can be updated without password.

    Only fields included in the request will be updated. Null values are ignored.
    """
    try:
        # Convert Pydantic model to dict, excluding unset fields
        updates_dict = request.updates.model_dump(exclude_unset=True)

        if not updates_dict:
            # No fields to update
            await db_session.refresh(
                current_user,
                ["current_education", "intended_education", "profile"],
            )
            return UserPartialUpdateResponse(
                updated_fields=[], user=UserOut.from_orm_model(current_user)
            )

        current_password = None
        if request.current_password:
            current_password = request.current_password.get_secret_value()

        # Load education relationships before updating
        await db_session.refresh(
            current_user,
            ["current_education", "intended_education"],
        )

        updated_user, updated_fields = await service.update_user_fields(
            db_session,
            current_user,
            updates_dict,
            current_password,
        )

        # Refresh relationships for response
        await db_session.refresh(
            updated_user,
            ["current_education", "intended_education", "referrals", "profile"],
        )

        return UserPartialUpdateResponse(
            updated_fields=updated_fields,
            user=UserOut.from_orm_model(updated_user),
        )

    except service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password or password required for sensitive fields",
        )
    except service.UsernameAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
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


@user_authenticated_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    request: PasswordRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
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


""" @user_authenticated_router.get("/stats", response_model=UserStatsMeResponse)
async def get_user_stats_me(
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    user_stats = await service.get_user_stats(db_session, user_id=current_user.id)
    return user_stats


@user_authenticated_router.get("/stats/{username}", response_model=UserStatsResponse)
async def get_stats_by_username(
    username: str,
    db_session: DBSessionAnnotated,
):
    try:
        user_stats = await service.get_user_stats(db_session, username=username)
        return user_stats
    except service.UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) """


@user_authenticated_router.post(
    "/check-contacts",
    response_model=PaginatedResponse[OtherUserOut],
)
async def check_contacts(
    raw_phone_numbers_schema: RawPhoneNumbersIn,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
    db_session: DBSessionAnnotated,
):
    raw_phone_numbers = raw_phone_numbers_schema.phone_numbers
    users = await service.check_contacts(db_session, raw_phone_numbers)
    user_outs = await service.to_other_user_out(db_session, [user.id for user in users])
    return paginate(user_outs, pagination)


@user_router.get(
    "/search-username",
    response_model=PaginatedResponse[OtherUserOut],
)
async def search_username(
    username: str,
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
    db_session: DBSessionAnnotated,
):
    users = await service.search_username(db_session, username)
    user_outs = await service.to_other_user_out(db_session, [user.id for user in users])
    return paginate(user_outs, pagination)


@user_router.get(
    "/sentinel",
    response_model=list[OtherUserOut],
)
async def sentinel_users(
    db_session: DBSessionAnnotated,
):
    users = await service.get_sentinel_users(db_session)
    user_outs = await service.to_other_user_out(db_session, [user.id for user in users])
    return user_outs


@user_authenticated_router.get(
    "/ranking",
    response_model=list[UserInRanking],
)
async def user_ranking(
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
    score_type: Literal["xp", "social"],
    school_filter: int | None = None,
    intended_course_filter: str | None = None,
    intended_college_filter: int | None = None,
    education_level_filter: EducationLevel | None = None,
    subject: str | None = None,
):
    if score_type == "xp" and subject is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subject is not allowed for xp score type",
        )
    return await service.get_ranking(
        db_session,
        current_user.id,
        score_type=score_type,
        school_filter=school_filter,
        course_filter=intended_course_filter,
        education_level_filter=education_level_filter,
        subject=subject,
    )


@user_authenticated_router.post(
    "/online-info",
    response_model=list[OnlineInfo],
)
async def get_online_info(
    user_ids_in: UserIdsIn,
    db_session: DBSessionAnnotated,
):
    return await service.get_online_info(db_session, user_ids_in.user_ids)


@user_authenticated_router.get(
    "/me/balance",
    response_model=BalanceOut,
)
async def get_balance(
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    try:
        return {"balance": await service.get_balance(db_session, current_user.id)}
    except service.UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


user_router.include_router(user_authenticated_router)
