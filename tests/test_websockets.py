from unittest.mock import patch

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws

import app.users.jwt_token as jwt_token
from app.ws.schemas import MessageType, WebsocketMessage
from tests.conftest import BASE_URL


class TestWebSocketAuthentication:
    """Test WebSocket JWT authentication functionality."""

    async def test_websocket_missing_token(self, ws_client: AsyncClient):
        """Test WebSocket connection fails when no token is provided."""
        with pytest.raises(Exception):
            async with aconnect_ws(f"{BASE_URL}/api/ws", client=ws_client) as ws:
                await ws.receive_json()

    async def test_websocket_invalid_token(self, ws_client: AsyncClient):
        """Test WebSocket connection fails with invalid token."""
        with pytest.raises(Exception):
            async with aconnect_ws(
                f"{BASE_URL}/api/ws?token=invalid_token", client=ws_client
            ) as ws:
                await ws.receive_json()

    async def test_websocket_expired_token(self, ws_client: AsyncClient):
        """Test WebSocket connection fails with expired token."""
        with patch.object(jwt_token, "process_token") as mock_process_token:
            mock_process_token.side_effect = jwt_token.TokenError("Token expired")

            with pytest.raises(Exception):
                async with aconnect_ws(
                    f"{BASE_URL}/api/ws?token=expired_token", client=ws_client
                ) as ws:
                    await ws.receive_json()


class TestWebSocketMessaging:
    """Test WebSocket message handling functionality."""

    async def test_echo_message(
        self, ws_client: AsyncClient, websocket_access_token: str
    ):
        """Test echo message functionality."""
        async with aconnect_ws(
            f"{BASE_URL}/api/ws?token={websocket_access_token}", client=ws_client
        ) as ws:
            await ws.send_json({"message_type": "echo", "message": "Hello!"})
            message = await ws.receive_json()
            assert message == {"message_type": "echo", "message": "Hello!"}

    async def test_invalid_message_format(
        self, ws_client: AsyncClient, websocket_access_token: str
    ):
        """Test handling of invalid message format."""
        async with aconnect_ws(
            f"{BASE_URL}/api/ws?token={websocket_access_token}", client=ws_client
        ) as websocket:
            # Send invalid message format (missing required fields)
            await websocket.send_json({"invalid": "format"})

            # Connection should be closed due to validation error
            with pytest.raises(Exception):
                await websocket.receive_json()

    async def test_unsupported_message_type(
        self, ws_client: AsyncClient, websocket_access_token: str
    ):
        """Test handling of unsupported message types."""
        async with aconnect_ws(
            f"{BASE_URL}/api/ws?token={websocket_access_token}", client=ws_client
        ) as websocket:
            # Send message with unsupported type
            invalid_msg = {"message_type": "unsupported_type", "message": "test"}

            with pytest.raises(Exception):
                await websocket.send_json(invalid_msg)
                await websocket.receive_json()

    async def test_multiple_messages(
        self, ws_client: AsyncClient, websocket_access_token: str
    ):
        """Test sending multiple messages in sequence."""
        async with aconnect_ws(
            f"{BASE_URL}/api/ws?token={websocket_access_token}", client=ws_client
        ) as websocket:
            messages = ["Message 1", "Message 2", "Message 3"]

            for test_message in messages:
                echo_msg = WebsocketMessage(
                    message_type=MessageType.ECHO, message=test_message
                )
                await websocket.send_json(echo_msg.model_dump())

                response = await websocket.receive_json()
                received_msg = WebsocketMessage.model_validate(response)

                assert received_msg.message_type == MessageType.ECHO
                assert received_msg.message == test_message
