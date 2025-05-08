from api.models import User
from api.tests.factories import UserFactory
from django.test import Client
from django.urls import reverse
from pico_backend.auth import generate_tokens
from quiz.models import (
    SessionParticipation,
)
from quiz.tests.factories import QuestionFactory
from shared.testing import PatchingAndRedisTestCase


class DuelViewsTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user = UserFactory.create()
        cls.user2 = UserFactory.create()
        cls.user3 = UserFactory.create()
        cls.access_token1, _ = generate_tokens(cls.user)
        cls.access_token2, _ = generate_tokens(cls.user2)
        cls.access_token3, _ = generate_tokens(cls.user3)
        cls.auth_headers1 = {"Authorization": f"Bearer {cls.access_token1}"}
        cls.auth_headers2 = {"Authorization": f"Bearer {cls.access_token2}"}
        cls.auth_headers3 = {"Authorization": f"Bearer {cls.access_token3}"}
        cls.multiple_choice_questions = QuestionFactory.create_batch_multiple_choice(50)

        # Create a test duel that can be reused
        url = reverse("api:duel_list")
        client = Client(headers=cls.auth_headers1)
        client2 = Client(headers=cls.auth_headers2)
        response = client.post(
            url,
            content_type="application/json",
            data={
                "user_id": cls.user2.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )

        # user2 confirms participation
        duel_confirm_url = reverse("api:duel_confirm", args=[response.json()["id"]])
        client2.patch(duel_confirm_url, content_type="application/json")

        cls.test_duel_id = response.json()["id"]
        cls.test_duel_first_question = response.json()["questions_and_answers"][0]
        cls.test_duel_code = response.json()["code"]

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers1)
        self.client2 = Client(headers=self.auth_headers2)
        self.client3 = Client(headers=self.auth_headers3)

    """ def test_duel_detail(self):
        url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], self.test_duel_id)
        self.assertEqual(data["code"], self.test_duel_code)
        self.assertEqual(len(data["participations"]), 2)
        self.assertEqual(len(data["questions_and_answers"]), 15)
        self.assertEqual(data["n_rounds"], 3)
        self.assertEqual(data["n_questions_per_round"], 5)
        self.assertTrue(data["is_fast"]) """

    """ def test_create_duel_random_official_questions(self):
        url = reverse("api:duel_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "user_id": self.user2.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("code", data)
        self.assertEqual(len(data["participations"]), 2)
        # Check that creator is confirmed and opponent is not
        creator_participant = next(
            p for p in data["participations"] if p["user"]["id"] == self.user.id
        )
        opponent_participant = next(
            p for p in data["participations"] if p["user"]["id"] == self.user2.id
        )
        self.assertTrue(creator_participant["confirmed"])
        self.assertFalse(opponent_participant["confirmed"])
        self.assertEqual(len(data["questions_and_answers"]), 15)
        self.assertEqual(
            data["n_rounds"],
            3,
        )
        self.assertEqual(
            data["n_questions_per_round"],
            5,
        )
        self.assertTrue(data["is_fast"]) """

    """ def test_create_duel_query_official_questions(self):
        url = reverse("api:duel_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "user_id": self.user2.id,
                "selection_method": "query_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
                "is_fast": False,
            },
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("code", data)
        self.assertEqual(len(data["participations"]), 2)
        self.assertEqual(len(data["questions_and_answers"]), 0)
        self.assertEqual(
            data["n_rounds"],
            3,
        )
        self.assertEqual(
            data["n_questions_per_round"],
            5,
        )
        self.assertFalse(data["is_fast"]) """

    def test_create_duel_custom_questions(self):
        url = reverse("api:duel_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "user_id": self.user2.id,
                "selection_method": "user_generated",
                "n_rounds": 3,
                "n_questions_per_round": 5,
                "question_blocks": [
                    "What is the capital of France?",
                    "What is the capital of Germany?",
                    "What is the capital of Italy?",
                    "What is the capital of Spain?",
                    "What is the capital of Portugal?",
                ],
                "topic": "Capitais",
                "subject": "Geografia",
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertIn("code", data)
        self.assertEqual(len(data["participations"]), 2)
        self.assertEqual(len(data["questions_and_answers"]), 5)

    """ def test_add_questions_to_duel(self):
        # First create a duel
        url = reverse("api:duel_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "user_id": self.user2.id,
                "selection_method": "query_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        duel_id = response.json()["id"]

        # Now add questions to it
        url = reverse("api:duel_add_questions", args=[duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={
                "query": "What is the capital of France?",
            },
        )
        self.assertEqual(response.status_code, 204)

        url = reverse("api:duel_detail", args=[duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["rounds"]), 3)
        self.assertEqual(data["rounds"][0]["query"], "What is the capital of France?")
        self.assertEqual(data["rounds"][1]["query"], "")
        self.assertEqual(data["rounds"][2]["query"], "")

        # Check that the questions were added
        self.assertEqual(len(data["questions_and_answers"]), 5)

        # add more questions to the duel
        url = reverse("api:duel_add_questions", args=[duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"query": "What is the capital of Germany?"},
        )
        self.assertEqual(response.status_code, 204)

        url = reverse("api:duel_detail", args=[duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["rounds"]), 3)
        self.assertEqual(data["rounds"][0]["query"], "What is the capital of France?")
        self.assertEqual(data["rounds"][1]["query"], "What is the capital of Germany?")
        self.assertEqual(data["rounds"][2]["query"], "")
        self.assertEqual(len(data["questions_and_answers"]), 10)

        # add more questions to the duel
        url = reverse("api:duel_add_questions", args=[duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"query": "What is the capital of Italy?"},
        )
        self.assertEqual(response.status_code, 204)

        url = reverse("api:duel_detail", args=[duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["rounds"]), 3)
        self.assertEqual(data["rounds"][0]["query"], "What is the capital of France?")
        self.assertEqual(data["rounds"][1]["query"], "What is the capital of Germany?")
        self.assertEqual(data["rounds"][2]["query"], "What is the capital of Italy?")
        self.assertEqual(len(data["questions_and_answers"]), 15) """

    def test_confirm_duel(self):
        # User2 confirms the duel
        url = reverse("api:duel_confirm", args=[self.test_duel_id])
        response = self.client2.patch(url, content_type="application/json")
        self.assertEqual(response.status_code, 204)

        # Check that the SessionParticipant was updated
        self.assertTrue(
            SessionParticipation.objects.filter(
                session_id=self.test_duel_id, user_id=self.user2.id, confirmed=True
            ).exists()
        )

    def test_reject_duel(self):
        # User2 rejects the duel
        url = reverse("api:duel_reject", args=[self.test_duel_id])
        response = self.client2.patch(url, content_type="application/json")
        self.assertEqual(response.status_code, 204)

        # Check that the SessionParticipant was deleted
        self.assertFalse(
            SessionParticipation.objects.filter(
                session_id=self.test_duel_id, user_id=self.user2.id
            ).exists()
        )

    def test_invite_to_duel(self):
        # create a new duel
        url = reverse("api:duel_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "user_id": None,
                "n_rounds": 3,
                "n_questions_per_round": 5,
                "selection_method": "query_official",
            },
        )
        self.assertEqual(response.status_code, 201)
        duel_id = response.json()["id"]

        # invite user2 to the duel
        url = reverse("api:duel_invite", args=[duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"user_id": self.user2.id},
        )
        self.assertEqual(response.status_code, 204)

        # do a duel list from that user's perspective
        url = reverse("api:duel_list")
        response = self.client2.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # assert that one of the duels there is the duel we created right now
        self.assertTrue(
            any(d["id"] == duel_id for d in data),
            f"Duel {duel_id} not found in duel list",
        )
        # grab that duel and check that the user we invited is in it
        duel = next(d for d in data if d["id"] == duel_id)
        self.assertTrue(
            any(p["user"]["id"] == self.user2.id for p in duel["participations"]),
            f"User {self.user2.id} not found in duel {duel_id} participations",
        )
        # grab the participation of the user we invited and check that it is not confirmed
        participation = next(
            p for p in duel["participations"] if p["user"]["id"] == self.user2.id
        )
        self.assertFalse(participation["confirmed"])

    def test_invite_to_duel_full(self):
        url = reverse("api:duel_invite", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"user_id": self.user3.id},
        )
        self.assertEqual(response.status_code, 400)

        # check that the duel detail does not have the user we invited
        url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(
            any(p["user"]["id"] == self.user3.id for p in data["participations"]),
            f"User {self.user3.id} found in duel {self.test_duel_id} participations",
        )

    def test_join_duel_by_code(self):
        # create a duel
        url = reverse("api:duel_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "user_id": None,
                "n_rounds": 3,
                "n_questions_per_round": 5,
                "selection_method": "query_official",
            },
        )
        duel_id = response.json()["id"]
        duel_code = response.json()["code"]

        # join the duel by code
        url = reverse("api:duel_join_by_code")
        response = self.client2.patch(
            url,
            content_type="application/json",
            data={"code": duel_code},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], duel_id)
        self.assertEqual(len(data["participations"]), 2)
        self.assertTrue(
            any(p["user"]["id"] == self.user2.id for p in data["participations"]),
            f"User {self.user2.id} not found in duel {duel_id} participations",
        )

        # check that the duel detail has the user we joined
        url = reverse("api:duel_detail", args=[duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["participations"]), 2)
        self.assertTrue(
            any(p["user"]["id"] == self.user2.id for p in data["participations"]),
            f"User {self.user2.id} not found in duel {duel_id} participations",
        )

    def test_join_duel_by_code_already_in_duel(self):
        # create a duel
        url = reverse("api:duel_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "user_id": None,
                "n_rounds": 3,
                "n_questions_per_round": 5,
                "selection_method": "query_official",
            },
        )
        duel_id = response.json()["id"]
        duel_code = response.json()["code"]

        # try to join the duel by code with the same user that created it
        url = reverse("api:duel_join_by_code")
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"code": duel_code},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "User already in duel")

        # verify participation count hasn't changed
        participation_count = SessionParticipation.objects.filter(
            session_id=duel_id
        ).count()
        self.assertEqual(participation_count, 1)  # just the creator

    def test_join_duel_by_code_full(self):
        url = reverse("api:duel_join_by_code")
        response = self.client3.patch(
            url,
            content_type="application/json",
            data={"code": self.test_duel_code},
        )
        self.assertEqual(response.status_code, 400)

        # check that the duel detail does not have the user that tried to join
        url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(
            any(p["user"]["id"] == self.user3.id for p in data["participations"]),
            f"User {self.user3.id} found in duel {self.test_duel_id} participations",
        )

    def test_join_duel_by_code_not_found(self):
        url = reverse("api:duel_join_by_code")
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"code": "AAAAA"},
        )
        self.assertEqual(response.status_code, 404)

    def test_question_seen_never_seen(self):
        url = reverse("api:duel_question_seen", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_duel_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # call duel get to see if the duel answer instance does not exist
        url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions_and_answers"][0]["answers"]), 0)

    def test_question_seen_already_seen(self):
        url = reverse("api:duel_question_seen", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_duel_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # mark as seen again
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_duel_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # check that the duel answer instance does not exist
        url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions_and_answers"][0]["answers"]), 0)

    def test_question_timed_out_already_seen(self):
        # mark as seen
        url = reverse("api:duel_question_seen", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_duel_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # mark as timed out
        url = reverse("api:duel_question_timed_out", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={"question_id": self.test_duel_first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # call duel get to see if the duel answer instance exists
        url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions_and_answers"][0]["answers"]), 1)
        self.assertEqual(
            data["questions_and_answers"][0]["answers"][0]["timed_out"], True
        )

    def test_submit_answer_already_seen(self):  # this is the normal flow
        # mark as seen
        url = reverse("api:duel_question_seen", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_duel_first_question["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # submit answer
        url = reverse("api:duel_submit_answer", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_duel_first_question["id"],
                "answer_choice_id": self.test_duel_first_question["choices"][0]["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # check that the answers are present in the duel detail
        url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["questions_and_answers"][0]["answers"]), 1)
        self.assertEqual(
            data["questions_and_answers"][0]["answers"][0]["choice_id"],
            self.test_duel_first_question["choices"][0]["id"],
        )
        self.assertEqual(
            data["questions_and_answers"][0]["answers"][0]["timed_out"], False
        )

    def test_submit_answer_correct(self):
        # mark question as seen first
        url = reverse("api:duel_question_seen", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_duel_first_question["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # submit answer
        url = reverse("api:duel_submit_answer", args=[self.test_duel_id])
        response = self.client.patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_duel_first_question["id"],
                "answer_choice_id": next(
                    choice["id"]
                    for choice in self.test_duel_first_question["choices"]
                    if choice["is_correct"]
                ),
            },
        )
        self.assertEqual(response.status_code, 204)

        # check that the user's dynamic score increased
        self.user.quiz_info.refresh_from_db()
        self.assertEqual(self.user.quiz_info.dynamic_score, 1)

    def test_duel_list(self):
        # Create a few duels
        url = reverse("api:duel_list")
        self.client.post(
            url,
            content_type="application/json",
            data={
                "user_id": self.user2.id,
                "selection_method": "query_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        self.client2.post(
            url,
            content_type="application/json",
            data={
                "user_id": self.user.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )

        # Get duel list
        url = reverse("api:duel_list")
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)  # Including test_duel

        response = self.client2.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)  # Including test_duel

    def test_duel_attack_suggestions(self):
        url = reverse("api:duel_attack_suggestions")
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 0)

        # User2 answers a question
        # First mark question as seen
        seen_url = reverse("api:duel_question_seen", args=[self.test_duel_id])
        response = self.client2.patch(
            seen_url,
            content_type="application/json",
            data={
                "question_id": self.test_duel_first_question["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # Then submit answer
        url = reverse("api:duel_submit_answer", args=[self.test_duel_id])
        response = self.client2.patch(
            url,
            content_type="application/json",
            data={
                "question_id": self.test_duel_first_question["id"],
                "answer_choice_id": self.test_duel_first_question["choices"][0]["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # Get duel attack suggestions
        url = reverse("api:duel_attack_suggestions")
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id"], self.user2.id)

    def test_duel_turn_flow(self):
        # Submit answers for all questions in all rounds
        url = reverse("api:duel_submit_answer", args=[self.test_duel_id])
        seen_url = reverse("api:duel_question_seen", args=[self.test_duel_id])

        # Get initial duel state
        detail_url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(detail_url, content_type="application/json")
        data = response.json()
        n_questions = data["n_questions_per_round"]
        n_rounds = data["n_rounds"]

        for round in range(n_rounds):
            if round % 2 == 0:
                # Even rounds: User 1 attacks, User 2 defends
                attacking_client = self.client
                defending_client = self.client2
                defending_user_id = self.user2.id
            else:
                # Odd rounds: User 2 attacks, User 1 defends
                attacking_client = self.client2
                defending_client = self.client
                defending_user_id = self.user.id

            # Attacker's turn
            for i in range(n_questions):
                # First mark question as seen
                response = attacking_client.patch(
                    seen_url,
                    content_type="application/json",
                    data={
                        "question_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["id"],
                    },
                )
                self.assertEqual(response.status_code, 204)

                # Then submit answer
                response = attacking_client.patch(
                    url,
                    content_type="application/json",
                    data={
                        "question_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["id"],
                        "answer_choice_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["choices"][0]["id"],
                    },
                )
                self.assertEqual(response.status_code, 204)

            # Get duel detail to check phase and turn switched
            response = self.client.get(detail_url, content_type="application/json")
            data = response.json()

            # Phase should switch from attack to defense
            self.assertEqual(data["duel_phase"], "defense")

            # Turn should switch to defender
            self.assertEqual(data["current_turn_user_id"], defending_user_id)

            # Current turn start time should be updated
            self.assertIsNotNone(data["current_turn_start_time"])

            # Defender's turn
            for i in range(n_questions):
                # First mark question as seen
                response = defending_client.patch(
                    seen_url,
                    content_type="application/json",
                    data={
                        "question_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["id"],
                    },
                )
                self.assertEqual(response.status_code, 204)

                # Then submit answer
                response = defending_client.patch(
                    url,
                    content_type="application/json",
                    data={
                        "question_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["id"],
                        "answer_choice_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["choices"][0]["id"],
                    },
                )
                self.assertEqual(response.status_code, 204)

            # Get duel state after round
            response = self.client.get(detail_url, content_type="application/json")
            data = response.json()

            if round < n_rounds - 1:
                # Phase should switch back to attack for next round
                self.assertEqual(data["duel_phase"], "attack")

                # Turn should switch to next attacker
                next_attacker_id = self.user2.id if round % 2 == 0 else self.user.id
                self.assertEqual(data["current_turn_user_id"], next_attacker_id)

                # Current turn start time should be updated
                self.assertIsNotNone(data["current_turn_start_time"])

        response = self.client.get(detail_url, content_type="application/json")
        data = response.json()

        # Duel should be completed
        self.assertEqual(data["status"], "completed")

        # current turn user id should be None
        self.assertIsNone(data["current_turn_user_id"])

        # duel phase should be empty
        self.assertEqual(data["duel_phase"], "")

        # current turn start time should be None
        self.assertIsNone(data["current_turn_start_time"])

        # Winner should be None since it's a draw
        self.assertIsNone(data["winner_id"])

    def test_duel_turn_flow_with_timeouts(self):
        # Similar to test_duel_turn_flow but with timeouts
        url = reverse("api:duel_question_timed_out", args=[self.test_duel_id])
        seen_url = reverse("api:duel_question_seen", args=[self.test_duel_id])
        detail_url = reverse("api:duel_detail", args=[self.test_duel_id])

        # Get initial duel state
        response = self.client.get(detail_url, content_type="application/json")
        data = response.json()
        n_questions = data["n_questions_per_round"]
        n_rounds = data["n_rounds"]

        for round in range(n_rounds):
            if round % 2 == 0:
                # Even rounds: User 1 attacks, User 2 defends
                attacking_client = self.client
                defending_client = self.client2
                defending_user_id = self.user2.id
            else:
                # Odd rounds: User 2 attacks, User 1 defends
                attacking_client = self.client2
                defending_client = self.client
                defending_user_id = self.user.id

            # Attacker's turn - mix of timeouts and answers
            for i in range(n_questions):
                # First mark question as seen
                response = attacking_client.patch(
                    seen_url,
                    content_type="application/json",
                    data={
                        "question_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["id"],
                    },
                )
                self.assertEqual(response.status_code, 204)

                # Then mark as timed out
                response = attacking_client.patch(
                    url,
                    content_type="application/json",
                    data={
                        "question_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["id"],
                    },
                )
                self.assertEqual(response.status_code, 204)

            # Verify phase and turn switched after attacker's turn
            response = self.client.get(detail_url, content_type="application/json")
            data = response.json()
            self.assertEqual(data["duel_phase"], "defense")
            self.assertEqual(data["current_turn_user_id"], defending_user_id)
            self.assertIsNotNone(data["current_turn_start_time"])

            # Defender's turn - end with timeout to test turn switching
            for i in range(n_questions - 1):
                # First mark question as seen
                response = defending_client.patch(
                    seen_url,
                    content_type="application/json",
                    data={
                        "question_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["id"],
                    },
                )
                self.assertEqual(response.status_code, 204)

                # Then submit answer
                response = defending_client.patch(
                    reverse("api:duel_submit_answer", args=[self.test_duel_id]),
                    content_type="application/json",
                    data={
                        "question_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["id"],
                        "answer_choice_id": data["questions_and_answers"][
                            round * n_questions + i
                        ]["choices"][0]["id"],
                    },
                )
                self.assertEqual(response.status_code, 204)

            # Last question: mark as seen then times out
            response = defending_client.patch(
                seen_url,
                content_type="application/json",
                data={
                    "question_id": data["questions_and_answers"][
                        round * n_questions + n_questions - 1
                    ]["id"],
                },
            )
            self.assertEqual(response.status_code, 204)

            response = defending_client.patch(
                url,
                content_type="application/json",
                data={
                    "question_id": data["questions_and_answers"][
                        round * n_questions + n_questions - 1
                    ]["id"],
                },
            )
            self.assertEqual(response.status_code, 204)

            # Verify turn switches properly after timeout
            response = self.client.get(detail_url, content_type="application/json")
            data = response.json()

            if round < n_rounds - 1:
                self.assertEqual(data["duel_phase"], "attack")
                next_attacker_id = self.user2.id if round % 2 == 0 else self.user.id
                self.assertEqual(data["current_turn_user_id"], next_attacker_id)
                self.assertIsNotNone(data["current_turn_start_time"])

        # Verify final state
        response = self.client.get(detail_url, content_type="application/json")
        data = response.json()
        self.assertEqual(data["status"], "completed")
        self.assertIsNone(data["current_turn_user_id"])
        self.assertIsNone(data["winner_id"])

    def test_mixed_answer_submission_methods(self):
        # Test that different combinations of seen/timeout/answer work correctly
        detail_url = reverse("api:duel_detail", args=[self.test_duel_id])
        response = self.client.get(detail_url, content_type="application/json")
        data = response.json()
        first_question = data["questions_and_answers"][0]

        # Test sequence: seen -> timeout
        response = self.client.patch(
            reverse("api:duel_question_seen", args=[self.test_duel_id]),
            content_type="application/json",
            data={"question_id": first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        response = self.client.patch(
            reverse("api:duel_question_timed_out", args=[self.test_duel_id]),
            content_type="application/json",
            data={"question_id": first_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        # Verify the answer state
        response = self.client.get(detail_url, content_type="application/json")
        data = response.json()
        answer = data["questions_and_answers"][0]["answers"][0]
        self.assertTrue(answer["timed_out"])
        self.assertIsNone(answer["choice_id"])

        # Test sequence: seen -> answer (second question)
        second_question = data["questions_and_answers"][1]
        response = self.client.patch(
            reverse("api:duel_question_seen", args=[self.test_duel_id]),
            content_type="application/json",
            data={"question_id": second_question["id"]},
        )
        self.assertEqual(response.status_code, 204)

        response = self.client.patch(
            reverse("api:duel_submit_answer", args=[self.test_duel_id]),
            content_type="application/json",
            data={
                "question_id": second_question["id"],
                "answer_choice_id": second_question["choices"][0]["id"],
            },
        )
        self.assertEqual(response.status_code, 204)

        # Verify the answer state
        response = self.client.get(detail_url, content_type="application/json")
        data = response.json()
        answer = data["questions_and_answers"][1]["answers"][0]
        self.assertFalse(answer["timed_out"])
        self.assertEqual(answer["choice_id"], second_question["choices"][0]["id"])

    """ def test_duel_turn_flow_with_winner(self):
        win_duel(self.client, self.client2, self.user, self.user2) """


def _win_duel_base(
    client1: Client,
    client2: Client,
    user1: User,
    user2: User,
    selection_method: str = "random_official",
    n_rounds: int = 3,
    n_questions_per_round: int = 5,
    tournament_id: int | None = None,
) -> dict:
    """
    Base function for winning a duel between user1 and user2,
    where user1 answers all questions correctly and
    user2 answers some questions correctly (first question of each round)
    but most incorrectly, resulting in user1 winning the duel.

    Parameters:
    - client1: The client instance for user1.
    - client2: The client instance for user2.
    - user1: The first user (winner).
    - user2: The second user (loser).
    - selection_method: Method to select questions.
    - n_rounds: Number of rounds in the duel.
    - n_questions_per_round: Number of questions per round.
    - tournament_id: Optional tournament ID if this is a tournament duel.

    Returns:
    - final_duel_data: The final state of the duel.

    Raises:
    - Exception: If any of the API requests fail.
    """
    # Step 1: Create a new duel
    duel_create_url = reverse("api:duel_list")
    duel_data = {
        "selection_method": selection_method,
        "n_rounds": n_rounds,
        "n_questions_per_round": n_questions_per_round,
    }

    if tournament_id:
        duel_data.update({"user_id": None, "tournament_id": tournament_id})
    else:
        duel_data["user_id"] = user2.id

    duel_response = client1.post(
        duel_create_url, content_type="application/json", data=duel_data
    )
    if duel_response.status_code != 201:
        raise Exception(
            f"Duel creation failed with status {duel_response.status_code}: {duel_response.content}"
        )
    duel_id = duel_response.json()["id"]

    # Have user2 join if this is a tournament duel
    if tournament_id:
        tournament_join_url = reverse("api:duel_join_by_tournament")
        client2.patch(
            tournament_join_url,
            content_type="application/json",
            data={"tournament_id": tournament_id},
        )
    else:  # have user2 confirm participation if it is not a tournament duel
        duel_confirm_url = reverse("api:duel_confirm", args=[duel_id])
        client2.patch(duel_confirm_url, content_type="application/json")

    # Step 2: Retrieve duel details to get questions and answers
    duel_detail_url = reverse("api:duel_detail", args=[duel_id])
    duel_detail_response = client1.get(duel_detail_url, content_type="application/json")
    if duel_detail_response.status_code != 200:
        raise Exception(
            f"Fetching duel details failed with status {duel_detail_response.status_code}: {duel_detail_response.content}"
        )
    duel_data = duel_detail_response.json()
    questions = duel_data["questions_and_answers"]

    # Step 3: Submit answers for each round
    submit_answer_url = reverse("api:duel_submit_answer", args=[duel_id])
    question_seen_url = reverse("api:duel_question_seen", args=[duel_id])

    for round_num in range(n_rounds):
        if round_num % 2 == 0:
            attacking_client = client1
            defending_client = client2
        else:
            attacking_client = client2
            defending_client = client1

        # Helper function to submit answers for a turn
        def submit_turn_answers(client, is_client1):
            for i in range(n_questions_per_round):
                question = questions[round_num * n_questions_per_round + i]
                correct_choice = next(c for c in question["choices"] if c["is_correct"])
                incorrect_choice = next(
                    c for c in question["choices"] if not c["is_correct"]
                )

                # Mark question as seen before answering
                seen_response = client.patch(
                    question_seen_url,
                    content_type="application/json",
                    data={"question_id": question["id"]},
                )
                if seen_response.status_code != 204:
                    raise Exception(
                        f"Marking question as seen failed with status {seen_response.status_code}: {seen_response.content}"
                    )

                # Determine which choice to submit
                if is_client1:
                    choice_id = correct_choice["id"]  # User1 answers correctly
                else:
                    # User2 answers first question correctly, others incorrectly
                    choice_id = (
                        correct_choice["id"] if i == 0 else incorrect_choice["id"]
                    )

                response = client.patch(
                    submit_answer_url,
                    content_type="application/json",
                    data={
                        "question_id": question["id"],
                        "answer_choice_id": choice_id,
                    },
                )
                if response.status_code != 204:
                    raise Exception(
                        f"Submitting answer failed with status {response.status_code}: {response.content}"
                    )

        # Submit answers for both turns
        submit_turn_answers(attacking_client, attacking_client == client1)
        submit_turn_answers(defending_client, defending_client == client1)

    # Step 4: Verify the duel outcome
    final_duel_response = client1.get(duel_detail_url, content_type="application/json")
    if final_duel_response.status_code != 200:
        raise Exception(
            f"Fetching final duel state failed with status {final_duel_response.status_code}: {final_duel_response.content}"
        )
    final_duel_data = final_duel_response.json()

    # Verify duel completion and winner
    if final_duel_data.get("status") != "completed":
        raise Exception(
            f"Duel status is not 'completed'. Current status: {final_duel_data.get('status')}"
        )
    if final_duel_data.get("winner_id") != user1.id:
        raise Exception(
            f"Incorrect winner. Expected: {user1.id}, Got: {final_duel_data.get('winner_id')}"
        )
    if final_duel_data.get("current_turn_user_id") is not None:
        raise Exception("Current turn user should be None.")

    # Verify score changes
    participations = final_duel_data.get("participations", [])
    if len(participations) < 2:
        raise Exception("Insufficient participation data.")

    participation_user1 = next(
        (p for p in participations if p["user"]["id"] == user1.id), None
    )
    participation_user2 = next(
        (p for p in participations if p["user"]["id"] == user2.id), None
    )

    if not participation_user1 or not participation_user2:
        raise Exception("Participation data for one or both users is missing.")

    if not isinstance(participation_user1.get("duel_score_change"), float):
        raise Exception("User1 score change is not a float.")
    if not isinstance(participation_user2.get("duel_score_change"), float):
        raise Exception("User2 score change is not a float.")

    if participation_user1["duel_score_change"] <= 0:
        raise Exception("User1 score did not increase.")
    if participation_user2["duel_score_change"] >= 0:
        raise Exception("User2 score did not decrease.")

    if (
        round(
            participation_user1["duel_score_change"]
            + participation_user2["duel_score_change"],
            10,
        )
        != 0
    ):
        raise Exception("Score changes do not balance out.")

    return final_duel_data


def win_duel(
    client1,
    client2,
    user1,
    user2,
    selection_method="random_official",
    n_rounds=3,
    n_questions_per_round=5,
):
    """Wrapper for winning a regular duel"""
    return _win_duel_base(
        client1,
        client2,
        user1,
        user2,
        selection_method,
        n_rounds,
        n_questions_per_round,
    )


def win_duel_in_tournament(
    client1,
    client2,
    user1,
    user2,
    tournament_id,
    selection_method="random_official",
    n_rounds=3,
    n_questions_per_round=5,
):
    """Wrapper for winning a tournament duel"""
    return _win_duel_base(
        client1,
        client2,
        user1,
        user2,
        selection_method,
        n_rounds,
        n_questions_per_round,
        tournament_id,
    )
