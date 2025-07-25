# This code is originally from https://github.com/kuzxnia/async_factory_boy
# MIT License
# Copyright (c) 2022 Kacper Kuźniarski

import functools
import logging
import os
import tempfile
import uuid
from typing import Any, TypeVar

from factory.alchemy import SQLAlchemyOptions
from factory.base import Factory
from factory.declarations import (
    Iterator,
    LazyFunction,
    RelatedFactoryList,
    SelfAttribute,
    Sequence,
    SubFactory,
)
from factory.faker import Faker as FactoryFaker
from faker import Faker
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session

import app.database as database
from app.base import Base
from app.community.models import Community
from app.countries.models import Country
from app.education.models import (
    AdministrativeCategory,
    Course,
    EducationInfo,
    EducationLevel,
    Institution,
    InstitutionType,
    LevelStage,
)
from app.fcm.models import DeviceType, FCMDevice
from app.files.models import File
from app.files.storage import storage
from app.flows.db_types import ContentBlockDB, ImageBlockDB, RichText, TextBlock
from app.flows.models import (
    Choice,
    Exam,
    Flow,
    FlowDifficulty,
    FlowElement,
    FlowInputType,
    FlowQuestion,
    FlowSourceType,
    OfficialQuestionSource,
    Question,
    QuestionAnswerType,
    QuestionArea,
    QuestionDifficulty,
    QuestionSourceType,
)
from app.notifications.models import (
    ExternalInAppNotification,
    FlowInAppNotification,
)
from app.users.models import User
from app.users.service import get_password_hash

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Base)

# Module-level cache for file data to ensure consistency across fields
_file_cache: dict[str, dict[str, Any]] = {}


def name_sequence(n: int) -> str:
    return f"User {n}"


def username_sequence(n: int) -> str:
    return f"user{n}"


def email_sequence(n: int) -> str:
    return f"user{n}@example.com"


def phone_number_sequence(n: int) -> str:
    return f"tel:+55-11-99999-9{n:03d}"


@functools.lru_cache(maxsize=None)
def hashed_password_func() -> str:
    return get_password_hash("defaultpassword")


def institution_name_sequence(n: int) -> str:
    return f"Institution {n}"


def course_name_i18n_sequence(n: int) -> dict[str, str]:
    return {"en": f"Course {n}", "pt": f"Curso {n}"}


def community_name_sequence(n: int) -> str:
    return f"Community {n}"


def community_subtitle_sequence(n: int) -> str:
    return f"Join Community {n} and connect with peers!"


def file_id_sequence(n: int) -> str:
    return f"file{n}"


def flow_title_sequence(n: int) -> str:
    return f"Flow {n}"


def education_level_name_i18n_sequence(n: int) -> dict[str, str]:
    return {"en": f"Education Level {n}", "pt": f"Nível de Ensino {n}"}


def level_stage_name_sequence(n: int) -> str:
    return f"Level Stage {n}"


def country_code_sequence(n: int) -> str:
    n = n % (26 * 26)  # Wrap around after 676
    first = n // 26
    second = n % 26
    return chr(ord("A") + first) + chr(ord("A") + second)


def country_name_sequence(n: int) -> str:
    return f"Country {n}"


def country_phone_code_sequence(n: int) -> str:
    n = n % (1000)  # Wrap around after 1000
    return f"{n:03d}"


def create_file_data() -> dict[str, Any]:
    """Create a real file in storage and return the file metadata."""
    # Generate unique content and filename
    unique_id = uuid.uuid4().hex[:8]
    content = f"Test file content {unique_id}\nThis is a test file created by FileFactory.\nLine 3 with more content."
    original_name = f"test_file_{unique_id}.txt"

    # Create temporary file with the content
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write(content)
        temp_path = f.name

    try:
        # Upload to storage backend
        file_id = storage.upload(temp_path, original_name)
        size = len(content.encode("utf-8"))
        return {"file_id": file_id, "original_name": original_name, "size": size}
    finally:
        # Clean up temporary file
        os.unlink(temp_path)


def get_file_id() -> str:
    """Create file data and return the file_id."""
    file_data = create_file_data()
    cache_key = file_data["file_id"]
    _file_cache[cache_key] = file_data
    return file_data["file_id"]


