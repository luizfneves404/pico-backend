from datetime import timedelta

from api.tests.factories import UserFactory
from currency.models import Currency, CurrencyAction, CurrencyType
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pico_backend.auth import generate_tokens
from quiz import tasks
from quiz.tests.factories import QuestionFactory
from shared.testing import PatchingAndRedisTestCase

User = get_user_model()


class TasksTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.users = UserFactory.create_batch(4)
        cls.access_tokens = [generate_tokens(user)[0] for user in cls.users]
        cls.auth_headers = [
            {"Authorization": f"Bearer {token}"} for token in cls.access_tokens
        ]
        cls.multiple_choice_questions = QuestionFactory.create_batch_multiple_choice(50)

        url = reverse("api:challenge_list")
        client = Client(headers=cls.auth_headers[0])
        response = client.post(
            url,
            content_type="application/json",
            data={
                "user_ids": [cls.users[1].id, cls.users[2].id],
                "selection_method": "random_official",
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
                "is_fast": True,
            },
        )
        cls.test_challenge_id = response.json()["id"]
        cls.test_challenge_questions = response.json()["questions_and_answers"]
        cls.test_challenge_code = response.json()["code"]
        cls.test_challenge_is_fast = response.json()["is_fast"]

    def setUp(self):
        super().setUp()
        self.clients = [Client(headers=headers) for headers in self.auth_headers]

    def test_task_reset_dynamic_scores(self):
        Currency.objects.create(
            action=CurrencyAction.DYNAMIC_RANKING_REWARD,
            currency_type=CurrencyType.REWARD,
            value=100,
            is_default=True,
        )
        Currency.objects.create(
            action=CurrencyAction.SCHOOL_DYNAMIC_RANKING_REWARD,
            currency_type=CurrencyType.REWARD,
            value=100,
            is_default=True,
        )

        # answer some questions correctly
        for i in range(10):
            # mark question as seen
            url = reverse("api:challenge_question_seen", args=[self.test_challenge_id])
            response = self.clients[0].patch(
                url,
                content_type="application/json",
                data={"question_id": self.test_challenge_questions[i]["id"]},
            )
            self.assertEqual(response.status_code, 204)

            # submit answer
            url = reverse("api:challenge_submit_answer", args=[self.test_challenge_id])
            response = self.clients[0].patch(
                url,
                content_type="application/json",
                data={
                    "question_id": self.test_challenge_questions[i]["id"],
                    "answer_choice_id": next(
                        choice["id"]
                        for choice in self.test_challenge_questions[i]["choices"]
                        if choice["is_correct"]
                    ),
                },
            )
            self.assertEqual(response.status_code, 204)

        # check dynamic score
        self.users[0].quiz_info.refresh_from_db()
        self.assertEqual(
            self.users[0].quiz_info.dynamic_score,
            10,
        )

        # reward dynamic ranking just to see if works
        tasks.task_reward_dynamic_ranking.delay()

        # reset dynamic scores
        tasks.task_reset_dynamic_scores.delay()
        self.users[0].quiz_info.refresh_from_db()
        self.assertEqual(self.users[0].quiz_info.dynamic_score, 0)
