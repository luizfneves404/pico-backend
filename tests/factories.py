# This code is originally from https://github.com/kuzxnia/async_factory_boy
# MIT License
# Copyright (c) 2022 Kacper Kuźniarski

import functools
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
from app.education.models import College, Course, Education, School
from app.files.models import File
from app.flows.models import (
    ENEM_AREAS,
    Choice,
    Flow,
    FlowElement,
    FlowInputType,
    FlowQuestion,
    Question,
    QuestionAnswerType,
)
from app.users.models import EducationLevel, User, UserProfile
from app.users.service import get_password_hash

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


def file_key_sequence(n: int) -> str:
    return f"file{n}"


def flow_title_sequence(n: int) -> str:
    return f"Flow {n}"


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
    async def create(cls, session: AsyncSession | None = None, **kwargs: Any) -> T:
        instance = super().create(**kwargs)
        session.add(instance)
        await session.flush()
        return instance

    @classmethod
    async def create_batch(
        cls, size: int, session: AsyncSession | None = None, **kwargs: Any
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


class EducationFactory(AsyncSQLAlchemyFactory[Education]):
    """Factory for creating Education instances."""

    class Meta:
        model = Education

    level = EducationLevel.THIRD_YEAR_HIGH_SCHOOL
    institution = SubFactory(SchoolFactory)
    course = SubFactory(CourseFactory)


class UserProfileFactory(AsyncSQLAlchemyFactory[UserProfile]):
    class Meta:
        model = UserProfile

    social_score = 0
    xp_score = 0


class UserFactory(AsyncSQLAlchemyFactory[User]):
    """Factory for creating User instances."""

    class Meta:
        model = User
        sqlalchemy_get_or_create = ("username",)

    username = Sequence(username_sequence)
    hashed_password = LazyFunction(hashed_password_func)
    email = Sequence(email_sequence)
    phone_number = Sequence(phone_number_sequence)
    is_superuser = False
    is_premium = False
    balance = 1000
    is_bot = False
    bot_difficulty = None
    signup_source = "social"
    current_education = SubFactory(EducationFactory)
    intended_education = SubFactory(EducationFactory)
    profile = SubFactory(UserProfileFactory)


class FileFactory(AsyncSQLAlchemyFactory[File]):
    """Factory for creating File instances."""

    class Meta:
        model = File
        sqlalchemy_get_or_create = ("key",)

    key = Sequence(file_key_sequence)
    updated_at = Faker("date_time_this_year")


class QuestionFactory(AsyncSQLAlchemyFactory[Question]):
    """Factory for creating Question instances."""

    class Meta:
        model = Question
        sqlalchemy_get_or_create = ("text",)

    text = Faker("sentence")
    subject = "Matemática"
    difficulty = "Fácil"
    source = "ENEM"
    is_active = True
    allow_resubmit = False
    answer_text = "This is the correct answer"
    embedding = Faker("random_elements", elements=[0.0, 1.0], length=1024)
    source = Faker("sentence")
    difficulty = Faker("sentence")
    image = SubFactory(FileFactory)
    answer_image = SubFactory(FileFactory)
    video_url = Faker("sentence")
    is_fast = Faker("sentence")


class ChoiceFactory(AsyncSQLAlchemyFactory[Choice]):
    """Factory for creating Choice instances."""

    class Meta:
        model = Choice
        sqlalchemy_get_or_create = ("text",)

    text = Faker("sentence")
    is_correct = Iterator([True, False, True, False, False, True])
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
    difficulty = ""
    flow_input_type = FlowInputType.TOPIC
    input_topic = Faker("paragraph")
    created_by = SubFactory(UserFactory)
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
    element_type = "question"
    is_active = True
    is_correct = False
    text = Faker("paragraph")
    subject = "Matemática"
    source = "ENEM"
    question = SubFactory(QuestionFactory)
