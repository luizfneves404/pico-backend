import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

import app.users.jwt_token as jwt_token
from app.arq_client import enqueue_job
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
    CollegeUpdateRequest,
    CommitmentUpdateRequest,
    CourseUpdateRequest,
    EducationLevelUpdateRequest,
    EmailUpdateRequest,
    OnlineInfo,
    OtherUserOut,
    PasswordRequest,
    PasswordUpdateRequest,
    PhoneNumberUpdateRequest,
    RawPhoneNumbersIn,
    RefreshRequest,
    SchoolUpdateRequest,
    TokenResponse,
    UserIn,
    UserInRanking,
    UsernameUpdateRequest,
    UserOut,
    UserStatsMeResponse,
    UserStatsResponse,
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
):
    await enqueue_job("ping")
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
    return {"access": access_token, "refresh": refresh_token}


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
):
    logger.info("Starting create_user")
    try:
        db_user = await service.create_user(
            db_session,
            username=user_in.username.strip(),
            password=user_in.password.get_secret_value(),
            phone_number=user_in.phone_number,
            email=user_in.email,
            chosen_college=user_in.chosen_college,
            chosen_course=user_in.chosen_course,
            education_level=user_in.education_level,
            commitment=user_in.commitment,
            referred_by_username=user_in.referred_by_username,
            school_id=user_in.school_id,
            signup_source=user_in.signup_source,
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
    return db_user


@user_authenticated_router.get(
    "/me", response_model=UserOut, status_code=status.HTTP_200_OK
)
async def read_users_me(
    current_user: CurrentUserAnnotated, db_session: DBSessionAnnotated
):
    await db_session.refresh(
        current_user,
        ["chosen_college", "chosen_course", "referrals"],
    )
    return current_user


@user_authenticated_router.patch(
    "/set-username", status_code=status.HTTP_204_NO_CONTENT
)
async def update_username(
    request: UsernameUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    try:
        await service.set_username(
            db_session,
            current_user,
            request.new_username.strip(),
            request.current_password.get_secret_value(),
        )
    except service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    except service.UsernameAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )


@user_authenticated_router.patch(
    "/set-password", status_code=status.HTTP_204_NO_CONTENT
)
async def update_password(
    request: PasswordUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    try:
        await service.set_password(
            db_session,
            current_user,
            request.new_password.get_secret_value(),
            request.current_password.get_secret_value(),
        )
    except service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )


@user_authenticated_router.patch(
    "/set-phone-number", status_code=status.HTTP_204_NO_CONTENT
)
async def update_phone_number(
    request: PhoneNumberUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    try:
        await service.set_phone_number(
            db_session,
            current_user,
            request.new_phone_number,
            request.current_password.get_secret_value(),
        )
    except service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    except service.PhoneNumberAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already exists",
        )


@user_authenticated_router.patch("/set-email", status_code=status.HTTP_204_NO_CONTENT)
async def update_email(
    request: EmailUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    try:
        await service.set_email(
            db_session,
            current_user,
            request.new_email,
            request.current_password.get_secret_value(),
        )
    except service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    except service.EmailAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )


@user_authenticated_router.patch("/set-school", status_code=status.HTTP_204_NO_CONTENT)
async def update_school(
    request: SchoolUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    await service.set_school(
        db_session, current_user, new_school_id=request.new_school_id
    )


@user_authenticated_router.patch(
    "/set-chosen-college", status_code=status.HTTP_204_NO_CONTENT
)
async def update_chosen_college(
    request: CollegeUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    await service.set_chosen_college(
        db_session, current_user, request.new_chosen_college
    )


@user_authenticated_router.patch(
    "/set-chosen-course", status_code=status.HTTP_204_NO_CONTENT
)
async def update_chosen_course(
    request: CourseUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    await service.set_chosen_course(db_session, current_user, request.new_chosen_course)


@user_authenticated_router.patch(
    "/set-commitment", status_code=status.HTTP_204_NO_CONTENT
)
async def update_commitment(
    request: CommitmentUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    await service.set_commitment(db_session, current_user, request.commitment)


@user_authenticated_router.patch(
    "/set-education-level", status_code=status.HTTP_204_NO_CONTENT
)
async def update_education_level(
    request: EducationLevelUpdateRequest,
    current_user: CurrentUserAnnotated,
    db_session: DBSessionAnnotated,
):
    await service.set_education_level(db_session, current_user, request.education_level)


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


@user_authenticated_router.get("/stats", response_model=UserStatsMeResponse)
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
        )


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
    school_filter: int | None = None,
    course_filter: str | None = None,
    score_type: Literal["dynamic", "percentage"] = "dynamic",
    education_level_filter: EducationLevel | None = None,
    subject: str | None = None,
):
    if score_type == "dynamic" and subject is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subject is not allowed for dynamic score type",
        )
    return await service.get_ranking(
        db_session,
        current_user.id,
        score_type=score_type,
        school_filter=school_filter,
        course_filter=course_filter,
        education_level_filter=education_level_filter,
        subject=subject,
    )


@router.post(
    "/online-info",
    response={200: list[OnlineInfo]},
    url_name="user_online_info",
)
async def get_online_info(request, user_ids_in: UserIdsIn):
    return await user_service.get_online_info(user_ids_in.user_ids)


@router.get(
    "/me/balance",
    response={200: BalanceOut},
    url_name="get_balance",
)
async def get_balance(request):
    try:
        return {"balance": await user_service.get_balance(request.auth.id)}
    except user_service.UserNotFoundError:
        raise HttpError(404, "User not found")


user_router.include_router(user_authenticated_router)
