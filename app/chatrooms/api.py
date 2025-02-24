from chatrooms.chatroom_service import create_chatrooms as crud_create_chatrooms
from chatrooms.schemas import ChatRoomIn, ChatRoomOut, MemberOut
from deps import CurrentUserDep, DBSessionDep
from fastapi import APIRouter, status

router = APIRouter(prefix="/chatrooms", tags=["chatrooms"])


@router.post("", response_model=ChatRoomOut, status_code=status.HTTP_201_CREATED)
async def create_chatrooms(
    creator: CurrentUserDep, chatrooms: ChatRoomIn, db_session: DBSessionDep
) -> ChatRoomOut:
    db_chatrooms = await crud_create_chatrooms(
        db_session,
        creator,
        chatrooms,
    )
    await db_session.refresh(db_chatrooms)
    chatrooms_out = ChatRoomOut(
        id=db_chatrooms.id,
        name=db_chatrooms.name,
        timestamp=db_chatrooms.timestamp,
        members=[
            MemberOut(
                username=member.username,
                phone_number=member.phone_number,
                id=member.id,
                is_admin=member.role in [1, 2],
            )
            for member in db_chatrooms.members
        ],
    )

    return chatrooms_out
