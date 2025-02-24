from typing import Annotated

import users.token as token
import users.user_service as user_service
from deps import CurrentUserDep, DBSessionDep
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from users.schemas import (
    RefreshRequest,
    TokenResponse,
    UserIn,
    UserOut,
    VerifyRequest,
)
from users.token import TokenError

token_router = APIRouter(prefix="/token", tags=["token"])
user_router = APIRouter(prefix="/users", tags=["users"])


@token_router.post("/pair", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db_session: DBSessionDep
):
    user = await user_service.authenticate_user(
        db_session, form_data.username, form_data.password
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
    except user_service.UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )


@token_router.post("/verify", response_model=TokenResponse)
async def verify_token(verify_request: VerifyRequest, db_session: DBSessionDep) -> None:
    try:
        await token.process_token(db_session, verify_request.token)
    except TokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)


@user_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserIn, db_session: DBSessionDep):
    try:
        db_user = await user_service.create_user(
            db_session,
            user_in.username,
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
    except user_service.UsernameAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )
    except user_service.PhoneNumberAlreadyExists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already exists",
        )
    return db_user


@user_router.get("/me", response_model=UserOut, status_code=status.HTTP_200_OK)
async def read_users_me(current_user: CurrentUserDep, db_session: DBSessionDep):
    await db_session.refresh(
        current_user, ["chosen_college", "chosen_course", "referral_count"]
    )
    return current_user
