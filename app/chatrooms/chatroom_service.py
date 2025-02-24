import users.user_service as user_service
from chatrooms.models import Chatroom as ChatRoomDBModel
from chatrooms.models import Membership
from chatrooms.schemas import ChatRoomIn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from users.models import User as User


async def create_chatrooms(
    db_session: AsyncSession, creator: User, chatrooms: ChatRoomIn
):
    # Create a new chat room
    db_chatrooms = ChatRoomDBModel(name=chatrooms.name)
    db_session.add(db_chatrooms)
    await db_session.flush()  # Flush to get db_chatrooms.id populated

    # Now create Membership instances with the newly obtained chatrooms_id
    creator_membership = Membership(
        chatrooms_id=db_chatrooms.id, user_id=creator.id, role=2
    )
    db_session.add(creator_membership)

    if creator.id in chatrooms.members_ids:
        chatrooms.members_ids.remove(creator.id)

    for member_id in chatrooms.members_ids:
        member = await user_service.get_user(db_session, id=member_id)
        if member:
            member_membership = Membership(
                chatrooms_id=db_chatrooms.id, user_id=member.id, role=0
            )
            db_session.add(member_membership)

    await db_session.flush()
    stmt = (
        select(ChatRoomDBModel)
        .where(ChatRoomDBModel.id == db_chatrooms.id)
        .options(selectinload(ChatRoomDBModel.members))
    )
    result = await db_session.execute(stmt)
    db_chatrooms = result.scalars().first()

    return db_chatrooms