def get_original_name_for_file_id() -> str:
    """Return the original_name for the most recently created file."""
    if not _file_cache:
        return create_file_data()["original_name"]
    # Get the most recent file data
    latest_key = max(_file_cache.keys())
    return _file_cache[latest_key]["original_name"]


def get_size_for_file_id() -> int:
    """Return the size for the most recently created file."""
    if not _file_cache:
        return create_file_data()["size"]
    # Get the most recent file data
    latest_key = max(_file_cache.keys())
    return _file_cache[latest_key]["size"]


class AsyncSQLAlchemyFactory(Factory[T]):
    """Factory for creating SQLAlchemy model instances asynchronously.
    To get type hints do not use await Factory(), use await Factory.create().
    DO NOT OVERRIDE FOREIGN KEYS BY PASSING _id fields, pass the object instead."""

    _options_class = SQLAlchemyOptions

    class Meta:
        abstract = True

    @classmethod
    def get_db_session(cls) -> async_scoped_session[AsyncSession]:
        if not database.sc_session:
            raise RuntimeError("Database session is not set")
        return database.sc_session

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> T:
        instance = super().create(**kwargs)
        session.add(instance)
        await session.flush()
        return instance

    @classmethod
    async def create_batch(
        cls, size: int, session: AsyncSession, **kwargs: Any
    ) -> list[T]:
        instances = [super().create(**kwargs) for _ in range(size)]
        session.add_all(instances)
        await session.flush()
        return instances


class CountryFactory(AsyncSQLAlchemyFactory[Country]):
    class Meta:
        model = Country

    code = Sequence(country_code_sequence)
    name = Sequence(country_name_sequence)
    phone_code = Sequence(country_phone_code_sequence)


class EducationLevelFactory(AsyncSQLAlchemyFactory[EducationLevel]):
    class Meta:
        model = EducationLevel

    name_i18n = Sequence(education_level_name_i18n_sequence)
    stages = RelatedFactoryList(
        "tests.factories.LevelStageFactory",
        size=3,
        factory_related_name="level",
        country=SelfAttribute("..related_country"),
    )
    courses = RelatedFactoryList(
        "tests.factories.CourseFactory",
        size=3,
        factory_related_name="level",
    )

    class Params:
        related_country = SubFactory(CountryFactory)


class LevelStageFactory(AsyncSQLAlchemyFactory[LevelStage]):
    class Meta:
        model = LevelStage

    name = Sequence(level_stage_name_sequence)
    country = SubFactory(CountryFactory)
    level = SubFactory(
        EducationLevelFactory, related_country=SelfAttribute("..country")
    )


class CourseFactory(AsyncSQLAlchemyFactory[Course]):
    class Meta:
        model = Course

    name_i18n = Sequence(course_name_i18n_sequence)
    level = SubFactory(
        EducationLevelFactory, related_country=SelfAttribute("..related_country")
    )
    user_submitted = False

    class Params:
        related_country = SubFactory(CountryFactory)


class InstitutionFactory(AsyncSQLAlchemyFactory[Institution]):
    class Meta:
        model = Institution

    name = Sequence(institution_name_sequence)
    institution_type = InstitutionType.SCHOOL
    user_submitted = False
    country = SubFactory(CountryFactory)
    level = SubFactory(
        EducationLevelFactory, related_country=SelfAttribute("..country")
    )
    administrative_category = AdministrativeCategory.UNKNOWN


class CommunityFactory(AsyncSQLAlchemyFactory[Community]):
    """Factory for creating Community instances."""

    class Meta:
        model = Community

    name = Sequence(community_name_sequence)
    subtitle = Sequence(community_subtitle_sequence)


class EducationFactory(AsyncSQLAlchemyFactory[EducationInfo]):
    """Factory for creating Education instances."""

    class Meta:
        model = EducationInfo

    level = SubFactory(
        EducationLevelFactory, related_country=SelfAttribute("..related_country")
    )
    institution = SubFactory(
        InstitutionFactory,
        country=SelfAttribute("..related_country"),
    )
    course = SubFactory(CourseFactory)

    class Params:
        related_country = SubFactory(CountryFactory)


