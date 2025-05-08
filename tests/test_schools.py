async def test_list_schools(client):
    # Create two schools
    school1_response = await client.post("/api/schools", json={"name": "School 1"})
    assert school1_response.status_code == 201
    school1 = school1_response.json()

    school2_response = await client.post("/api/schools", json={"name": "School 2"})
    assert school2_response.status_code == 201
    school2 = school2_response.json()

    # Get list of schools
    response = await client.get("/api/schools")
    assert response.status_code == 200
    schools = response.json()
    assert len(schools) == 2
    assert schools[0]["id"] == school1["id"]
    assert schools[0]["name"] == school1["name"]
    assert schools[1]["id"] == school2["id"]
    assert schools[1]["name"] == school2["name"]


async def test_get_school_detail(client):
    # Create a school
    create_response = await client.post("/api/schools", json={"name": "Test School"})
    assert create_response.status_code == 201
    school = create_response.json()

    # Get school details
    response = await client.get(f"/api/schools/{school['id']}/detail")
    assert response.status_code == 200
    assert response.json()["id"] == school["id"]
    assert response.json()["name"] == school["name"]


async def test_get_school_detail_not_found(client):
    response = await client.get(f"/api/schools/{9999}/detail")
    assert response.status_code == 404


async def test_create_school(client):
    response = await client.post("/api/schools", json={"name": "New School"})
    assert response.status_code == 201
    assert response.json()["name"] == "New School"

    # assert that the school exists
    response = await client.get("/api/schools")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "New School"


async def test_create_school_invalid(client):
    response = await client.post("/api/schools", json={"name": ""})
    assert response.status_code == 422
