from datetime import timedelta
from datetime import timezone as datetime_timezone

from challenges.models import TournamentStatus
from challenges.tests.factories import (
    PrizeFactory,
    TournamentFactory,
    TournamentParticipationFactory,
)
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pico_backend.auth import generate_tokens
from quiz.tests.factories import QuestionFactory
from shared.testing import PatchingAndRedisTestCase


class TournamentViewsTests(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.tournament = TournamentFactory.create()

        # add many users to the tournament
        cls.tournament_participations = TournamentParticipationFactory.create_batch(
            10, tournament=cls.tournament
        )

        # for each of them, generate an access token
        cls.access_tokens = [
            generate_tokens(tournament_participation.user)[0]
            for tournament_participation in cls.tournament_participations
        ]
        cls.auth_headers = [
            {"Authorization": f"Bearer {access_token}"}
            for access_token in cls.access_tokens
        ]

        cls.prizes = PrizeFactory.create_batch(4, tournament=cls.tournament)

        cls.multiple_choice_questions = QuestionFactory.create_batch_multiple_choice(50)

    def setUp(self):
        super().setUp()
        self.clients = [
            Client(headers=auth_header) for auth_header in self.auth_headers
        ]

    def _mark_question_seen_and_submit_answer(
        self, client, duel_id, question_id, answer_choice_id
    ):
        """Helper method to mark a question as seen before submitting an answer."""
        # Mark the question as seen first
        seen_url = reverse("api:duel_question_seen", args=[duel_id])
        seen_response = client.patch(
            seen_url,
            content_type="application/json",
            data={"question_id": question_id},
        )
        self.assertEqual(
            seen_response.status_code,
            204,
            f"Failed to mark question {question_id} as seen",
        )

        # Then submit the answer
        submit_url = reverse("api:duel_submit_answer", args=[duel_id])
        submit_response = client.patch(
            submit_url,
            content_type="application/json",
            data={
                "question_id": question_id,
                "answer_choice_id": answer_choice_id,
            },
        )
        self.assertEqual(
            submit_response.status_code,
            204,
            f"Failed to submit answer for question {question_id}",
        )
        return submit_response

    def test_tournament_join_by_code(self):
        # remove the user from the tournament
        self.tournament_participations[0].delete()

        url = reverse("api:tournament_join_by_code")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={"tournament_code": self.tournament.code},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.tournament.id)
        self.assertEqual(
            any(
                participation["id"] == self.tournament_participations[0].user.id
                for participation in response.json()["participations"]
            ),
            True,
        )
        self.assertEqual(len(response.json()["participations"]), 10)

    def test_create_duel_in_tournament_ongoing(self):
        # tournament detail to confirm has no pending duel
        url = reverse("api:tournament_detail", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        # create a duel within the tournament
        url = reverse("api:duel_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_id": None,
                "tournament_id": self.tournament.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["tournament_id"], self.tournament.id)
        self.assertEqual(
            response.json()["participations"][0]["user"]["id"],
            self.tournament_participations[0].user.id,
        )

        # tournament detail to confirm has pending duel
        url = reverse("api:tournament_detail", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_create_duel_in_tournament_ongoing_with_user_id(self):
        url = reverse("api:duel_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_id": self.tournament_participations[0].user.id,
                "tournament_id": self.tournament.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        self.assertEqual(response.status_code, 422)
        # confirm it wasnt created
        url = reverse("api:tournament_detail", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_create_duel_in_tournament_upcoming(self):
        self.tournament.start_time = timezone.now() + timedelta(days=1)
        self.tournament.end_time = timezone.now() + timedelta(days=2)
        self.tournament.status = TournamentStatus.UPCOMING
        self.tournament.save()

        url = reverse("api:tournament_detail", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        # create a duel within the tournament
        url = reverse("api:duel_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_id": None,
                "tournament_id": self.tournament.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Tournament is not active")

    def test_create_duel_in_tournament_completed(self):
        self.tournament.start_time = timezone.now() - timedelta(days=2)
        self.tournament.end_time = timezone.now() - timedelta(days=1)
        self.tournament.status = TournamentStatus.COMPLETED
        self.tournament.save()

        url = reverse("api:tournament_detail", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        # create a duel within the tournament
        url = reverse("api:duel_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_id": None,
                "tournament_id": self.tournament.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Tournament is not active")

    def test_join_duel_by_tournament(self):
        # tournament detail to confirm has no pending duel
        url = reverse("api:tournament_detail", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        # create a duel within the tournament
        url = reverse("api:duel_list")
        response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_id": None,
                "tournament_id": self.tournament.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        self.assertEqual(response.status_code, 201)

        # tournament detail to confirm has pending duel
        url = reverse("api:tournament_detail", args=[self.tournament.id])
        response = self.clients[1].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        # join the duel
        url = reverse("api:duel_join_by_tournament")
        response = self.clients[1].patch(
            url,
            content_type="application/json",
            data={"tournament_id": self.tournament.id},
        )
        self.assertEqual(response.status_code, 200)
        # check that there are two participations
        self.assertEqual(len(response.json()["participations"]), 2)
        self.assertEqual(
            any(
                participation["user"]["id"] == self.tournament_participations[0].user.id
                for participation in response.json()["participations"]
            ),
            True,
        )
        self.assertEqual(
            any(
                participation["user"]["id"] == self.tournament_participations[1].user.id
                for participation in response.json()["participations"]
            ),
            True,
        )

    def test_tournament_list(self):
        url = reverse("api:tournament_list")
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["id"], self.tournament.id)
        self.assertEqual(response.json()[0]["name"], self.tournament.name)
        self.assertEqual(response.json()[0]["description"], self.tournament.description)
        self.assertEqual(
            response.json()[0]["start_time"],
            self.tournament.start_time.astimezone(datetime_timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        )
        self.assertEqual(
            response.json()[0]["end_time"],
            self.tournament.end_time.astimezone(datetime_timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        )
        self.assertEqual(response.json()[0]["status"], "ongoing")

    """ def test_tournament_detail(self):
        url = reverse("api:tournament_detail", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.tournament.id)
        self.assertEqual(response.json()["name"], self.tournament.name)
        self.assertEqual(response.json()["description"], self.tournament.description)
        self.assertEqual(
            response.json()["start_time"],
            self.tournament.start_time.astimezone(datetime_timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        )
        self.assertEqual(
            response.json()["end_time"],
            self.tournament.end_time.astimezone(datetime_timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        )
        self.assertEqual(response.json()["status"], "ongoing")
        self.assertEqual(len(response.json()["participations"]), 10)
        for idx, participation in enumerate(response.json()["participations"]):
            # the user is there
            self.assertEqual(
                participation["id"], self.tournament_participations[idx].user.id
            )
            self.assertEqual(
                participation["username"],
                self.tournament_participations[idx].user.username,
            )
            self.assertEqual(participation["score"], 0)
            self.assertEqual(participation["rank"], idx + 1)
            if idx < len(self.prizes):
                self.assertEqual(participation["prize"], self.prizes[idx].amount)
            else:
                self.assertEqual(participation["prize"], 0)

        win_duel_in_tournament(
            self.clients[1],
            self.clients[4],
            self.tournament_participations[1].user,
            self.tournament_participations[4].user,
            self.tournament.id,
        )
        win_duel_in_tournament(
            self.clients[1],
            self.clients[5],
            self.tournament_participations[1].user,
            self.tournament_participations[5].user,
            self.tournament.id,
        )
        win_duel_in_tournament(
            self.clients[0],
            self.clients[6],
            self.tournament_participations[0].user,
            self.tournament_participations[6].user,
            self.tournament.id,
        )
        win_duel_in_tournament(
            self.clients[2],
            self.clients[7],
            self.tournament_participations[2].user,
            self.tournament_participations[7].user,
            self.tournament.id,
        )
        win_duel_in_tournament(
            self.clients[2],
            self.clients[8],
            self.tournament_participations[2].user,
            self.tournament_participations[8].user,
            self.tournament.id,
        )
        win_duel_in_tournament(
            self.clients[1],
            self.clients[2],
            self.tournament_participations[1].user,
            self.tournament_participations[2].user,
            self.tournament.id,
        )

        # final order should be (take into account win = 10, loss = -5)
        # 1. user 1 (score 30)
        # 2. user 2 (score 15)
        # 3. user 0 (score 10)
        # 4. user 3 (score 0)
        # 5. user 9 (score 0)
        # 6. user 4 (score -5)
        # 7. user 5 (score -5)
        # 8. user 6 (score -5)
        # 9. user 7 (score -5)
        # 10. user 8 (score -5)

        # Refresh the tournament object to get updated data
        self.tournament.refresh_from_db()

        # Final GET request to verify the updated state
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        participations = response.json()["participations"]
        self.assertEqual(len(participations), 10)

        # Define the expected final order with corresponding scores. take into account win = 10, loss = -5
        expected_order = [
            {"user_idx": 1, "score": 30},  # user1
            {"user_idx": 2, "score": 15},  # user2
            {"user_idx": 0, "score": 10},  # user0
            {"user_idx": 3, "score": 0},  # user3
            {"user_idx": 9, "score": 0},  # user9
            {"user_idx": 4, "score": -5},  # user4
            {"user_idx": 5, "score": -5},  # user5
            {"user_idx": 6, "score": -5},  # user6
            {"user_idx": 7, "score": -5},  # user7
            {"user_idx": 8, "score": -5},  # user8
        ]

        for idx, expected in enumerate(expected_order):
            participation = participations[idx]
            expected_participation = self.tournament_participations[
                expected["user_idx"]
            ].user

            # Verify user ID
            self.assertEqual(
                participation["id"],
                expected_participation.id,
                f"Participant at rank {idx + 1} has incorrect ID.",
            )

            # Verify username
            self.assertEqual(
                participation["username"],
                expected_participation.username,
                f"Participant at rank {idx + 1} has incorrect username.",
            )

            # Verify score
            self.assertEqual(
                participation["score"],
                expected["score"],
                f"Participant {expected_participation.username} has incorrect score.",
            )

            # Verify rank
            self.assertEqual(
                participation["rank"],
                idx + 1,
                f"Participant {expected_participation.username} has incorrect rank.",
            )

            # Verify prize if applicable
            if idx < len(self.prizes):
                expected_prize = self.prizes[idx].amount
            else:
                expected_prize = 0
            self.assertEqual(
                participation["prize"],
                expected_prize,
                f"Participant {expected_participation.username} has incorrect prize.",
            ) """

    def test_tournament_detail_does_not_exist(self):
        url = reverse("api:tournament_detail", args=[self.tournament.id + 999999999999])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_has_pending_duels(self):
        url = reverse("api:tournament_has_pending_duels", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), False)

        # create a duel within the tournament
        url = reverse("api:duel_list")
        duel_response = self.clients[0].post(
            url,
            content_type="application/json",
            data={
                "user_id": None,
                "tournament_id": self.tournament.id,
                "selection_method": "random_official",
                "n_rounds": 3,
                "n_questions_per_round": 5,
            },
        )
        self.assertEqual(duel_response.status_code, 201)

        url = reverse("api:tournament_has_pending_duels", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), False)

        # Get duel details to get questions
        duel_id = duel_response.json()["id"]
        questions = duel_response.json()["questions_and_answers"]

        # Answer first 5 questions
        for i in range(5):
            question = questions[i]
            correct_choice = next(c for c in question["choices"] if c["is_correct"])
            self._mark_question_seen_and_submit_answer(
                self.clients[0], duel_id, question["id"], correct_choice["id"]
            )

        # check that there is a pending duel
        url = reverse("api:tournament_has_pending_duels", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), True)

        # someone else joins the duel
        url = reverse("api:duel_join_by_tournament")
        response = self.clients[1].patch(
            url,
            content_type="application/json",
            data={"tournament_id": self.tournament.id},
        )

        url = reverse("api:tournament_has_pending_duels", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), False)

    """ def test_school_ranking(self):
        win_duel_in_tournament(
            self.clients[0],
            self.clients[1],
            self.tournament_participations[0].user,
            self.tournament_participations[1].user,
            self.tournament.id,
        )

        win_duel_in_tournament(
            self.clients[0],
            self.clients[2],
            self.tournament_participations[0].user,
            self.tournament_participations[2].user,
            self.tournament.id,
        )

        url = reverse("api:tournament_school_ranking", args=[self.tournament.id])
        response = self.clients[0].get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        schools_data = response.json()

        # First school won 2 duels
        self.assertEqual(schools_data[0]["score"], 20)
        # Other schools lost 1 duel each
        for i in range(1, 8):
            school = schools_data[i]
            user_school = self.tournament_participations[i + 2].user.school
            self.assertEqual(school["id"], user_school.id)
            self.assertEqual(school["name"], user_school.name)
            self.assertEqual(school["rank"], i + 1)

        self.assertEqual(
            schools_data[8]["id"],
            self.tournament_participations[1].user.school.id,
        )
        self.assertEqual(
            schools_data[8]["name"],
            self.tournament_participations[1].user.school.name,
        )
        self.assertEqual(schools_data[8]["score"], -5)
        self.assertEqual(schools_data[8]["rank"], 9)

        self.assertEqual(
            schools_data[9]["id"],
            self.tournament_participations[2].user.school.id,
        )
        self.assertEqual(
            schools_data[9]["name"],
            self.tournament_participations[2].user.school.name,
        )
        self.assertEqual(schools_data[9]["score"], -5)
        self.assertEqual(schools_data[9]["rank"], 10) """
