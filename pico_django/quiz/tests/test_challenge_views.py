from datetime import timedelta

from api.tests.factories import UserFactory
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pico_backend.auth import generate_tokens
from quiz.models import (
    SessionParticipation,
)
from quiz.tests.factories import QuestionFactory
from shared.testing import PatchingAndRedisTestCase

User = get_user_model()


class ChallengeViewsTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.users = UserFactory.create_batch(4)
        cls.access_tokens = [generate_tokens(user)[0] for user in cls.users]
        cls.auth_headers = [
            {"Authorization": f"Bearer {token}"} for token in cls.access_tokens
        ]
        cls.multiple_choice_questions = QuestionFactory.create_batch_multiple_choice(85)

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
        cls.test_challenge_first_question = response.json()["questions_and_answers"][0]
        cls.test_challenge_code = response.json()["code"]
        cls.test_challenge_is_fast = response.json()["is_fast"]

    def setUp(self):
        super().setUp()
        self.clients = [Client(headers=headers) for headers in self.auth_headers]

    def test_challenge_detail(self):
        url = reverse("api:challenge_detail", args=[self.test_challenge_id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.test_challenge_id)
        self.assertEqual(len(data["participations"]), 3)
        self.assertEqual(len(data["questions_and_answers"]), 20)
        self.assertIsInstance(data["start_time"], str)
        self.assertIsInstance(data["end_time"], str)
        self.assertEqual(data["is_fast"], self.test_challenge_is_fast)
        # check total answers and correct answers

        self.assertEqual(data["participations"][0]["total_answers"], 0)
        self.assertEqual(data["participations"][0]["correct_answers"], 0)

    def test_challenge_question_detail_no_answer(self):
        url = reverse(
            "api:challenge_question_detail",
            args=[self.test_challenge_id, self.test_challenge_first_question["id"]],
        )
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["answers"]), 0)
        self.assertEqual(data["text"], self.test_challenge_first_question["text"])
        self.assertEqual(data["id"], self.test_challenge_first_question["id"])
        self.assertEqual(data["choices"], self.test_challenge_first_question["choices"])

    def test_challenge_question_detail_with_answer(self):
        # first mark question as seen
        url = reverse("api:challenge_question_seen", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_challenge_first_question["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # then answer the question
        url = reverse("api:challenge_submit_answer", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_challenge_first_question["id"],
                "answer_choice_id": self.test_challenge_first_question["choices"][0][
                    "id"
                ],
            },
        )
        self.assertEqual(response.status_code, 204)

        # now check the question detail
        url = reverse(
            "api:challenge_question_detail",
            args=[self.test_challenge_id, self.test_challenge_first_question["id"]],
        )
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.test_challenge_first_question["id"])
        self.assertEqual(data["text"], self.test_challenge_first_question["text"])
        self.assertIn("answers", data)
        self.assertIn("choices", data)
        self.assertEqual(len(data["answers"]), 1)

    def test_create_challenge_random_official_questions(self):
        url = reverse("api:challenge_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_ids": [self.users[1].id, self.users[2].id],
                "selection_method": "random_official",
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
                "is_fast": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("code", data)
        self.assertEqual(data["title"], "aleatório")
        self.assertEqual(len(data["participations"]), 3)
        # Check that creator is confirmed and others are not
        creator_participant = next(
            p for p in data["participations"] if p["user"]["id"] == self.users[0].id
        )
        other_participants = [
            p for p in data["participations"] if p["user"]["id"] != self.users[0].id
        ]
        self.assertTrue(creator_participant["confirmed"])
        self.assertFalse(any(p["confirmed"] for p in other_participants))
        self.assertEqual(len(data["questions_and_answers"]), 20)
        self.assertIsInstance(data["start_time"], str)
        self.assertIsInstance(data["end_time"], str)
        self.assertEqual(data["is_fast"], True)

    def test_create_challenge_query_official_questions(self):
        url = reverse("api:challenge_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_ids": [self.users[1].id, self.users[2].id],
                "selection_method": "query_official",
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
                "query": "What is the capital of France?",
                "difficulty": "Fácil",
                "source_filter": "",
                "is_fast": False,
            },
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("code", data)
        self.assertEqual(data["title"], "What is the capital of France?")
        self.assertEqual(len(data["participations"]), 3)
        self.assertEqual(len(data["questions_and_answers"]), 20)
        self.assertIsInstance(data["start_time"], str)
        self.assertIsInstance(data["end_time"], str)
        self.assertEqual(data["is_fast"], False)
        self.assertEqual(data["difficulty"], "Fácil")
        self.assertEqual(data["source_filter"], "")

    def test_create_challenge_custom_questions(self):
        url = reverse("api:challenge_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_ids": [self.users[1].id, self.users[2].id],
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
                "selection_method": "user_generated",
                "question_blocks": [
                    "What is the capital of France?",
                    "What is the capital of Germany?",
                    "What is the capital of Italy?",
                    "What is the capital of Spain?",
                    "What is the capital of Portugal?",
                ],
                "is_fast": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("code", data)
        self.assertIn("Mocked response for mock_gpt-4o-mini_0_", data["title"])
        self.assertEqual(len(data["participations"]), 3)
        self.assertEqual(len(data["questions_and_answers"]), 5)
        self.assertIsInstance(data["start_time"], str)
        self.assertIsInstance(data["end_time"], str)

    def test_confirm_challenge(self):
        # User2 confirms the challenge
        url = reverse("api:challenge_confirm", args=[self.test_challenge_id])
        response = self.clients[1].patch(url, content_type="application/json")
        self.assertEqual(response.status_code, 204)

        # Check that the SessionParticipant was updated
        self.assertTrue(
            SessionParticipation.objects.filter(
                session_id=self.test_challenge_id,
                user_id=self.users[1].id,
                confirmed=True,
            ).exists()
        )

    def test_reject_challenge(self):
        # User2 rejects the challenge
        url = reverse("api:challenge_reject", args=[self.test_challenge_id])
        response = self.clients[1].patch(url, content_type="application/json")
        self.assertEqual(response.status_code, 204)

        # Check that the SessionParticipant was deleted
        self.assertFalse(
            SessionParticipation.objects.filter(
                session_id=self.test_challenge_id, user_id=self.users[1].id
            ).exists()
        )

    def test_invite_to_challenge(self):
        # create a new challenge
        url = reverse("api:challenge_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_ids": [],
                "selection_method": "random_official",
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
                "is_fast": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        challenge_id = response.json()["id"]

        # invite user2 to the challenge
        url = reverse("api:challenge_invite", args=[challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={"user_ids": [self.users[1].id, self.users[2].id]},
        )
        self.assertEqual(response.status_code, 204)

        # do a challenge list from that user's perspective
        url = reverse("api:challenge_list")
        response = self.clients[1].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # assert that one of the challenges there is the challenge we created right now
        self.assertTrue(
            any(d["id"] == challenge_id for d in data),
            f"Challenge {challenge_id} not found in challenge list",
        )
        # grab that challenge and check that the user we invited is in it
        challenge = next(d for d in data if d["id"] == challenge_id)
        self.assertTrue(
            any(
                p["user"]["id"] == self.users[1].id for p in challenge["participations"]
            ),
            f"User {self.users[1].id} not found in challenge {challenge_id} participations",
        )
        # grab the participation of the user we invited and check that it is not confirmed
        participation = next(
            p
            for p in challenge["participations"]
            if p["user"]["id"] == self.users[1].id
        )
        self.assertFalse(participation["confirmed"])

        self.assertEqual(len(challenge["participations"]), 3)

    def test_join_challenge_by_code(self):
        # create a challenge
        url = reverse("api:challenge_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_ids": [],
                "selection_method": "query_official",
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
            },
        )
        self.assertEqual(response.status_code, 201)
        challenge_id = response.json()["id"]
        challenge_code = response.json()["code"]

        # join the challenge by code
        url = reverse("api:challenge_join_by_code")
        response = self.clients[1].patch(
            url,
            content_type="application/json",
            data={"challenge_code": challenge_code},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], challenge_id)
        self.assertEqual(len(data["participations"]), 2)
        self.assertTrue(
            any(p["user"]["id"] == self.users[1].id for p in data["participations"]),
            f"User {self.users[1].id} not found in challenge {challenge_id} participations",
        )

        # check that the duel detail has the user we joined
        url = reverse("api:challenge_detail", args=[challenge_id])
        response = self.clients[1].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["participations"]), 2)
        self.assertTrue(
            any(p["user"]["id"] == self.users[1].id for p in data["participations"]),
            f"User {self.users[1].id} not found in challenge {challenge_id} participations",
        )

    def test_join_challenge_by_code_not_found(self):
        # try to join a challenge that doesn't exist
        url = reverse("api:challenge_join_by_code")
        response = self.clients[1].patch(
            url,
            content_type="application/json",
            data={"challenge_code": "non_existent_code"},
        )
        self.assertEqual(response.status_code, 404)

    def test_join_challenge_by_code_already_in_challenge(self):
        url = reverse("api:challenge_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_ids": [self.users[1].id],
                "selection_method": "query_official",
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
            },
        )
        self.assertEqual(response.status_code, 201)
        challenge_id = response.json()["id"]
        challenge_code = response.json()["code"]

        # try to join the challenge by code when already a participant
        url = reverse("api:challenge_join_by_code")
        response = self.clients[1].patch(
            url,
            content_type="application/json",
            data={"challenge_code": challenge_code},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "User already in challenge")

        # verify participation count hasn't changed
        participation_count = SessionParticipation.objects.filter(
            session_id=challenge_id
        ).count()
        self.assertEqual(participation_count, 2)  # creator + invited user

    def test_question_seen_never_seen(self):
        url = reverse("api:challenge_question_seen", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_challenge_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # call duel get to see if the duel answer instance does not exist
        url = reverse("api:challenge_detail", args=[self.test_challenge_id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions_and_answers"][0]["answers"]), 0)

    def test_question_seen_already_seen(self):
        url = reverse("api:challenge_question_seen", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_challenge_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # mark as seen again
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_challenge_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # check that the duel answer instance does not exist
        url = reverse("api:challenge_detail", args=[self.test_challenge_id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions_and_answers"][0]["answers"]), 0)

    def test_question_timed_out_already_seen(self):
        # mark as seen
        url = reverse("api:challenge_question_seen", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_challenge_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # mark as timed out
        url = reverse("api:challenge_question_timed_out", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_challenge_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # call duel get to see if the duel answer instance exists
        url = reverse("api:challenge_detail", args=[self.test_challenge_id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions_and_answers"][0]["answers"]), 1)
        self.assertEqual(
            data["questions_and_answers"][0]["answers"][0]["timed_out"], True
        )

    def test_submit_answer_already_seen(self):  # this is the normal flow
        # mark as seen
        url = reverse("api:challenge_question_seen", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_challenge_first_question["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # submit answer
        url = reverse("api:challenge_submit_answer", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_challenge_first_question["id"],
                "answer_choice_id": self.test_challenge_first_question["choices"][0][
                    "id"
                ],
            },
        )
        self.assertEqual(response.status_code, 204)

        # check that the answers are present in the challenge detail
        url = reverse("api:challenge_detail", args=[self.test_challenge_id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions_and_answers"][0]["answers"]), 1)
        self.assertEqual(
            data["questions_and_answers"][0]["answers"][0]["choice_id"],
            self.test_challenge_first_question["choices"][0]["id"],
        )
        self.assertEqual(
            data["questions_and_answers"][0]["answers"][0]["timed_out"], False
        )

    def test_submit_answer_correct(self):
        # First mark question as seen
        url = reverse("api:challenge_question_seen", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_challenge_first_question["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # Then submit the answer
        url = reverse("api:challenge_submit_answer", args=[self.test_challenge_id])
        response = self.clients[0].patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_challenge_first_question["id"],
                "answer_choice_id": next(
                    choice["id"]
                    for choice in self.test_challenge_first_question["choices"]
                    if choice["is_correct"]
                ),
            },
        )
        self.assertEqual(response.status_code, 204)

        # check that the user's dynamic score increased
        self.users[0].quiz_info.refresh_from_db()
        self.assertEqual(self.users[0].quiz_info.dynamic_score, 1)

    def test_challenge_list(self):
        # Create a few duels
        url = reverse("api:challenge_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_ids": [self.users[1].id],
                "selection_method": "query_official",
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
                "query": "What is the capital of France?",
            },
        )
        self.assertEqual(response.status_code, 201)
        response = self.clients[1].post(
            url,
            content_type="application/json",
            data={
                "user_ids": [self.users[0].id],
                "selection_method": "random_official",
                "start_time": timezone.now(),
                "end_time": timezone.now() + timedelta(days=1),
                "is_fast": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        # Get duel list
        url = reverse("api:challenge_list")
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)  # Including test_challenge

        response = self.clients[1].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)  # Including test_challenge

        response = self.clients[2].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)  # Including test_challenge
