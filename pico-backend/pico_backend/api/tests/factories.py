import factory
from django.contrib.auth import get_user_model
from quiz.models import UserInfo

from api.models import MembershipRole
from api.models.chat import ChatroomType
from api.services.constants import STARTING_DUEL_SCORE


class CourseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "api.Course"

    name = factory.Sequence(lambda n: f"Course {n}")


class CollegeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "api.College"

    name = factory.Sequence(lambda n: f"College {n}")
    courses = factory.RelatedFactoryList(CourseFactory, size=3)


class SchoolFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "api.School"

    name = factory.Sequence(lambda n: f"School {n}")


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    username = factory.Sequence(lambda n: f"testuser{n}")
    password = factory.PostGenerationMethodCall("set_password", "defaultpassword")
    phone_number = factory.Sequence(lambda n: f"tel:+55-21-99933-2{n:03d}")
    email = factory.Sequence(lambda n: f"testuser{n:03d}@example.com")
    school = factory.SubFactory(SchoolFactory)
    commitment = 17
    education_level = "TYHS"
    chosen_college = factory.SubFactory(CollegeFactory)
    chosen_course = factory.SubFactory(CourseFactory)
    signup_source = "social"

    @factory.post_generation
    def create_user_info(self, create, extracted, **kwargs):
        if not create:
            return

        UserInfo.objects.create(user=self, duel_score=STARTING_DUEL_SCORE)


class GroupChatroomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "api.GroupChatroom"

    name = factory.Sequence(lambda n: f"Test Chatroom {n}")


class OfficialChatroomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "api.OfficialChatroom"

    name = factory.Sequence(lambda n: f"Official Chatroom {n}")
    chat_type = ChatroomType.OFFICIAL


class MembershipFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    chatroom = factory.SubFactory(GroupChatroomFactory)
    role = MembershipRole.MEMBER

    class Meta:
        model = "api.Membership"


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "api.Message"

    content = factory.Sequence(lambda n: f"Test Message {n}")
    sender = factory.SubFactory(UserFactory)
    chatroom = factory.SubFactory(GroupChatroomFactory)
