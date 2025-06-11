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
from factory.faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session

import app.database as database
from app.base import Base
from app.community.models import Community
from app.education.models import College, Course, EducationInfo, EducationLevel, School
from app.files.models import File
from app.files.storage import storage
from app.flows.db_types import ContentBlock, ImageBlock, RichText, TextBlock
from app.flows.models import (
    ENEM_AREAS,
    Choice,
    Exam,
    Flow,
    FlowDifficulty,
    FlowElement,
    FlowInputType,
    FlowQuestion,
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

QUERIES = [
    "What is the capital of France?",
    "Quem sou eu?",
    "Como você é?",
    "O que você acha?",
    "minha história",
    "minha vida",
    "lesgoooooo",
    "what is love",
    "baby don't hurt me",
    "no more",
]

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


def school_name_sequence(n: int) -> str:
    return f"School {n}"


def course_name_sequence(n: int) -> str:
    return f"Course {n}"


def college_name_sequence(n: int) -> str:
    return f"College {n}"


def community_name_sequence(n: int) -> str:
    return f"Community {n}"


def community_subtitle_sequence(n: int) -> str:
    return f"Join Community {n} and connect with peers!"


def file_id_sequence(n: int) -> str:
    return f"file{n}"


def flow_title_sequence(n: int) -> str:
    return f"Flow {n}"


def education_level_name_sequence(n: int) -> str:
    return f"Education Level {n}"


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


class SchoolFactory(AsyncSQLAlchemyFactory[School]):
    class Meta:
        model = School
        sqlalchemy_get_or_create = ("name",)

    name = Sequence(school_name_sequence)
    institution_type = "school"
    user_submitted = False


class CourseFactory(AsyncSQLAlchemyFactory[Course]):
    class Meta:
        model = Course
        sqlalchemy_get_or_create = ("name",)

    name = Sequence(course_name_sequence)
    user_submitted = False


class CollegeFactory(AsyncSQLAlchemyFactory[College]):
    class Meta:
        model = College

    name = Sequence(college_name_sequence)
    institution_type = "college"
    user_submitted = False
    courses = RelatedFactoryList(CourseFactory, size=3)


class CommunityFactory(AsyncSQLAlchemyFactory[Community]):
    """Factory for creating Community instances."""

    class Meta:
        model = Community
        sqlalchemy_get_or_create = ("name",)

    name = Sequence(community_name_sequence)
    subtitle = Sequence(community_subtitle_sequence)


class EducationLevelFactory(AsyncSQLAlchemyFactory[EducationLevel]):
    class Meta:
        model = EducationLevel

    name = Sequence(education_level_name_sequence)


class EducationFactory(AsyncSQLAlchemyFactory[EducationInfo]):
    """Factory for creating Education instances."""

    class Meta:
        model = EducationInfo

    level = SubFactory(EducationLevelFactory)
    institution = SubFactory(SchoolFactory)
    course = SubFactory(CourseFactory)


class UserFactory(AsyncSQLAlchemyFactory[User]):
    """Factory for creating User instances."""

    class Meta:
        model = User
        sqlalchemy_get_or_create = ("username",)

    name = Sequence(name_sequence)
    username = Sequence(username_sequence)
    hashed_password = LazyFunction(hashed_password_func)
    email = Sequence(email_sequence)
    phone_number = Sequence(phone_number_sequence)
    is_superuser = False
    is_bot = False
    bot_difficulty = None
    signup_source = "social"
    current_education = SubFactory(EducationFactory)
    intended_education = SubFactory(EducationFactory)


class FileFactory(AsyncSQLAlchemyFactory[File]):
    """Factory for creating File instances that point to real files in storage."""

    class Meta:
        model = File
        sqlalchemy_get_or_create = ("file_id",)

    file_id = LazyFunction(get_file_id)
    original_name = LazyFunction(get_original_name_for_file_id)
    size = LazyFunction(get_size_for_file_id)
    updated_at = Faker("date_time_this_year")


def get_content_blocks() -> list[ContentBlock]:
    return [
        TextBlock(
            block_type="text",
            style="paragraph",
            content=[
                RichText(
                    text="This is sample question text for testing purposes.",
                    bold=False,
                    italic=False,
                    underline=False,
                    strikethrough=False,
                ),
            ],
        ),
        ImageBlock(
            block_type="image",
            file_id="file1",
            alt="This is a sample image for testing purposes.",
        ),
    ]


class ExamFactory(AsyncSQLAlchemyFactory[Exam]):
    """Factory for creating Exam instances."""

    name = "ENEM"
    country = "Brazil"

    class Meta:
        model = Exam
        sqlalchemy_get_or_create = ("name",)


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
        sqlalchemy_get_or_create = ("content_blocks",)

    content_blocks = LazyFunction(get_content_blocks)

    is_active = True
    subject = "Matemática"
    category = "Álgebra"
    subcategory = "Equações"
    caderno = "Azul"
    caderno_number = 1
    difficulty = QuestionDifficulty.EASY
    parameter_a = 1.0
    parameter_b = 2.0
    parameter_c = 3.0
    answer_text = "This is the correct answer"
    embedding = Faker("random_elements", elements=[0.0, 1.0], length=1024)
    source_type = QuestionSourceType.OFFICIAL
    official_source = SubFactory(OfficialQuestionSourceFactory)
    source_user_id = None
    answer_type = QuestionAnswerType.MULTIPLE_CHOICE
    answer_image = SubFactory(FileFactory)


class ChoiceFactory(AsyncSQLAlchemyFactory[Choice]):
    """Factory for creating Choice instances."""

    class Meta:
        model = Choice
        sqlalchemy_get_or_create = ("text",)

    text = Faker("sentence")
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
    query = Iterator(QUERIES)
    area = Iterator(ENEM_AREAS.keys())
    source_filter = ""
    difficulty = FlowDifficulty.ALL
    flow_input_type = FlowInputType.TOPIC
    input_topic = Faker("paragraph")
    created_by = None
    question_answer_type = QuestionAnswerType.MULTIPLE_CHOICE


class FlowElementFactory(AsyncSQLAlchemyFactory[FlowElement]):
    """Factory for creating FlowElement instances."""

    class Meta:
        model = FlowElement

    flow = SubFactory(FlowFactory)
    order = Sequence(lambda n: n)
    element_type = "flow_element"
    is_active = True
    is_correct = False
    text = Faker("paragraph")
    subject = "Matemática"
    source = "ENEM"


class FlowQuestionFactory(AsyncSQLAlchemyFactory[FlowQuestion]):
    """Factory for creating FlowQuestion instances."""

    class Meta:
        model = FlowQuestion

    flow = SubFactory(FlowFactory)
    order = Sequence(lambda n: n)
    element_type = "flow_question"
    question = SubFactory(QuestionFactory)


class ExternalInAppNotificationFactory(
    AsyncSQLAlchemyFactory[ExternalInAppNotification]
):
    """Factory for creating ExternalInAppNotification instances."""

    class Meta:
        model = ExternalInAppNotification

    seen = False
    user = None
    text = Faker("sentence")
    in_app_notification_type = "external_in_app_notification"
    external_url = Faker("url")


class FlowInAppNotificationFactory(AsyncSQLAlchemyFactory[FlowInAppNotification]):
    """Factory for creating FlowInAppNotification instances."""

    class Meta:
        model = FlowInAppNotification

    seen = False
    user = None
    text = Faker("sentence")
    in_app_notification_type = "flow_in_app_notification"
    flow = SubFactory(FlowFactory)
