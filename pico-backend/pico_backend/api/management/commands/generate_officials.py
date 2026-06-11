# myapp/management/commands/generate_officials.py

from api.models import Membership, OfficialChatroom
from api.models.chat import ChatroomType
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    def handle(self, *args, **options):
        created_users = User.objects.filter(username__startswith="AutomaticCreatedUser")
        official_chatrooms = []
        memberships = []
        for user in created_users:
            official_chatrooms.append(
                OfficialChatroom(name="Pico", chat_type=ChatroomType.OFFICIAL)
            )

        official_chatrooms = OfficialChatroom.objects.bulk_create(official_chatrooms)

        for user, chatroom in zip(created_users, official_chatrooms):
            memberships.append(Membership(user=user, chatroom=chatroom))

        Membership.objects.bulk_create(memberships)

        self.stdout.write(self.style.SUCCESS("Official chatrooms created successfully"))
