async def test_list_schools(client, school, school2):
    response = await client.get("/schools")
    assert response.status_code == 200
    assert len(response.json()) == 2
    schools = response.json()
    assert len(schools) == 2
    assert schools[0]["id"] == school["id"]
    assert schools[0]["name"] == school["name"]
    assert schools[1]["id"] == school2["id"]
    assert schools[1]["name"] == school2["name"]


async def test_get_school_detail(client, school):
    response = await client.get(f"/schools/{school['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == school["id"]
    assert response.json()["name"] == school["name"]


async def test_get_school_detail_not_found(client):
    response = await client.get(f"/schools/{9999}")
    assert response.status_code == 404


async def test_create_school(client):
    response = await client.post("/schools", json={"name": "New School"})
    assert response.status_code == 201
    assert response.json()["name"] == "New School"

    # assert that the school exists
    response = await client.get("/schools")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "New School"


async def test_create_school_invalid(client):
    response = await client.post("/schools", json={"name": ""})
    assert response.status_code == 422
