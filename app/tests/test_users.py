from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from tests.factories import CollegeFactory, CourseFactory, SchoolFactory, UserFactory
from users.models import User


async def test_create_user_followed_by_jwt_and_user_me(client: AsyncClient):
    user = UserFactory.build()
    response = await client.post(
        "/users",
        json={
            "username": user.username,
            "password": "defaultpassword",
            "phone_number": user.phone_number,
            "email": user.email,
            "school_id": user.school_id,
            "chosen_college": user.chosen_college.name,
            "chosen_course": user.chosen_course.name,
            "education_level": user.education_level.value,
            "referred_by_username": "",
            "commitment": user.commitment,
        },
    )
    assert response.status_code == 201
    response_data = response.json()
    user_id = response_data["id"]

    # Check response data
    assert response_data["username"] == user.username
    assert response_data["phone_number"] == user.phone_number
    assert response_data["email"] == user.email
    assert response_data["school_id"] == user.school_id
    assert response_data["commitment"] == user.commitment
    assert response_data["education_level"] == user.education_level.value
    assert response_data["chosen_college"] == user.chosen_college.name
    assert response_data["chosen_course"] == user.chosen_course.name
    assert response_data["referral_count"] == 0

    # Login with new user
    token_response = await client.post(
        "/token/pair",
        data={
            "username": user.username,
            "password": "defaultpassword",
        },
    )
    assert token_response.status_code == 200

    # Get user details
    headers = {"Authorization": f"Bearer {token_response.json()['access']}"}
    me_response = await client.get("/users/me", headers=headers)
    assert me_response.status_code == 200
    me_data = me_response.json()

    assert me_data["id"] == user_id
    assert me_data["username"] == user.username
    assert me_data["phone_number"] == user.phone_number
    assert me_data["email"] == user.email
    assert me_data["school_id"] == user.school_id
    assert me_data["commitment"] == user.commitment
    assert me_data["education_level"] == user.education_level.value
    assert me_data["chosen_college"] == user.chosen_college.name
    assert me_data["chosen_course"] == user.chosen_course.name


async def test_create_user_whitespace(client: AsyncClient):
    user = UserFactory.build()
    response = await client.post(
        "/users",
        json={
            "username": f"  {user.username}  ",
            "password": "defaultpassword",
            "phone_number": user.phone_number,
            "email": user.email,
            "school_id": user.school_id,
            "chosen_college": user.chosen_college.name,
            "chosen_course": user.chosen_course.name,
            "education_level": user.education_level.value,
        },
    )
    assert response.status_code == 201
    response_data = response.json()
    assert response_data["username"] == user.username

    # Login with new user
    token_response = await client.post(
        "/token/pair",
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
        "school_id": user2_data.school.id,
        "chosen_college": user2_data.chosen_college.name,
        "chosen_course": user2_data.chosen_course.name,
        "education_level": user2_data.education_level.value,
        "commitment": user2_data.commitment,
    }
    response = await client.post("/users", json=user_dict)
    assert response.status_code == 409


async def test_create_user_fail_username_empty(client: AsyncClient):
    user = UserFactory.build()
    user_dict = {
        "username": "",
        "password": "defaultpassword",
        "phone_number": user.phone_number,
        "email": user.email,
        "school_id": user.school.id,
        "chosen_college": user.chosen_college.name,
        "chosen_course": user.chosen_course.name,
        "education_level": user.education_level.value,
        "commitment": user.commitment,
    }
    response = await client.post("/users", json=user_dict)
    assert response.status_code == 422


async def test_retrieve_user_me(auth_client: AsyncClient, user: User):
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == user.id
    assert response_data["username"] == user.username
    assert response_data["phone_number"] == user.phone_number
    assert response_data["email"] == user.email
    assert response_data["school_id"] == (user.school.id if user.school else None)
    assert response_data["commitment"] == user.commitment
    assert response_data["education_level"] == user.education_level.value


async def test_update_username(auth_client: AsyncClient, user: User):
    data = {"new_username": "newname", "current_password": "defaultpassword"}
    response = await auth_client.patch("/users/set-username", json=data)
    assert response.status_code == 204
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["username"] == "newname"


