import logging
from typing import Annotated

import users.token as token
from deps import CurrentUserDep, DBSessionDep
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from users import service
from users.schemas import (
    RefreshRequest,
    TokenResponse,
    UserIn,
    UserOut,
    VerifyRequest,
)
from users.token import TokenError

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
    access_token, refresh_token = token.generate_tokens(user)
    return {"access": access_token, "refresh": refresh_token}


@token_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_request: RefreshRequest, db_session: DBSessionDep
) -> TokenResponse:
    try:
        user = await token.process_token(db_session, refresh_request.refresh, "refresh")
        access, refresh = token.generate_tokens(user)
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
        await token.process_token(db_session, verify_request.token)
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
            user_in.password,
            user_in.phone_number,
            user_in.email,
            user_in.chosen_college,
            user_in.chosen_course,
            user_in.education_level,
            user_in.commitment,
            user_in.referred_by_username,
            user_in.school,
            user_in.school_id,
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
        ["school", "chosen_college", "chosen_course", "referral_count"],
    )
    return current_user
