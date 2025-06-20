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
    Sequence,
    SubFactory,
)
from factory.faker import Faker as FactoryFaker
from faker import Faker
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
from app.files.models import File
from app.files.storage import storage
from app.flows.db_types import ContentBlock, ImageBlock, RichText, TextBlock
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
    QuestionDifficulty,
    QuestionSourceType,
)
from app.in_app_notifications.models import (
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
    To get type hints do not use await Factory(), use await Factory.create()"""

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


class EducationLevelFactory(AsyncSQLAlchemyFactory[EducationLevel]):
    class Meta:
        model = EducationLevel

    name_i18n = Sequence(education_level_name_i18n_sequence)
    stages = RelatedFactoryList(
        "tests.factories.LevelStageFactory", size=3, factory_related_name="level"
    )
    courses = RelatedFactoryList(
        "tests.factories.CourseFactory", size=3, factory_related_name="level"
    )


class CountryFactory(AsyncSQLAlchemyFactory[Country]):
    class Meta:
        model = Country

    code = Sequence(country_code_sequence)
    name = Sequence(country_name_sequence)
    phone_code = Sequence(country_phone_code_sequence)


class LevelStageFactory(AsyncSQLAlchemyFactory[LevelStage]):
    class Meta:
        model = LevelStage

    name = Sequence(level_stage_name_sequence)
    country = SubFactory(CountryFactory)
    level = SubFactory(EducationLevelFactory)


class CourseFactory(AsyncSQLAlchemyFactory[Course]):
    class Meta:
        model = Course

    name_i18n = Sequence(course_name_i18n_sequence)
    level = SubFactory(EducationLevelFactory)
    user_submitted = False


class InstitutionFactory(AsyncSQLAlchemyFactory[Institution]):
    class Meta:
        model = Institution

    name = Sequence(institution_name_sequence)
    institution_type = InstitutionType.SCHOOL
    user_submitted = False
    country = SubFactory(CountryFactory)
    level = SubFactory(EducationLevelFactory)
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

    level = SubFactory(EducationLevelFactory)
    institution = SubFactory(InstitutionFactory)
    course = SubFactory(CourseFactory)


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
    current_education = SubFactory(EducationFactory)
    intended_education = SubFactory(EducationFactory)
    country = SubFactory(CountryFactory)


class FileFactory(AsyncSQLAlchemyFactory[File]):
    """Factory for creating File instances that point to real files in storage."""

    class Meta:
        model = File

    file_id = LazyFunction(get_file_id)
    original_name = LazyFunction(get_original_name_for_file_id)
    size = LazyFunction(get_size_for_file_id)


def get_content_blocks() -> list[ContentBlock]:
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
        ImageBlock(
            block_type="image",
            file_url=Faker().url(),
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


class OfficialQuestionSourceFactory(AsyncSQLAlchemyFactory[OfficialQuestionSource]):
    """Factory for creating OfficialQuestionSource instances."""

    class Meta:
        model = OfficialQuestionSource

    exam = SubFactory(ExamFactory)
    year = 2024


class QuestionFactory(AsyncSQLAlchemyFactory[Question]):
    """Factory for creating Question instances."""

    class Meta:
        model = Question

    content_blocks = LazyFunction(get_content_blocks)
    answer_content_blocks = LazyFunction(get_content_blocks)

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
    """Factory for creating FlowQuestion instances."""

    class Meta:
        model = FlowQuestion

    flow = SubFactory(FlowFactory)
    order = Sequence(lambda n: n)
    question = SubFactory(QuestionFactory)


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
