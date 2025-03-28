import logging
from typing import Annotated

import users.jwt_token as jwt_token
from deps import CurrentUserDep, DBSessionDep
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from users import service
from users.jwt_token import TokenError
from users.schemas import (
    CollegeUpdateRequest,
    CommitmentUpdateRequest,
    CourseUpdateRequest,
    EducationLevelUpdateRequest,
    EmailUpdateRequest,
    PasswordRequest,
    PasswordUpdateRequest,
    PhoneNumberUpdateRequest,
    RefreshRequest,
    SchoolUpdateRequest,
    TokenResponse,
    UserIn,
    UsernameUpdateRequest,
    UserOut,
    UserStatsMeResponse,
    UserStatsResponse,
    VerifyRequest,
)

logger = logging.getLogger(__name__)

token_router = APIRouter(prefix="/token", tags=["token"])
user_router = APIRouter(prefix="/users", tags=["users"])


@token_router.post("/pair", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db_session: DBSessionDep
):
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
    refresh_request: RefreshRequest, db_session: DBSessionDep
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
async def verify_token(verify_request: VerifyRequest, db_session: DBSessionDep) -> None:
    try:
        await jwt_token.process_token(db_session, verify_request.token)
    except TokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)


@user_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    background_tasks: BackgroundTasks,
    db_session: DBSessionDep,
    user_in: UserIn,
):
    logger.info("Starting create_user")
    try:
        db_user = await service.create_user(
            background_tasks,
            db_session,
            user_in.username.strip(),
            user_in.password.get_secret_value(),
            user_in.phone_number,
            user_in.email,
            user_in.chosen_college,
            user_in.chosen_course,
            user_in.education_level,
            user_in.commitment,
            user_in.referred_by_username,
            user_in.school_id,
            user_in.signup_source,
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


@user_router.get("/me", response_model=UserOut, status_code=status.HTTP_200_OK)
async def read_users_me(current_user: CurrentUserDep, db_session: DBSessionDep):
    await db_session.refresh(
        current_user,
        ["chosen_college", "chosen_course", "referrals"],
    )
    return current_user


@user_router.patch("/set-username", status_code=status.HTTP_204_NO_CONTENT)
async def update_username(
    request: UsernameUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
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


@user_router.patch("/set-password", status_code=status.HTTP_204_NO_CONTENT)
async def update_password(
    request: PasswordUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
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


@user_router.patch("/set-phone-number", status_code=status.HTTP_204_NO_CONTENT)
async def update_phone_number(
    request: PhoneNumberUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
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


@user_router.patch("/set-email", status_code=status.HTTP_204_NO_CONTENT)
async def update_email(
    request: EmailUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
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


@user_router.patch("/set-school", status_code=status.HTTP_204_NO_CONTENT)
async def update_school(
    request: SchoolUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
):
    await service.set_school(
        db_session, current_user, new_school_id=request.new_school_id
    )


@user_router.patch("/set-chosen-college", status_code=status.HTTP_204_NO_CONTENT)
async def update_chosen_college(
    request: CollegeUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
):
    await service.set_chosen_college(
        db_session, current_user, request.new_chosen_college
    )


@user_router.patch("/set-chosen-course", status_code=status.HTTP_204_NO_CONTENT)
async def update_chosen_course(
    request: CourseUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
):
    await service.set_chosen_course(db_session, current_user, request.new_chosen_course)


@user_router.patch("/set-commitment", status_code=status.HTTP_204_NO_CONTENT)
async def update_commitment(
    request: CommitmentUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
):
    await service.set_commitment(db_session, current_user, request.commitment)


@user_router.patch("/set-education-level", status_code=status.HTTP_204_NO_CONTENT)
async def update_education_level(
    request: EducationLevelUpdateRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
):
    await service.set_education_level(db_session, current_user, request.education_level)


@user_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    request: PasswordRequest,
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
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


@user_router.get("/stats", response_model=UserStatsMeResponse)
async def get_user_stats_me(
    current_user: CurrentUserDep,
    db_session: DBSessionDep,
):
    user_stats = await service.get_user_stats(db_session, user_id=current_user.id)
    return user_stats


@user_router.get("/stats/{username}", response_model=UserStatsResponse)
async def get_stats_by_username(
    username: str,
    db_session: DBSessionDep,
):
    try:
        user_stats = await service.get_user_stats(db_session, username=username)
        return user_stats
    except service.UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
