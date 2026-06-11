from django.db import models
from django.db.models import BooleanField, Case, Min, When
from pgvector.django import HnswIndex, VectorField
from shared.openai_utils import NUMBER_OF_EMBEDDING_DIMENSIONS

from .user import User, get_deleted_user


class MembershipRole(models.TextChoices):
    MEMBER = "MEM", "Member"
    ADMIN = "ADM", "Admin"
    CREATOR = "CRE", "Creator"


class ChatroomQuerySet(models.QuerySet):
    async def with_members_is_admin(self) -> list["Chatroom"]:
        chatrooms = self.prefetch_related("members")

        memberships = (
            Membership.objects.filter(chatroom__in=chatrooms)
            .annotate(
                is_admin=Case(
                    When(
                        role__in=[MembershipRole.ADMIN, MembershipRole.CREATOR],
                        then=True,
                    ),
                    default=False,
                    output_field=BooleanField(),
                )
            )
            .values_list("user_id", "chatroom_id", "is_admin")
        )

        membership_info = {(m[0], m[1]): m[2] async for m in memberships}

        async for chatroom in chatrooms:
            async for member in chatroom.members.all():
                is_admin = membership_info.get((member.id, chatroom.id), False)
                setattr(member, "is_admin", is_admin)

        chatrooms = [chatroom async for chatroom in chatrooms]

        return chatrooms


class ChatroomType(models.TextChoices):
    DM = "DM", "Direct Message"
    GROUP = "GP", "Group"
    OFFICIAL = "OF", "Official"


# IMPORTANT: first member added is creator, others are members (unless admin=True)
class Chatroom(models.Model):
    id = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(
        User, related_name="chatroom_set", through="Membership"
    )
    name = models.CharField(max_length=120, blank=True, default="")
    icon = models.ImageField(upload_to="chatroom_icons", blank=True)
    chat_type = models.CharField(
        max_length=2, choices=ChatroomType.choices, default=ChatroomType.GROUP
    )
    objects = ChatroomQuerySet.as_manager()

    def is_member(self, user: User) -> bool:
        return self.members.filter(id=user.id).exists()

    async def ais_member(self, user: User) -> bool:
        return await self.members.filter(id=user.id).aexists()

    async def annotate_members_is_admin(self) -> "Chatroom":
        memberships = (
            Membership.objects.filter(chatroom=self)
            .annotate(
                is_admin=Case(
                    When(
                        role__in=[MembershipRole.ADMIN, MembershipRole.CREATOR],
                        then=True,
                    ),
                    default=False,
                    output_field=BooleanField(),
                )
            )
            .values_list("user_id", "chatroom_id", "is_admin")
        )

        membership_info = {(m[0], m[1]): m[2] async for m in memberships}

        async for member in self.members.all():
            is_admin = membership_info.get((member.id, self.id), False)
            setattr(member, "is_admin", is_admin)

        return self


class GroupChatroomManager(models.Manager):
    def get_queryset(self):
        return ChatroomQuerySet(self.model, using=self._db).filter(
            chat_type=ChatroomType.GROUP
        )


