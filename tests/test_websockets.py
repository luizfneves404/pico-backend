"""from models import User as UserDBModel
from sqlalchemy import select


async def test_notifications(client):
    with client.websocket_connect("/ws/notifications") as websocket:
        websocket.send_json({"message": "Hello WebSocket"})
        data = websocket.receive_json()
        assert data == {"message": "Hello WebSocket"}
"""
