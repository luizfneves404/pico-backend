import logging

from api.models import Chatroom, EmbeddedFile, Membership
from django.db.models import Min

logger = logging.getLogger(__name__)

MEMBERS_ERROR_MESSAGE = "Error getting members list."


def format_member_list(chatroom: Chatroom) -> str:
    """Formats the member list for a chatroom."""
    # Sort members by their membership timestamp
    sorted_memberships = [
        membership
        for membership in Membership.objects.filter(chatroom=chatroom)
        .select_related("user")
        .order_by("timestamp")
    ]
    # Format each member string
    return "\n".join(
        [
            f"{index + 1}. {membership.user.username}{(' - creator' if membership.role == 2 else ' - admin' if membership.role == 1 else '')}"
            for index, membership in enumerate(sorted_memberships)
        ]
    )


def format_files_list(chatroom: Chatroom) -> str:
    """Formats the file list for a chatroom."""
    # sort files by their earliest message timestamp
    sorted_embedded_files = [
        embedded_file
        for embedded_file in EmbeddedFile.objects.filter(messages__chatroom=chatroom)
        .annotate(earliest_message_timestamp=Min("messages__timestamp"))
        .order_by("earliest_message_timestamp")
    ]
    return "\n".join(
        [
            f"{index + 1}. {embedded_file.file.name.split('/')[-1]}"
            for index, embedded_file in enumerate(sorted_embedded_files)
        ]
    )