class GroupChatroom(Chatroom):
    objects = GroupChatroomManager()

    class Meta:
        proxy = True

    def add_member(self, user, admin=False):
        if not self.members.exists():
            role = MembershipRole.CREATOR
        elif admin:
            role = MembershipRole.ADMIN
        else:
            role = MembershipRole.MEMBER
        Membership.objects.create(user=user, chatroom=self, role=role)

    async def aadd_member(self, user, admin=False):
        if not await self.members.aexists():
            role = MembershipRole.CREATOR
        elif admin:
            role = MembershipRole.ADMIN
        else:
            role = MembershipRole.MEMBER
        await Membership.objects.acreate(user=user, chatroom=self, role=role)

    def add_members(self, users: list[User]):
        # if its the first member added, make them creator
        if not self.members.exists():
            Membership.objects.create(
                user=users[0], chatroom=self, role=MembershipRole.CREATOR
            )
            users.pop(0)
        Membership.objects.bulk_create(
            [Membership(user=user, chatroom=self) for user in users]
        )

    async def aadd_members(self, users: list[User]):
        # if its the first member added, make them creator
        if not await self.members.aexists():
            await Membership.objects.acreate(
                user=users[0], chatroom=self, role=MembershipRole.CREATOR
            )
            users.pop(0)
        await Membership.objects.abulk_create(
            [Membership(user=user, chatroom=self) for user in users]
        )

    def remove_member(self, user: User):
        is_creator = self.is_creator(user)
        Membership.objects.filter(user=user, chatroom=self).delete()
        if is_creator:
            self.set_new_creator()

    async def aremove_member(self, user: User):
        is_creator = await self.ais_creator(user)
        await Membership.objects.filter(user=user, chatroom=self).adelete()
        if is_creator:
            await self.aset_new_creator()

    @property
    def allowed_admins(self):
        return self.members.filter(
            membership__role__in=[MembershipRole.ADMIN, MembershipRole.CREATOR]
        )

    def has_admin_perms(self, user: User) -> bool:
        membership = Membership.objects.filter(user=user, chatroom=self).first()
        if membership:
            return membership.role in [
                MembershipRole.ADMIN,
                MembershipRole.CREATOR,
            ]
        return False

    async def ahas_admin_perms(self, user: User) -> bool:
        membership = await Membership.objects.filter(user=user, chatroom=self).afirst()
        if membership:
            return membership.role in [
                MembershipRole.ADMIN,
                MembershipRole.CREATOR,
            ]
        return False

    def set_admin(self, user: User, admin: bool):
        membership = Membership.objects.filter(user=user, chatroom=self).first()
        if membership and membership.role != MembershipRole.CREATOR:
            membership.role = MembershipRole.ADMIN if admin else MembershipRole.MEMBER
            membership.save()

    async def aset_admin(self, user: User, admin: bool):
        membership = await Membership.objects.filter(user=user, chatroom=self).afirst()
        if membership and membership.role != MembershipRole.CREATOR:
            membership.role = MembershipRole.ADMIN if admin else MembershipRole.MEMBER
            await membership.asave()

    def is_creator(self, user: User) -> bool:
        membership = Membership.objects.filter(user=user, chatroom=self).first()
        if membership is None:
            return False
        return membership.role == MembershipRole.CREATOR

    async def ais_creator(self, user: User) -> bool:
        membership = await Membership.objects.filter(user=user, chatroom=self).afirst()
        if membership is None:
            return False
        return membership.role == MembershipRole.CREATOR

    def get_creator(self) -> User:
        membership = (
            Membership.objects.filter(chatroom=self, role=MembershipRole.CREATOR)
            .select_related("user")
            .get()
        )
        return membership.user

    async def aget_creator(self) -> User:
        membership = (
            await Membership.objects.filter(chatroom=self, role=MembershipRole.CREATOR)
            .select_related("user")
            .aget()
        )
        return membership.user

    def set_new_creator(self):
        # Find the timestamp of the oldest admin
        oldest_admin_time = Membership.objects.filter(
            chatroom=self, role=MembershipRole.ADMIN
        ).aggregate(Min("timestamp"))["timestamp__min"]
        if oldest_admin_time:
            oldest_admin = Membership.objects.get(
                chatroom=self, timestamp=oldest_admin_time
            )
            oldest_admin.role = MembershipRole.CREATOR
            oldest_admin.save()
            return

        # Find the timestamp of the oldest member
        oldest_member_time = Membership.objects.filter(
            chatroom=self, role=MembershipRole.MEMBER
        ).aggregate(Min("timestamp"))["timestamp__min"]
        if oldest_member_time:
            oldest_member = Membership.objects.get(
                chatroom=self, timestamp=oldest_member_time
            )
            oldest_member.role = MembershipRole.CREATOR
            oldest_member.save()

    async def aset_new_creator(self):
        # Find the timestamp of the oldest admin
        oldest_admin_time = (
            await Membership.objects.filter(
                chatroom=self, role=MembershipRole.ADMIN
            ).aaggregate(Min("timestamp"))
        )["timestamp__min"]
        if oldest_admin_time:
            oldest_admin = await Membership.objects.aget(
                chatroom=self, timestamp=oldest_admin_time
            )
            oldest_admin.role = MembershipRole.CREATOR
            await oldest_admin.asave()
            return

        # Find the timestamp of the oldest member
        oldest_member_time = (
            await Membership.objects.filter(
                chatroom=self, role=MembershipRole.MEMBER
            ).aaggregate(Min("timestamp"))
        )["timestamp__min"]
        if oldest_member_time:
            oldest_member = await Membership.objects.aget(
                chatroom=self, timestamp=oldest_member_time
            )
            oldest_member.role = MembershipRole.CREATOR
            await oldest_member.asave()

    def __str__(self):
        return f"{self.name}, id={self.id}"