async def test_update_username_already_exists(
    auth_client: AsyncClient,
):
    existing_user = await UserFactory.create()
    data = {
        "new_username": existing_user.username,
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-username", json=data)
    assert response.status_code == 409
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["username"] != existing_user.username


async def test_update_username_already_exists_case_insensitive_and_whitespace(
    auth_client: AsyncClient,
):
    existing_user = await UserFactory.create()
    data = {
        "new_username": f"  {existing_user.username.upper()}  ",
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-username", json=data)
    assert response.status_code == 409
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["username"] != existing_user.username


async def test_update_password(auth_client: AsyncClient, user: User):
    data = {
        "new_password": "newpassword605",
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-password", json=data)
    assert response.status_code == 204
    token_response = await auth_client.post(
        "/token/pair",
        data={"username": user.username, "password": "newpassword605"},
    )
    assert token_response.status_code == 200


async def test_update_phone_number(auth_client: AsyncClient, user: User):
    data = {
        "new_phone_number": "21999202390",
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-phone-number", json=data)
    assert response.status_code == 204
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["phone_number"] == "tel:+55-21-99920-2390"


async def test_update_phone_number_already_exists(
    auth_client: AsyncClient,
):
    existing_user = await UserFactory.create()
    data = {
        "new_phone_number": existing_user.phone_number,
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-phone-number", json=data)
    assert response.status_code == 409
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["phone_number"] != existing_user.phone_number


async def test_update_phone_number_invalid(auth_client: AsyncClient, user: User):
    data = {
        "new_phone_number": "invalid",
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-phone-number", json=data)
    assert response.status_code == 422
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["phone_number"] != "invalid"


async def test_update_email(auth_client: AsyncClient, user: User):
    data = {
        "new_email": "test@example.com",
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-email", json=data)
    assert response.status_code == 204
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["email"] == "test@example.com"


async def test_update_email_already_exists(
    auth_client: AsyncClient,
):
    existing_user = await UserFactory.create()
    data = {
        "new_email": existing_user.email,
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-email", json=data)
    assert response.status_code == 409
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["email"] != existing_user.email


async def test_update_email_invalid(auth_client: AsyncClient, user: User):
    data = {
        "new_email": "invalid",
        "current_password": "defaultpassword",
    }
    response = await auth_client.patch("/users/set-email", json=data)
    assert response.status_code == 422
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["email"] != "invalid"


async def test_update_school(
    auth_client: AsyncClient,
):
    school = await SchoolFactory.create()
    data = {
        "new_school_id": school.id,
    }
    response = await auth_client.patch("/users/set-school", json=data)
    assert response.status_code == 204
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["school_id"] == school.id


async def test_update_school_to_blank(auth_client: AsyncClient):
    data = {
        "new_school_id": None,
    }
    response = await auth_client.patch("/users/set-school", json=data)
    assert response.status_code == 204
    # get the user details
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["school_id"] is None


async def test_update_chosen_college(
    auth_client: AsyncClient,
):
    college = await CollegeFactory.create()
    data = {
        "new_chosen_college": college.name,
    }
    response = await auth_client.patch("/users/set-chosen-college", json=data)
    assert response.status_code == 204
    # get the user details
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["chosen_college"] == college.name


async def test_update_chosen_college_to_blank(auth_client: AsyncClient):
    data = {
        "new_chosen_college": "",
    }
    response = await auth_client.patch("/users/set-chosen-college", json=data)
    assert response.status_code == 204
    # get the user details
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["chosen_college"] == ""


async def test_update_chosen_course(
    auth_client: AsyncClient,
):
    course = await CourseFactory.create()
    data = {
        "new_chosen_course": course.name,
    }
    response = await auth_client.patch("/users/set-chosen-course", json=data)
    assert response.status_code == 204
    # get the user details
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["chosen_course"] == course.name


async def test_update_chosen_course_to_blank(auth_client: AsyncClient):
    data = {
        "new_chosen_course": "",
    }
    response = await auth_client.patch("/users/set-chosen-course", json=data)
    assert response.status_code == 204
    # get the user details
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["chosen_course"] == ""


async def test_update_commitment(auth_client: AsyncClient):
    data = {
        "commitment": 10,
    }
    response = await auth_client.patch("/users/set-commitment", json=data)
    assert response.status_code == 204
    # get the user details
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["commitment"] == 10


async def test_update_education_level(auth_client: AsyncClient):
    data = {
        "education_level": "COL",
    }
    response = await auth_client.patch("/users/set-education-level", json=data)
    assert response.status_code == 204
    # get the user details
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["education_level"] == "COL"


async def test_destroy_user(auth_client: AsyncClient):
    data = {"current_password": "defaultpassword"}
    response = await auth_client.request(
        "DELETE",
        "/users/me",
        json=data,
    )
    assert response.status_code == 204
    # Check user doesn't exist
    response = await auth_client.get("/users/me")
    assert response.status_code == 401


async def test_destroy_user_wrong_password(auth_client: AsyncClient):
    data = {"current_password": "wrongpassword"}
    response = await auth_client.request(
        "DELETE",
        "/users/me",
        json=data,
    )
    assert response.status_code == 401
    # Check user still exists
    response = await auth_client.get("/users/me")
    assert response.status_code == 200


async def test_retrieve_user_stats_me(auth_client: AsyncClient, user: User):
    response = await auth_client.get("/users/stats")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == user.id
    assert response_data["username"] == user.username
    assert response_data["streak"] == 0
    assert response_data["done_today"] is False
    assert response_data["total_answers"] == 0
    assert response_data["correct_answers"] == 0
    assert "area_expected_scores" in response_data
    assert len(response_data["area_expected_scores"]) == 4
    for area in [
        "Matemática",
        "Linguagem",  # deveria ser Linguagens, mas o front ta esperando errado
        "Ciências Humanas",
        "Ciências da Natureza",
    ]:
        assert area in response_data["area_expected_scores"]
        assert isinstance(response_data["area_expected_scores"][area], float)
    assert "score" in response_data
    assert isinstance(response_data["score"], float)


async def test_retrieve_user_stats(auth_client: AsyncClient, user: User):
    response = await auth_client.get(f"/users/stats/{user.username}")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == user.id
    assert response_data["username"] == user.username
    assert response_data["school_id"] == user.school.id
    assert response_data["chosen_college"] == (
        "" if user.chosen_college is None else user.chosen_college.name
    )
    assert response_data["chosen_course"] == (
        "" if user.chosen_course is None else user.chosen_course.name
    )
    assert response_data["education_level"] == user.education_level

    assert "area_expected_scores" in response_data
    assert len(response_data["area_expected_scores"]) == 4
    for area in [
        "Matemática",
        "Linguagem",  # deveria ser Linguagens, mas o front ta esperando errado
        "Ciências Humanas",
        "Ciências da Natureza",
    ]:
        assert area in response_data["area_expected_scores"]
        assert isinstance(response_data["area_expected_scores"][area], float)
    assert "score" in response_data
    assert isinstance(response_data["score"], float)


async def test_check_contacts(
    auth_client: AsyncClient,
):
    users: list[User] = []
    for _ in range(7):
        user = await UserFactory.create()
        users.append(user)
    search_users: list[User] = []
    for i in range(1, 8):
        user = await UserFactory.create(username=f"searchuser{i}")
        search_users.append(user)

    url = "/users/check-contacts?page=1&page_size=4"
    phone_numbers = [str(user.phone_number) for user in users] + ["+551123111111"]
    data = {"phone_numbers": phone_numbers}
    response = await auth_client.post(url, json=data)
    assert response.status_code == 200
    results = response.json()["results"]
    response_ids = [user["id"] for user in results]
    assert len(response_ids) == 4

    new_url = "/users/check-contacts?page=2&page_size=4"
    new_response = await auth_client.post(new_url, json=data)
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

    assert "+551123111111" not in response_phone_numbers


async def test_search_username(
    auth_client: AsyncClient,
):
    users: list[User] = []
    for _ in range(7):
        user = await UserFactory.create()
        users.append(user)
    search_users: list[User] = []
    for i in range(1, 8):
        user = await UserFactory.create(username=f"searchuser{i}")
        search_users.append(user)

    url = "/users/search?username=searchuser&page=1&page_size=4"
    response = await auth_client.get(url)
    assert response.status_code == 200
    results = response.json()["results"]
    response_ids = [user["id"] for user in results]
    assert len(response_ids) == 4

    new_url = "/users/search?username=searchuser&page=2&page_size=4"
    new_response = await auth_client.get(new_url)
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
    current_user = await auth_client.get("/users/me")
    current_user_data = current_user.json()
    assert current_user_data["id"] not in response_ids


async def test_retrieve_sentinel_users(
    db_session: AsyncSession, auth_client: AsyncClient
):
    # Get sentinel users
    url = "/users/sentinel"
    response = await auth_client.get(url)
    assert response.status_code == 200
    response_data = response.json()
    response_ids = [user["id"] for user in response_data]
    response_usernames = [user["username"] for user in response_data]

    assert len(response_ids) == 3

    deleted_user = (
        await db_session.execute(select(User).where(User.username == "deleted_user"))
    ).scalar_one()
    system_user = (
        await db_session.execute(select(User).where(User.username == "system_user"))
    ).scalar_one()
    pico_user = (
        await db_session.execute(select(User).where(User.username == "pico_user"))
    ).scalar_one()

    assert deleted_user.id in response_ids
    assert deleted_user.username in response_usernames
    assert system_user.id in response_ids
    assert system_user.username in response_usernames
    assert pico_user.id in response_ids
    assert pico_user.username in response_usernames
