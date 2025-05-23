from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import BooleanField, Case, Min, When
from pgvector.django import HnswIndex, VectorField
from shared.openai_utils import NUMBER_OF_EMBEDDING_DIMENSIONS

DELETED_USERNAME = "deleted"
DELETED_PHONE_NUMBER = "1121111111"
DELETED_EMAIL = "deleted@pico.fyi"
PICO_USERNAME = "pico"
PICO_PHONE_NUMBER = "1122211111"
PICO_EMAIL = "pico@pico.fyi"
SYSTEM_USERNAME = "system"
SYSTEM_PHONE_NUMBER = "1122111111"
SYSTEM_EMAIL = "system@pico.fyi"

SENTINEL_USERNAMES = [DELETED_USERNAME, PICO_USERNAME, SYSTEM_USERNAME]


def get_deleted_user():
    return User.objects.get_deleted_user()


class UserQuerySet(models.QuerySet):
    def with_referral_count(self):
        return self.annotate(referral_count=models.Count("referrals"))


class UserManager(BaseUserManager):
    def get_queryset(self):
        return UserQuerySet(self.model, using=self._db)

    async def acreate_user(
        self, username, phone_number, email, password=None, **extra_fields
    ):
        user = self.model(username=username, phone_number=phone_number, email=email)
        user.set_password(password)
        user.is_staff = extra_fields.get("is_staff", False)
        user.is_superuser = extra_fields.get("is_superuser", False)
        user.school_id = extra_fields.get("school_id", None)
        user.chosen_college = extra_fields.get("chosen_college", None)
        user.chosen_course = extra_fields.get("chosen_course", None)
        user.referred_by = extra_fields.get("referred_by", None)
        user.commitment = extra_fields.get("commitment", 20)
        user.education_level = extra_fields.get(
            "education_level", EducationLevel.UNKNOWN
        )
        user.signup_source = extra_fields.get("signup_source", SignupSource.UNKNOWN)
        await user.asave(using=self._db)
        return user

    def create_user(self, username, phone_number, email, password=None, **extra_fields):
        user = self.model(username=username, phone_number=phone_number, email=email)
        user.set_password(password)
        user.is_staff = extra_fields.get("is_staff", False)
        user.is_superuser = extra_fields.get("is_superuser", False)
        user.school_id = extra_fields.get("school_id", None)
        user.chosen_college = extra_fields.get("chosen_college", None)
        user.chosen_course = extra_fields.get("chosen_course", None)
        user.referred_by = extra_fields.get("referred_by", None)
        user.commitment = extra_fields.get("commitment", 20)
        user.education_level = extra_fields.get(
            "education_level", EducationLevel.UNKNOWN
        )
        user.signup_source = extra_fields.get("signup_source", SignupSource.UNKNOWN)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, username, phone_number, email, password=None, **extra_fields
    ):
        """
        Create and return a superuser with an email, password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(username, phone_number, email, password, **extra_fields)

    def get_sentinel_users(self) -> list["User"]:
        return list(
            User.objects.filter(username__in=SENTINEL_USERNAMES).order_by("username")
        )

    async def aget_sentinel_users(self) -> list["User"]:
        return [
            user
            async for user in self.filter(username__in=SENTINEL_USERNAMES).order_by(
                "username"
            )
        ]

    def get_deleted_user(self):
        return self.get(username=DELETED_USERNAME)

    async def aget_deleted_user(self):
        return await self.aget(username=DELETED_USERNAME)

    def get_pico_user(self):
        return self.get(username=PICO_USERNAME)

    async def aget_pico_user(self):
        return await self.aget(username=PICO_USERNAME)

    def get_system_user(self):
        return self.get(username=SYSTEM_USERNAME)

    async def aget_system_user(self):
        return await self.aget(username=SYSTEM_USERNAME)


class NonSentinelUserManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().exclude(username__in=SENTINEL_USERNAMES)


class Course(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=120)
    user_submitted = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                name="unique_course_name",
            )
        ]


class College(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=120)
    courses = models.ManyToManyField(Course)
    user_submitted = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                name="unique_college_name",
            )
        ]


class School(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=120)
    user_submitted = models.BooleanField(default=False)
    inep_code = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["inep_code"],
                condition=~models.Q(inep_code=""),
                name="unique_inep_code",
            )
        ]

    def __str__(self):
        return self.name


class EducationLevel(models.TextChoices):
    MIDDLE_SCHOOL = "MS", "Middle School"
    FIRST_YEAR_HIGH_SCHOOL = "FYHS", "First Year High School"
    SECOND_YEAR_HIGH_SCHOOL = "SYHS", "Second Year High School"
    THIRD_YEAR_HIGH_SCHOOL = "TYHS", "Third Year High School"
    HIGH_SCHOOL_COMPLETE = "HSG", "High School Complete"
    COLLEGE = "COL", "College"
    UNKNOWN = "", "Unknown"


class SignupSource(models.TextChoices):
    REFERRAL = "referral", "Amigo ou colega"
    SOCIAL = "social", "Redes sociais"
    INTERNET = "internet", "Pesquisa na internet"
    TEACHER = "teacher", "Indicação de professor"
    EVENT = "event", "Evento educacional"
    OTHER = "other", "Outro"
    UNKNOWN = "", "Desconhecido"


class User(AbstractUser):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=50, unique=True)
    phone_number = models.CharField(max_length=25, unique=True)
    email = models.EmailField(max_length=255, unique=True)

    school = models.ForeignKey(
        School,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
    )
    education_level = models.CharField(
        max_length=4,
        choices=EducationLevel.choices,
        default="",
        blank=True,
    )
    chosen_college = models.ForeignKey(
        College, null=True, blank=True, on_delete=models.SET_NULL
    )
    chosen_course = models.ForeignKey(
        Course, null=True, blank=True, on_delete=models.SET_NULL
    )
    is_premium = models.BooleanField(default=False)
    referred_by = models.ForeignKey(
        "User",
        related_name="referrals",
        null=True,
        blank=True,
        on_delete=models.SET(get_deleted_user),
    )
    commitment = models.IntegerField(default=20)
    balance = models.PositiveIntegerField(default=1000)
    signup_source = models.CharField(
        max_length=255,
        blank=True,
        default=SignupSource.UNKNOWN,
        choices=SignupSource.choices,
    )

    # Bot fields
    is_bot = models.BooleanField(default=False)
    bot_difficulty = models.FloatField(null=True, blank=True, default=None)

    objects = UserManager()
    non_sentinel_objects = NonSentinelUserManager()

    REQUIRED_FIELDS = [
        "phone_number",
        "email",
    ]  # required fields should not contain USERNAME_FIELD or password, as per django docs
    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(is_bot=True, bot_difficulty__isnull=False)
                | models.Q(is_bot=False, bot_difficulty__isnull=True),
                name="bot_difficulty_validation",
            )
        ]


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