class DMChatroomManager(models.Manager):
    def get_queryset(self):
        return ChatroomQuerySet(self.model, using=self._db).filter(
            chat_type=ChatroomType.DM
        )

    def get_or_create_dm(self, user1: User, user2: User):
        existing_dms = self.get_queryset().filter(members=user1).filter(members=user2)
        if existing_dms.exists():
            return existing_dms.first()
        else:
            new_dm = self.model(chat_type=ChatroomType.DM)
            new_dm.save()
            new_dm.members.add(user1, user2)
            return new_dm

    async def aget_or_create_dm(self, user1: User, user2: User):
        existing_dms = self.get_queryset().filter(members=user1).filter(members=user2)
        if await existing_dms.aexists():
            return await existing_dms.afirst()
        else:
            new_dm = self.model(chat_type=ChatroomType.DM)
            await new_dm.asave()
            await new_dm.members.aadd(user1, user2)
            return new_dm

    async def aget_or_create_dms(
        self, user: User, users: list[User]
    ) -> list[tuple[Chatroom, bool]]:
        user_ids = [u.id for u in users] + [user.id]
        user_pairs = [tuple(sorted((user.id, u.id))) for u in users]

        existing_chatrooms = (
            Chatroom.objects.filter(members=user)
            .filter(chat_type=ChatroomType.DM, members__in=user_ids)
            .prefetch_related("members")
        )

        existing_dms_map = {}
        async for chatroom in existing_chatrooms:
            members_ids = tuple(
                [member.id async for member in chatroom.members.order_by("id")]
            )
            existing_dms_map[members_ids] = chatroom

        new_dms = []
        valid_chatrooms = []
        pairs_to_be_added = []
        memberships_to_create = []

        for sorted_pair in user_pairs:
            if sorted_pair in existing_dms_map:
                valid_chatrooms.append(existing_dms_map[sorted_pair])
            else:
                pairs_to_be_added.append(sorted_pair)
                new_dm = self.model(chat_type=ChatroomType.DM)
                new_dms.append(new_dm)
                valid_chatrooms.append(new_dm)

        if new_dms:
            await self.abulk_create(new_dms)
            for dm, pair in zip(new_dms, pairs_to_be_added):
                memberships_to_create.append(Membership(user_id=pair[0], chatroom=dm))
                memberships_to_create.append(Membership(user_id=pair[1], chatroom=dm))

        await Membership.objects.abulk_create(memberships_to_create)

        return [(chatroom, chatroom in new_dms) for chatroom in valid_chatrooms]


class DMChatroom(Chatroom):
    objects = DMChatroomManager()

    class Meta:
        proxy = True

    def __str__(self):
        return f"DM Chatroom: {', '.join(user.username for user in self.members.order_by('id'))}"


class OfficialManager(models.Manager):
    def get_queryset(self):
        return ChatroomQuerySet(self.model, using=self._db).filter(
            chat_type=ChatroomType.OFFICIAL
        )

    def get_official(self, user: User):
        return self.get_queryset().filter(members=user).get()

    async def aget_official(self, user: User):
        return await self.get_queryset().filter(members=user).aget()

    def create_official(self, name: str, user: User, extra_users: list[User]):
        existing_officials = self.get_queryset().filter(members=user)
        if existing_officials.exists():
            raise OfficialChatroom.OfficialChatroomAlreadyExists
        else:
            new_official = self.model(name=name, chat_type=ChatroomType.OFFICIAL)
            new_official.save()
            new_official.members.add(user, *extra_users)
            return new_official

    async def acreate_official(self, name: str, user: User, extra_users: list[User]):
        existing_officials = self.get_queryset().filter(members=user)
        if await existing_officials.aexists():
            raise OfficialChatroom.OfficialChatroomAlreadyExists
        else:
            new_official = self.model(name=name, chat_type=ChatroomType.OFFICIAL)
            await new_official.asave()
            await new_official.members.aadd(user, *extra_users)
            return new_official


