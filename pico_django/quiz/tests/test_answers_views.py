import quiz.session_service as session_service
from api.tests.factories import MembershipFactory, OfficialChatroomFactory, UserFactory
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from pico_backend.auth import generate_tokens
from quiz.models import QuestionType
from quiz.tests.factories import QuestionFactory, QuizFactory
from shared.testing import PatchingAndRedisTestCase

User = get_user_model()


class AnswersTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = UserFactory.create()
        cls.official_chatroom = OfficialChatroomFactory.create()
        MembershipFactory.create(user=cls.user, chatroom=cls.official_chatroom)
        cls.quiz1 = QuizFactory.create(
            question_type=QuestionType.MULTIPLE_CHOICE, created_by=cls.user
        )
        cls.quiz2 = QuizFactory.create(
            question_type=QuestionType.MULTIPLE_CHOICE, created_by=cls.user
        )
        questions = QuestionFactory.create_batch_multiple_choice(2)
        session_service.add_questions_to_session(cls.quiz1.id, [questions[0]])
        session_service.add_questions_to_session(cls.quiz2.id, [questions[1]])

        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers)

    def test_answers_list(self):
        # answer questions to be able to query them
        self.client.post(
            reverse("api:quiz_submit_multiple_choice", args=[self.quiz1.id]),
            content_type="application/json",
            data={
                "answers": [
                    {
                        "question_id": self.quiz1.questions.first().id,
                        "answer_choice_id": self.quiz1.questions.first()
                        .choices.first()
                        .id,
                    }
                ]
            },
        )
        self.client.post(
            reverse("api:quiz_submit_multiple_choice", args=[self.quiz2.id]),
            content_type="application/json",
            data={
                "answers": [
                    {
                        "question_id": self.quiz2.questions.first().id,
                        "answer_choice_id": self.quiz2.questions.first()
                        .choices.first()
                        .id,
                    }
                ]
            },
        )

        url = reverse("api:answers_list")
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["total_answers"], 2)
        self.assertEqual(len(response.json()[0]["answers"]), 2)
        self.assertEqual(
            response.json()[0]["answers"][0]["question_id"],
            self.quiz1.questions.first().id,
        )
        self.assertEqual(
            response.json()[0]["answers"][1]["question_id"],
            self.quiz2.questions.first().id,
        )