class UserFactory(AsyncSQLAlchemyFactory[User]):
    """Factory for creating User instances."""

    class Meta:
        model = User

    name = Sequence(name_sequence)
    username = Sequence(username_sequence)
    hashed_password = LazyFunction(hashed_password_func)
    google_id = ""
    apple_id = ""
    email = Sequence(email_sequence)
    phone_number = Sequence(phone_number_sequence)
    is_superuser = False
    is_bot = False
    bot_difficulty = None
    signup_source = "social"
    current_education = SubFactory(
        EducationFactory, related_country=SelfAttribute("..country")
    )
    intended_education = SubFactory(
        EducationFactory, related_country=SelfAttribute("..country")
    )
    country = SubFactory(CountryFactory)


class FileFactory(AsyncSQLAlchemyFactory[File]):
    """Factory for creating File instances that point to real files in storage."""

    class Meta:
        model = File

    file_id = LazyFunction(get_file_id)
    original_name = LazyFunction(get_original_name_for_file_id)
    size = LazyFunction(get_size_for_file_id)


def get_content_blocks(file: File) -> list[ContentBlockDB]:
    return [
        TextBlock(
            block_type="text",
            style="paragraph",
            content=[
                RichText(
                    text=Faker().paragraph(),
                    bold=Faker().boolean(),
                    italic=Faker().boolean(),
                    underline=Faker().boolean(),
                    strikethrough=Faker().boolean(),
                ),
            ],
        ),
        ImageBlockDB(
            block_type="image",
            image_id=file.id,
            alt=Faker().sentence(),
        ),
    ]


class ExamFactory(AsyncSQLAlchemyFactory[Exam]):
    """Factory for creating Exam instances."""

    name = "ENEM"
    country = SubFactory(CountryFactory)
    education_level = SubFactory(EducationLevelFactory)
    course = SubFactory(CourseFactory)

    class Meta:
        model = Exam


class QuestionAreaFactory(AsyncSQLAlchemyFactory[QuestionArea]):
    """Factory for creating QuestionArea instances."""

    class Meta:
        model = QuestionArea

    name = Sequence(lambda n: f"Area {n}")
    country = SubFactory(CountryFactory)
    education_level = SubFactory(EducationLevelFactory)
    course = SubFactory(CourseFactory)
    tags = FactoryFaker("words", nb=3)


class OfficialQuestionSourceFactory(AsyncSQLAlchemyFactory[OfficialQuestionSource]):
    """Factory for creating OfficialQuestionSource instances."""

    class Meta:
        model = OfficialQuestionSource

    exam = SubFactory(ExamFactory)
    year = FactoryFaker("random_int", min=2020, max=2025)


class QuestionFactory(AsyncSQLAlchemyFactory[Question]):
    """Factory for creating Question instances."""

    class Meta:
        model = Question

    is_active = True
    is_quantitative = False
    difficulty = Iterator(QuestionDifficulty)
    major_tags = FactoryFaker("words", nb=3)
    minor_tags = FactoryFaker("words", nb=3)
    parameter_a = 1.0
    parameter_b = 2.0
    parameter_c = 3.0
    embedding = FactoryFaker("random_elements", elements=[0.0, 1.0], length=1024)
    source_type = QuestionSourceType.OFFICIAL
    official_source = SubFactory(OfficialQuestionSourceFactory)
    source_user_id = None
    answer_type = QuestionAnswerType.MULTIPLE_CHOICE

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> Question:
        file = await FileFactory.create(session=session)
        content_blocks = get_content_blocks(file)
        answer_content_blocks = get_content_blocks(file)

        kwargs.setdefault("content_blocks", content_blocks)
        kwargs.setdefault("answer_content_blocks", answer_content_blocks)

        return await super().create(session=session, **kwargs)


class ChoiceFactory(AsyncSQLAlchemyFactory[Choice]):
    """Factory for creating Choice instances."""

    class Meta:
        model = Choice

    text = FactoryFaker("sentence")
    is_correct = Iterator([True, False, True, False, False, True])
    order = Sequence(lambda n: n)
    question = SubFactory(QuestionFactory)

    @classmethod
    async def create_batch_multiple_choice(
        cls, size: int, **kwargs: Any
    ) -> list[Choice]:
        questions = await super().create_batch(size, **kwargs)
        for question in questions:
            # Create 4 incorrect choices
            await ChoiceFactory.create_batch(4, question=question, is_correct=False)
            # Create 1 correct choice
            await ChoiceFactory.create(question=question, is_correct=True)
        return questions


