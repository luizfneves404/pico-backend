import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    WebSocket,
    WebSocketDisconnect,
    WebSocketException,
    status,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

import app.ws.service as ws_service
from app.database import db_manager
from app.users import jwt_token
from app.users.models import User
from app.ws.schemas import MessageType, WebsocketMessage

WEBSOCKET_URL = "/ws"

router = APIRouter(prefix=WEBSOCKET_URL, tags=["websockets"])
logger = logging.getLogger(__name__)


async def get_db_session_websocket():
    """
    This function is used to get a database session in websocket endpoints,
    allowing you to begin and commit transactions whenever you want.
    It will begin a transaction and yield the session.
    The transaction will be committed if the session is used.
    If an exception is raised, the transaction will be rolled back.
    If you wish to keep the session useful after an error, use nested transactions.
    """
    async with db_manager.session() as session:
        yield session


DBSessionAnnotated = Annotated[AsyncSession, Depends(get_db_session_websocket)]


async def get_current_user(
    token: Annotated[str, Query()], db_session: DBSessionAnnotated
) -> User:
    try:
        async with db_session.begin():
            return await jwt_token.process_token(db_session, token, "access")
    except jwt_token.TokenError as e:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=str(e),
        ) from e


CurrentUserAnnotated = Annotated[User, Depends(get_current_user)]


# TODO: record on mixpanel the disconnect and connect events
@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    db_session: DBSessionAnnotated,
    current_user: CurrentUserAnnotated,
):
    """WebSocket endpoint with JWT authentication."""
    # Accept connection after successful authentication
    await websocket.accept()
    logger.info(
        f"WebSocket connection established for user {current_user.id}"
        " ({current_user.username})"
    )

    # Handle user connection event
    async with db_session.begin():
        await ws_service.handle_user_connection_event(db_session, current_user.id)

    try:
        while True:
            data = await websocket.receive_json()

            message = WebsocketMessage.model_validate(data)

            await handle_websocket_message(websocket, message)

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket disconnected normally for user {current_user.id}"
            " ({current_user.username})"
        )
    except ValidationError:
        await websocket.close(
            code=status.WS_1007_INVALID_FRAME_PAYLOAD_DATA,
            reason="Invalid message format",
        )

    except Exception:
        try:
            await websocket.close(
                code=status.WS_1011_INTERNAL_ERROR,
                reason="Internal server error",
            )
            logger.exception(
                f"WebSocket disconnected with error for user {current_user.id}"
                " ({current_user.username})"
            )
        except Exception:
            pass  # Connection might already be closed
        raise

    finally:
        async with db_session.begin():
            await ws_service.handle_user_disconnection_event(
                db_session, current_user.id
            )


async def handle_websocket_message(
    websocket: WebSocket,
    message: WebsocketMessage,
):
    """Handle a message from the websocket."""
    match message.message_type:
        case MessageType.ECHO:
            await websocket.send_json(
                WebsocketMessage(
                    message_type=MessageType.ECHO,
                    message=message.message,
                ).model_dump()
            )
