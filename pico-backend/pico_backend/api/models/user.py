from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

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
                check=models.Q(is_bot=True, bot_difficulty__isnull=False)
                | models.Q(is_bot=False, bot_difficulty__isnull=True),
                name="bot_difficulty_validation",
            )
        ]