class FlowFactory(AsyncSQLAlchemyFactory[Flow]):
    """Factory for creating Flow instances."""

    class Meta:
        model = Flow

    title = Sequence(flow_title_sequence)
    cover_image = SubFactory(FileFactory)
    difficulty = FlowDifficulty.ALL
    flow_input_type = FlowInputType.TOPIC
    input_topic = FactoryFaker("paragraph")
    created_by = SubFactory(UserFactory)
    action_link = FactoryFaker("url")
    action_text = FactoryFaker("sentence")
    question_answer_type = QuestionAnswerType.MULTIPLE_CHOICE
    source_type = FlowSourceType.OFFICIAL
    max_num_questions = 10
    major_tags = FactoryFaker("words", nb=3)
    minor_tags = FactoryFaker("words", nb=3)


class FlowElementFactory(AsyncSQLAlchemyFactory[FlowElement]):
    """Factory for creating FlowElement instances."""

    class Meta:
        model = FlowElement

    flow = SubFactory(FlowFactory)
    order = Sequence(lambda n: n)
    element_type = "flow_element"
    is_active = True
    is_correct = False
    text = FactoryFaker("paragraph")
    subject = "Matemática"
    source = "ENEM"


class FlowQuestionFactory(AsyncSQLAlchemyFactory[FlowQuestion]):
    class Meta:
        model = FlowQuestion

    flow = SubFactory(FlowFactory)

    # Order should be sequential **within** a flow, starting at 0 for every new flow.
    # Using a global Sequence causes order values to grow across tests, which can
    # make newly-created questions exceed the cutoff (< 5) used by
    # `get_flow_loader`, resulting in empty `flow.elements` collections.  We
    # therefore assign the order dynamically based on the current maximum order
    # of the given flow.

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> FlowQuestion:
        """Create a FlowQuestion ensuring `order` is sequential inside each flow.

        If the caller didn't specify an explicit ``order``, we compute the next
        available order for the provided ``flow`` (or a newly-created flow) by
        querying the maximum existing order and adding one.  This guarantees
        that orders start at 0 for every flow and remain contiguous, no matter
        how many FlowQuestions have been created in other tests.
        """
        flow: Flow | None = kwargs.get("flow")

        if flow is not None and "order" not in kwargs:
            # Fetch the current maximum order for this flow (-1 if none exist)
            max_order_query = select(
                func.coalesce(func.max(FlowElement.order), -1)
            ).where(FlowElement.flow_id == flow.id)
            result = await session.execute(max_order_query)
            max_order: int = result.scalar_one()
            kwargs["order"] = max_order + 1

        # 🧙 If no question was provided, create one explicitly via await
        if "question" not in kwargs:
            kwargs["question"] = await QuestionFactory.create(session=session)

        return await super().create(session=session, **kwargs)

    @classmethod
    async def create_batch(
        cls, size: int, session: AsyncSession, **kwargs: Any
    ) -> list[FlowQuestion]:
        """Create a batch of ``FlowQuestion`` instances ensuring correct ordering.

        This implementation ensures each call goes through :meth:`create`,
        preserving the per-flow sequential ordering logic.
        """
        return [await cls.create(session=session, **kwargs) for _ in range(size)]


class ExternalInAppNotificationFactory(
    AsyncSQLAlchemyFactory[ExternalInAppNotification]
):
    """Factory for creating ExternalInAppNotification instances."""

    class Meta:
        model = ExternalInAppNotification

    seen = False
    user = None
    text = FactoryFaker("sentence")
    external_url = FactoryFaker("url")


class FlowInAppNotificationFactory(AsyncSQLAlchemyFactory[FlowInAppNotification]):
    """Factory for creating FlowInAppNotification instances."""

    class Meta:
        model = FlowInAppNotification

    seen = False
    user = None
    text = FactoryFaker("sentence")
    flow = SubFactory(FlowFactory)


class FCMDeviceFactory(AsyncSQLAlchemyFactory[FCMDevice]):
    """Factory for creating FCMDevice instances."""

    class Meta:
        model = FCMDevice

    user = SubFactory(UserFactory)
    registration_id = FactoryFaker("uuid4")
    device_type = DeviceType.ANDROID
