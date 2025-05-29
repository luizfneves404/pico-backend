from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.users.models import User
from tests.factories import (
    CollegeFactory,
    CourseFactory,
    SchoolFactory,
    UserFactory,
)


async def test_create_user_followed_by_jwt_and_user_me(
    client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        school = await SchoolFactory.create(session)
        college = await CollegeFactory.create(session)
        course = await CourseFactory.create(session)
        user = UserFactory.build()
    response = await client.post(
        "/api/users",
        json={
            "username": user.username,
            "password": "defaultpassword",
            "phone_number": user.phone_number,
            "email": user.email,
            "current_education": {
                "level": "TYHS",
                "institution_id": school.id,
            },
            "intended_education": {
                "level": "COL",
                "institution_id": college.id,
                "course_id": course.id,
            },
            "referred_by_username": "",
        },
    )
    assert response.status_code == 201
    response_data = response.json()
    user_id = response_data["id"]

    # Check response data
    assert response_data["username"] == user.username
    assert response_data["phone_number"] == user.phone_number
    assert response_data["email"] == user.email
    assert response_data["current_education"]["level"] == "TYHS"
    assert response_data["intended_education"]["level"] == "COL"

    # Login with new user
    token_response = await client.post(
        "/api/token/pair",
        data={
            "username": user.username,
            "password": "defaultpassword",
        },
    )
    assert token_response.status_code == 200

    # Get user details
    headers = {"Authorization": f"Bearer {token_response.json()['access']}"}
    me_response = await client.get("/api/users/me", headers=headers)
    assert me_response.status_code == 200
    me_data = me_response.json()

    assert me_data["id"] == user_id
    assert me_data["username"] == user.username
    assert me_data["phone_number"] == user.phone_number
    assert me_data["email"] == user.email
    assert me_data["current_education"]["level"] == "TYHS"
    assert me_data["current_education"]["institution_id"] == school.id
    assert me_data["current_education"]["course_id"] == course.id
    assert me_data["intended_education"]["level"] == "COL"
    assert me_data["intended_education"]["institution_id"] == college.id
    assert me_data["intended_education"]["course_id"] == course.id


async def test_create_user_whitespace(client: AsyncClient):
    user = UserFactory.build()
    response = await client.post(
        "/api/users",
        json={
            "username": f"  {user.username}  ",
            "password": "defaultpassword",
            "phone_number": user.phone_number,
            "email": user.email,
            "current_education": {"level": "TYHS", "institution_id": 1, "course_id": 1},
        },
    )
    assert response.status_code == 201
    response_data = response.json()
    assert response_data["username"] == user.username

    # Login with new user
    token_response = await client.post(
        "/api/token/pair",
        data={
            "username": user.username,
            "password": "defaultpassword",
        },
    )
    assert token_response.status_code == 200


async def test_create_user_fail_username_case_insensitive_and_whitespace(
    client: AsyncClient, user: User
):
    user2_data = UserFactory.build()
    user_dict = {
        "username": f"  {user.username.upper()}  ",
        "password": "defaultpassword",
        "phone_number": user2_data.phone_number,
        "email": user2_data.email,
        "current_education": {"level": "TYHS", "institution_id": 1, "course_id": 1},
    }
    response = await client.post("/api/users", json=user_dict)
    assert response.status_code == 409


async def test_create_user_fail_username_empty(client: AsyncClient):
    user = UserFactory.build()
    user_dict = {
        "username": "",
        "password": "defaultpassword",
        "phone_number": user.phone_number,
        "email": user.email,
        "current_education": {"level": "TYHS", "institution_id": 1, "course_id": 1},
    }
    response = await client.post("/api/users", json=user_dict)
    assert response.status_code == 422


async def test_retrieve_user_me(user_client: AsyncClient, user: User):
    response = await user_client.get("/api/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == user.id
    assert response_data["username"] == user.username
    assert response_data["phone_number"] == user.phone_number
    assert response_data["email"] == user.email
    assert response_data["xp_score"] == 0
    assert response_data["social_score"] == 0
    # Check that education data is present
    if response_data["current_education"]:
        assert "level" in response_data["current_education"]
        assert "institution_id" in response_data["current_education"]
        assert "course_id" in response_data["current_education"]


async def test_retrieve_other_user(user_client: AsyncClient, user: User):
    user2 = await UserFactory.create()
    response = await user_client.get(f"/api/users/other/{user2.id}")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == user2.id
    assert response_data["username"] == user2.username
    assert response_data["phone_number"] == user2.phone_number
    assert response_data["email"] == user2.email
    assert response_data["current_education"] is None
    assert response_data["intended_education"] is None
    assert response_data["xp_score"] == 0
    assert response_data["social_score"] == 0


async def test_update_username(user_client: AsyncClient, user: User):
    data = {"updates": {"username": "newname"}, "current_password": "defaultpassword"}
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "username" in response_data["updated_fields"]
    assert response_data["user"]["username"] == "newname"


async def test_update_username_already_exists(
    user_client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        existing_user = await UserFactory.create(session=session)
    data = {
        "updates": {"username": existing_user.username},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 409
    response = await user_client.get("/api/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["username"] != existing_user.username


async def test_update_username_already_exists_case_insensitive_and_whitespace(
    user_client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        existing_user = await UserFactory.create(session=session)
    data = {
        "updates": {"username": f"  {existing_user.username.upper()}  "},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 409
    response = await user_client.get("/api/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["username"] != existing_user.username


async def test_update_password(user_client: AsyncClient, user: User):
    data = {
        "updates": {"password": "newpassword605"},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "password" in response_data["updated_fields"]
    token_response = await user_client.post(
        "/api/token/pair",
        data={"username": user.username, "password": "newpassword605"},
    )
    assert token_response.status_code == 200


async def test_update_phone_number(user_client: AsyncClient, user: User):
    data = {
        "updates": {"phone_number": "21999202390"},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "phone_number" in response_data["updated_fields"]
    assert response_data["user"]["phone_number"] == "tel:+55-21-99920-2390"


async def test_update_phone_number_already_exists(
    user_client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        existing_user = await UserFactory.create(session=session)
    data = {
        "updates": {"phone_number": existing_user.phone_number},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 409
    response = await user_client.get("/api/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["phone_number"] != existing_user.phone_number


async def test_update_phone_number_invalid(user_client: AsyncClient, user: User):
    data = {
        "updates": {"phone_number": "invalid"},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 422
    response = await user_client.get("/api/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["phone_number"] != "invalid"


async def test_update_email(user_client: AsyncClient, user: User):
    data = {
        "updates": {"email": "test@example.com"},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "email" in response_data["updated_fields"]
    assert response_data["user"]["email"] == "test@example.com"


async def test_update_email_already_exists(
    user_client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        existing_user = await UserFactory.create(session=session)
    data = {
        "updates": {"email": existing_user.email},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 409
    response = await user_client.get("/api/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["email"] != existing_user.email


async def test_update_email_invalid(user_client: AsyncClient, user: User):
    data = {
        "updates": {"email": "invalid"},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 422
    response = await user_client.get("/api/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["email"] != "invalid"


async def test_update_current_education(
    user_client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        school = await SchoolFactory.create(session=session)
        course = await CourseFactory.create(session=session)
    data = {
        "updates": {
            "current_education": {
                "level": "TYHS",
                "institution_id": school.id,
                "course_id": course.id,
            }
        }
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "current_education" in response_data["updated_fields"]
    assert response_data["user"]["current_education"]["level"] == "TYHS"
    assert response_data["user"]["current_education"]["institution_id"] == school.id
    assert response_data["user"]["current_education"]["course_id"] == course.id


async def test_update_intended_education(
    user_client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        college = await CollegeFactory.create(session=session)
        course = await CourseFactory.create(session=session)
    data = {
        "updates": {
            "intended_education": {
                "level": "COL",
                "institution_id": college.id,
                "course_id": course.id,
            }
        }
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "intended_education" in response_data["updated_fields"]
    assert response_data["user"]["intended_education"]["level"] == "COL"
    assert response_data["user"]["intended_education"]["institution_id"] == college.id
    assert response_data["user"]["intended_education"]["course_id"] == course.id


async def test_destroy_user(user_client: AsyncClient):
    data = {"current_password": "defaultpassword"}
    response = await user_client.request(
        "DELETE",
        "/api/users/me",
        json=data,
    )
    assert response.status_code == 204
    # Check user doesn't exist
    response = await user_client.get("/api/users/me")
    assert response.status_code == 401


async def test_destroy_user_wrong_password(user_client: AsyncClient):
    data = {"current_password": "wrongpassword"}
    response = await user_client.request(
        "DELETE",
        "/api/users/me",
        json=data,
    )
    assert response.status_code == 401
    # Check user still exists
    response = await user_client.get("/api/users/me")
    assert response.status_code == 200


async def test_check_contacts(
    user_client: AsyncClient,
    session: AsyncSession,
):
    async with session.begin():
        users = await UserFactory.create_batch(7, session=session)
        search_users: list[User] = []
        for i in range(1, 8):
            user = await UserFactory.create(username=f"searchuser{i}", session=session)
            search_users.append(user)

    url = "/api/users/check-contacts?page=1&page_size=4"
    phone_numbers = [str(user.phone_number) for user in users] + ["+551123111111"]
    data = {"phone_numbers": phone_numbers}
    response = await user_client.post(url, json=data)
    assert response.status_code == 200
    results = response.json()["results"]
    response_ids = [user["id"] for user in results]
    assert len(response_ids) == 4

    new_url = "/api/users/check-contacts?page=2&page_size=4"
    new_response = await user_client.post(new_url, json=data)
    assert new_response.status_code == 200
    new_results = new_response.json()["results"]
    new_response_ids = [user["id"] for user in new_results]
    assert len(new_response_ids) == 3

    response_ids.extend(new_response_ids)

    for user in users:
        assert user.id in response_ids

    for search_user in search_users:
        assert search_user.id not in response_ids

    response_phone_numbers = [user["phone_number"] for user in results + new_results]

    for user in users:
        assert user.phone_number in response_phone_numbers

    assert "tel:+55-11-2311-1111" not in response_phone_numbers


async def test_search_username(user_client: AsyncClient, session: AsyncSession):
    async with session.begin():
        users = await UserFactory.create_batch(7, session=session)
        search_users: list[User] = []
        for i in range(1, 8):
            user = await UserFactory.create(username=f"searchuser{i}", session=session)
            search_users.append(user)

    url = "/api/users/search-username?username=searchuser&page=1&page_size=4"
    response = await user_client.get(url)
    assert response.status_code == 200
    results = response.json()["results"]
    response_ids = [user["id"] for user in results]
    assert len(response_ids) == 4

    new_url = "/api/users/search-username?username=searchuser&page=2&page_size=4"
    new_response = await user_client.get(new_url)
    assert new_response.status_code == 200
    new_results = new_response.json()["results"]
    new_response_ids = [user["id"] for user in new_results]
    assert len(new_response_ids) == 3

    response_ids.extend(new_response_ids)

    for search_user in search_users:
        assert search_user.id in response_ids

    for user in users:
        assert user.id not in response_ids

    # Assuming auth_client is authenticated with a user
    current_user = await user_client.get("/api/users/me")
    current_user_data = current_user.json()
    assert current_user_data["id"] not in response_ids


async def test_retrieve_sentinel_users(session: AsyncSession, user_client: AsyncClient):
    # Get sentinel users
    url = "/api/users/sentinel"
    response = await user_client.get(url)
    assert response.status_code == 200
    response_data = response.json()
    response_ids = [user["id"] for user in response_data]
    response_usernames = [user["username"] for user in response_data]

    assert len(response_ids) == 3
    async with session.begin():
        deleted_user = (
            await session.execute(select(User).where(User.username == "deleted"))
        ).scalar_one()
        system_user = (
            await session.execute(select(User).where(User.username == "system"))
        ).scalar_one()
        pico_user = (
            await session.execute(select(User).where(User.username == "pico"))
        ).scalar_one()

    assert deleted_user.id in response_ids
    assert deleted_user.username in response_usernames
    assert system_user.id in response_ids
    assert system_user.username in response_usernames
    assert pico_user.id in response_ids
    assert pico_user.username in response_usernames


async def test_get_balance(user_client: AsyncClient):
    url = "/api/users/me/balance"
    response = await user_client.get(url)
    assert response.status_code == 200
    assert response.json()["balance"] == 1000


async def test_unified_update_single_field(user_client: AsyncClient, user: User):
    data = {
        "updates": {"username": "newusername"},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "username" in response_data["updated_fields"]
    assert response_data["user"]["username"] == "newusername"


async def test_unified_update_multiple_fields(user_client: AsyncClient, user: User):
    data = {
        "updates": {"username": "newusername", "email": "new@example.com"},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "username" in response_data["updated_fields"]
    assert "email" in response_data["updated_fields"]
    assert response_data["user"]["username"] == "newusername"
    assert response_data["user"]["email"] == "new@example.com"


async def test_unified_update_sensitive_field_without_password(
    user_client: AsyncClient,
):
    data = {"updates": {"username": "newusername"}}
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 400


async def test_unified_update_mixed_fields(user_client: AsyncClient, user: User):
    data = {
        "updates": {"username": "mixeduser"},
        "current_password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "username" in response_data["updated_fields"]
    assert response_data["user"]["username"] == "mixeduser"


async def test_unified_update_no_changes(user_client: AsyncClient):
    data: dict[str, Any] = {"updates": {}}
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["updated_fields"] == []


async def test_unified_update_wrong_password(user_client: AsyncClient):
    data = {"updates": {"username": "wrongpass"}, "password": "wrongpassword"}
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 401


async def test_unified_update_duplicate_username(
    user_client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        existing_user = await UserFactory.create(session=session)

    data = {
        "updates": {"username": existing_user.username},
        "password": "defaultpassword",
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 409


async def test_unified_update_education(
    user_client: AsyncClient, session: AsyncSession
):
    async with session.begin():
        college = await CollegeFactory.create(session=session)
        course = await CourseFactory.create(session=session)

    data = {
        "updates": {
            "intended_education": {
                "level": "COL",
                "institution_id": college.id,
                "course_id": course.id,
            }
        }
    }
    response = await user_client.patch("/api/users/me", json=data)
    assert response.status_code == 200
    response_data = response.json()
    assert "intended_education" in response_data["updated_fields"]
    assert response_data["user"]["intended_education"]["level"] == "COL"
    assert response_data["user"]["intended_education"]["institution_id"] == college.id
    assert response_data["user"]["intended_education"]["course_id"] == course.id


async def test_update_user_fields_mixed_password_required(user_client: AsyncClient):
    """Test that password is required when updating mixed fields."""
    data = {
        "updates": {"username": "mixeduser"},
    }
    response = await user_client.patch("/users/me", json=data)
    assert response.status_code == 400

    response_data = response.json()
    assert "password is required" in response_data["detail"].lower()