class OfficialChatroom(Chatroom):
    class OfficialChatroomAlreadyExists(Exception):
        pass

    objects = OfficialManager()

    class Meta:
        proxy = True

    def __str__(self):
        return f"Official Chatroom: {', '.join(user.username for user in self.members.order_by('id'))}"


class Membership(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
    )
    chatroom = models.ForeignKey(
        Chatroom,
        on_delete=models.CASCADE,
    )

    role = models.CharField(
        max_length=3, choices=MembershipRole.choices, default=MembershipRole.MEMBER
    )

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} in {self.chatroom} with role {self.role}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "chatroom"], name="unique_membership"
            )
        ]
        indexes = [
            models.Index(fields=["user", "chatroom"]),
        ]


def file_upload_directory_path(instance, filename) -> str:
    if hasattr(instance, "file_group") and instance.file_group is not None:
        return f"files/file_group_{instance.file_group.id}/{filename}"
    else:
        return f"files/no_file_group/{filename}"


class MessageQuerySet(models.QuerySet):
    def prefetch_for_notification(self):
        return self.select_related(
            "sender", "parent_message", "essay_topic", "session", "chatroom"
        ).prefetch_related(
            "thread_messages__thread_messages",
            "thread_messages__sender",
            "embedded_files",
            "chatroom__members",
        )


class Message(models.Model):
    id = models.AutoField(primary_key=True)
    sender = models.ForeignKey(  # type: ignore
        User,
        on_delete=models.SET(get_deleted_user),
    )
    content = models.TextField(max_length=3000, blank=True, default="")
    timestamp = models.DateTimeField(auto_now_add=True)

    chatroom = models.ForeignKey(
        Chatroom,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    parent_message = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="thread_messages",
        null=True,
        blank=True,
    )

    embedding = VectorField(
        dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS, null=True, blank=True
    )

    essay_topic = models.ForeignKey(
        "essays.EssayTopic",
        on_delete=models.SET_NULL,
        related_name="messages",
        null=True,
        blank=True,
    )
    session = models.ForeignKey(
        "quiz.Session",
        on_delete=models.SET_NULL,
        related_name="messages",
        null=True,
        blank=True,
    )

    objects = MessageQuerySet.as_manager()

    def __str__(self):
        return self.content

    class Meta:
        indexes = [
            models.Index(fields=["chatroom"]),
            HnswIndex(
                name="message_cosine_similarity_index",
                fields=["embedding"],
                m=16,
                ef_construction=200,
                opclasses=["vector_cosine_ops"],
            ),
        ]


class FileGroup(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=120)

    def __str__(self):
        return self.name


class EmbeddedFile(models.Model):
    id = models.AutoField(primary_key=True)
    file = models.FileField(upload_to=file_upload_directory_path)
    file_processing_done = models.BooleanField(default=False, null=True, blank=True)
    text = models.TextField(blank=True, default="")
    name = models.CharField(max_length=120, blank=True, default="")
    messages = models.ManyToManyField(
        Message,
        blank=True,
        related_name="embedded_files",
    )
    file_group = models.ForeignKey(
        FileGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="embedded_files",
    )

    def __str__(self):
        return self.name

    @property
    def chatroom(self) -> Chatroom | None:
        message = self.messages.first()
        if message:
            return message.chatroom
        return None


class EmbeddedTextChunk(models.Model):
    id = models.AutoField(primary_key=True)
    embedded_file = models.ForeignKey(
        EmbeddedFile,
        on_delete=models.CASCADE,
        related_name="embedded_text_chunks",
    )
    text = models.TextField()
    embedding = VectorField(
        dimensions=NUMBER_OF_EMBEDDING_DIMENSIONS, null=True, blank=True
    )

    class Meta:
        indexes = [
            HnswIndex(
                name="chunk_cosine_similarity_index",
                fields=["embedding"],
                m=16,
                ef_construction=200,
                opclasses=["vector_cosine_ops"],
            ),
        ]
