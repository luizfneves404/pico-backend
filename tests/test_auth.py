import jwt
from httpx import AsyncClient

from app.config import settings
from app.users.models import User


async def test_token_obtain_pair(client: AsyncClient, user: User):
    response = await client.post(
        "/api/token/pair",
        data={
            "username": user.email,
            "password": "defaultpassword",
        },
    )
    assert response.status_code == 200
    response_data = response.json()
    assert "access" in response_data
    assert "refresh" in response_data

    # Verify token is valid
    decoded_token = jwt.decode(
        response_data["access"], settings.secret_key, algorithms=["HS256"]
    )
    assert decoded_token["user_id"] == user.id


async def test_token_obtain_pair_whitespace(client: AsyncClient, user: User):
    response = await client.post(
        "/api/token/pair",
        data={
            "username": f"  {user.email}  ",
            "password": "defaultpassword",
        },
    )
    assert response.status_code == 200
    response_data = response.json()

    # Verify token is valid
    decoded_token = jwt.decode(
        response_data["access"], settings.secret_key, algorithms=["HS256"]
    )
    assert decoded_token["user_id"] == user.id


async def test_token_verify(client: AsyncClient, user: User):
    token_response = await client.post(
        "/api/token/pair",
        data={
            "username": user.email,
            "password": "defaultpassword",
        },
    )
    access_token = token_response.json()["access"]

    response = await client.post(
        "/api/token/verify",
        json={"token": access_token},
    )
    assert response.status_code == 200


async def test_token_refresh(client: AsyncClient, user: User):
    token_response = await client.post(
        "/api/token/pair",
        data={
            "username": user.email,
            "password": "defaultpassword",
        },
    )
    refresh_token = token_response.json()["refresh"]

    response = await client.post(
        "/api/token/refresh",
        json={"refresh": refresh_token},
    )
    assert response.status_code == 200
    new_access_token = response.json()["access"]

    # Verify new token is valid
    decoded_token = jwt.decode(
        new_access_token, settings.secret_key, algorithms=["HS256"]
    )
    assert decoded_token["user_id"] == user.id


async def test_user_me_endpoint(client: AsyncClient, user: User):
    token_response = await client.post(
        "/api/token/pair",
        data={
            "username": user.email,
            "password": "defaultpassword",
        },
    )
    access_token = token_response.json()["access"]

    headers = {"Authorization": f"Bearer {access_token}"}
    response = await client.get("/api/users/me", headers=headers)
    assert response.status_code == 200
    user_data = response.json()

    assert user_data["id"] == user.id
    assert user_data["username"] == user.username
    assert user_data["phone_number"] == user.phone_number
    assert user_data["email"] == user.email
