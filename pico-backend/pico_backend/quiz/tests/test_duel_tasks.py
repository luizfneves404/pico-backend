from api.tests.factories import SchoolFactory, UserFactory
from challenges.tests.factories import TournamentFactory
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from shared.testing import PatchingAndRedisTestCase

from pico_backend.auth import generate_tokens
from quiz.models import (
    Duel,
)
from quiz.tests.factories import QuestionFactory

User = get_user_model()


class BotDuelTasksTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        # Create users
        school = SchoolFactory.create(name="School A")
        school2 = SchoolFactory.create(name="School B")
        cls.user = UserFactory.create(school=school)
        cls.bot = UserFactory.create(
            username="bot1", is_bot=True, bot_difficulty=0.3, school=school2
        )
        cls.bot2 = UserFactory.create(
            username="bot2", is_bot=True, bot_difficulty=0.7, school=school
        )  # Same school as user

        # Create questions with choices for the duel
        cls.questions = QuestionFactory.create_batch_multiple_choice(15)
        cls.tournament = TournamentFactory.create()

        cls.access_token, _ = generate_tokens(cls.user)
        cls.auth_headers = {"Authorization": f"Bearer {cls.access_token}"}

    def _create_duel(self, selection_method="random_official"):
        """Helper method to create a duel with the specified selection method."""
        client = Client(headers=self.auth_headers)
        url = reverse("api:duel_list")
        response = client.post(
            url,
            content_type="application/json",
            data={
                "selection_method": selection_method,
                "n_rounds": 3,
                "n_questions_per_round": 2,
                "tournament_id": self.tournament.id,
            },
        )
        duel_id = response.json()["id"]
        return Duel.objects.get(id=duel_id)

    """ def test_bot_joins_and_answers_tournament_duel(self):
        #Test that a bot from a different school joins an eligible tournament duel.
        # Create a duel and make the first move
        duel = self._create_duel()
        bots.do_random_turn(self.user, duel)

        bot_join_and_answer_duels()

        # Check that a bot joined
        participation_manager = duel.session_participation_set
        self.assertEqual(participation_manager.count(), 2)
        bot_participation = participation_manager.exclude(user=self.user).first()
        self.assertTrue(bot_participation.user.is_bot)
        self.assertNotEqual(bot_participation.user.school, self.user.school)

        # Check that turns were assigned to the bot
        bot_turns: QuerySet[Turn] = Turn.objects.filter(
            round__duel=duel, user=bot_participation.user
        )
        self.assertEqual(bot_turns.count(), 3)

        # check that bot answered questions
        bot_answers: QuerySet[SessionQuestionUser] = SessionQuestionUser.objects.filter(
            session_question__session=duel, user=self.bot
        )
        self.assertEqual(bot_answers.count(), 2)

        # run func again
        bot_join_and_answer_duels()

        # check that bot answered questions
        bot_answers: QuerySet[SessionQuestionUser] = SessionQuestionUser.objects.filter(
            session_question__session=duel, user=self.bot
        )
        self.assertEqual(bot_answers.count(), 4)

        # Have player take their turns
        bots.do_random_turn(self.user, duel)
        bots.do_random_turn(self.user, duel)

        # run func again
        bot_join_and_answer_duels()

        # check that bot answered questions
        bot_answers: QuerySet[SessionQuestionUser] = SessionQuestionUser.objects.filter(
            session_question__session=duel, user=self.bot
        )
        self.assertEqual(bot_answers.count(), 6) """

    """ def test_bot_joins_and_answers_query_official_duel(self):
        # Test that a bot handles a QUERY_OFFICIAL duel correctly by adding questions by query.
        # Create a new duel with QUERY_OFFICIAL selection method
        query_official_duel = self._create_duel(selection_method="query_official")

        # User adds questions to the duel by query
        add_questions_url = reverse(
            "api:duel_add_questions", args=[query_official_duel.id]
        )
        client = Client(headers=self.auth_headers)
        response = client.patch(
            add_questions_url,
            content_type="application/json",
            data={
                "query": "physics concept",
                "area": "",
                "source_filter": "",
                "difficulty": "Média",
                "is_fast": True,
            },
        )
        self.assertEqual(response.status_code, 204)

        # User makes a move
        bots.do_random_turn(self.user, query_official_duel)

        # Run bot task to join and answer
        bot_join_and_answer_duels()

        # Verify bot joined
        participation_manager = query_official_duel.session_participation_set
        self.assertEqual(participation_manager.count(), 2)
        bot_participation = participation_manager.exclude(user=self.user).first()
        self.assertTrue(bot_participation.user.is_bot)

        # Check that bot answered questions
        bot_answers = SessionQuestionUser.objects.filter(
            session_question__session=query_official_duel, user=bot_participation.user
        )
        self.assertEqual(bot_answers.count(), 2)

        # run func again, adding questions for next round
        bot_join_and_answer_duels()

        # check that bot added questions
        total_questions = SessionQuestion.objects.filter(
            session=query_official_duel
        ).count()
        self.assertEqual(total_questions, 4)  # 2 from user's query + 2 from bot

        # check that bot answered questions
        bot_answers = SessionQuestionUser.objects.filter(
            session_question__session=query_official_duel, user=bot_participation.user
        )
        self.assertEqual(bot_answers.count(), 4)

        bots.do_random_turn(self.user, query_official_duel)

        add_questions_url = reverse(
            "api:duel_add_questions", args=[query_official_duel.id]
        )
        response = client.patch(
            add_questions_url,
            content_type="application/json",
            data={
                "query": "physics concept",
                "area": "",
                "source_filter": "",
                "difficulty": "",
                "is_fast": True,
            },
        )
        self.assertEqual(response.status_code, 204)

        bots.do_random_turn(self.user, query_official_duel)

        bot_join_and_answer_duels()

        # check that bot answered questions
        bot_answers = SessionQuestionUser.objects.filter(
            session_question__session=query_official_duel, user=bot_participation.user
        )
        self.assertEqual(bot_answers.count(), 6) """
