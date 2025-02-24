"""from sqlalchemy import select


def chatroom_payload(member_ids):
    return {
        "name": "coolchatroom",
        "members_ids": member_ids,
    }


async def create_chatrooms(async_client, payload):
    return await async_client.post("/chatrooms", json=payload)


async def get_chatrooms_from_db(db_session, name):
    return (
        await db_session.scalars(
            select(ChatRoomDBModel).where(ChatRoomDBModel.name == name)
        )
    ).first()


async def test_create_chatroom(auth_async_client, db_session, new_user2):
    payload = chatroom_payload([new_user2["id"]])
    response = await create_chatrooms(auth_async_client, payload)
    assert response.status_code == 201
    response_data = response.json()
    assert response_data["name"] == payload["name"]
    assert response_data["members_ids"] == payload["members_ids"]

    chatroom = await get_chatrooms_from_db(db_session, payload["name"])
    assert chatroom is not None
    assert chatroom.name == payload["name"]"""
