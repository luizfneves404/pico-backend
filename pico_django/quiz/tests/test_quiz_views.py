import quiz.session_service as session_service
from api.models import Chatroom, User
from api.tests.factories import MembershipFactory, OfficialChatroomFactory, UserFactory
from django.test import AsyncClient, Client
from django.urls import reverse
from pico_backend.auth import generate_tokens
from quiz.models import Question, QuestionType, Quiz, SessionQuestionUser
from quiz.tests.factories import QuestionFactory, QuizFactory
from shared.testing import PatchingAndRedisTestCase

NUM_WEAK_SUBCATEGORIES = 5


class QuizCoreTestCase(PatchingAndRedisTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user: User = UserFactory.create()
        cls.user2: User = UserFactory.create(
            school=cls.user.school, chosen_course=cls.user.chosen_course
        )
        cls.official_chatroom: Chatroom = OfficialChatroomFactory.create()
        MembershipFactory.create(user=cls.user, chatroom=cls.official_chatroom)
        cls.quiz1: Quiz = QuizFactory.create(
            question_type=QuestionType.MULTIPLE_CHOICE, created_by=cls.user
        )
        cls.quiz2: Quiz = QuizFactory.create(
            question_type=QuestionType.MULTIPLE_CHOICE, created_by=cls.user
        )
        multiple_choice_questions = QuestionFactory.create_batch_multiple_choice(50)
        session_service.add_questions_to_session(
            cls.quiz1.id, multiple_choice_questions[:10]
        )
        session_service.add_questions_to_session(
            cls.quiz2.id, multiple_choice_questions[10:20]
        )
        open_ended_questions: list[Question] = QuestionFactory.create_batch(20)
        cls.open_ended_quiz1: Quiz = QuizFactory.create(
            question_type=QuestionType.OPEN_ENDED, created_by=cls.user
        )
        session_service.add_questions_to_session(
            cls.open_ended_quiz1.id, open_ended_questions[:10]
        )
        cls.open_ended_quiz2: Quiz = QuizFactory.create(
            question_type=QuestionType.OPEN_ENDED, created_by=cls.user
        )
        session_service.add_questions_to_session(
            cls.open_ended_quiz2.id, open_ended_questions[10:20]
        )
        cls.access_token1, _ = generate_tokens(cls.user)
        cls.access_token2, _ = generate_tokens(cls.user2)
        cls.auth_headers1 = {"Authorization": f"Bearer {cls.access_token1}"}
        cls.auth_headers2 = {"Authorization": f"Bearer {cls.access_token2}"}

    def setUp(self):
        super().setUp()
        self.client = Client(headers=self.auth_headers1)
        self.client2 = Client(headers=self.auth_headers2)
        self.async_client = (
            AsyncClient()
        )  # you should pass headers when making the request

    def test_quiz_list(self):
        # answer questions for the quiz to appear
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

        url = reverse("api:quiz_list")
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_user_quizzes(self):
        url = reverse("api:user_quizzes", args=[self.user2.id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)
        # make user2 answer a quiz
        self.client2.post(
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
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_quiz_create_not_official_chatroom(self):
        url = reverse("api:quiz_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "chatroom_id": -1,
                "query": "What is the capital of France?",
                "area": "",
                "source_filter": "",
                "difficulty": "Fácil",
                "n_questions": 10,
                "question_type": "multiple_choice",
            },
        )
        self.assertEqual(response.status_code, 201)
        # check that all of the questions have the same difficulty as the quiz
        questions = response.json()["questions_and_answers"]
        self.assertEqual(len(questions), 10)
        for question in questions:
            self.assertEqual(question["difficulty"], "Fácil")

    def test_quiz_create_no_query(self):
        url = reverse("api:quiz_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "query": "",
                "area": "",
                "source_filter": "",
                "difficulty": "Difícil",
                "n_questions": 10,
                "question_type": "multiple_choice",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["questions_and_answers"]), 10)
        for question in response.json()["questions_and_answers"]:
            self.assertEqual(question["difficulty"], "Difícil")

    """ def test_create_quiz_with_parent_quiz(self):
        url = reverse("api:quiz_list")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "parent_quiz_id": self.quiz1.id,
                "query": "What is the capital of France?",
                "area": "",
                "source_filter": "",
                "difficulty": "Difícil",
                "n_questions": 10,
                "question_type": "multiple_choice",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["parent_quiz_id"], self.quiz1.id)
        # check that none of the questions are also on the parent quiz
        self.assertEqual(len(response.json()["questions_and_answers"]), 10)
        parent_quiz_questions = self.quiz1.questions.values_list("id", flat=True)
        for question in response.json()["questions_and_answers"]:
            self.assertNotIn(question["id"], parent_quiz_questions) """

    def test_create_personalized_quiz(self):
        url = reverse("api:create_personalized_quiz")
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "question_type": "multiple_choice",
                "parent_quiz_id": None,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["parent_quiz_id"], None)
        self.assertEqual(response.json()["quiz_type"], "personalized")
        self.assertEqual(
            len(response.json()["questions_and_answers"]), self.user.commitment
        )

    def test_quiz_detail(self):
        url = reverse("api:quiz_detail", args=[self.quiz1.id])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.quiz1.id)
        self.assertEqual(response.json()["source_filter"], self.quiz1.source_filter)
        self.assertEqual(response.json()["difficulty"], self.quiz1.difficulty)
        self.assertIsNotNone(response.json()["code"])
        self.assertRegex(response.json()["code"], r"^[A-Z0-9]{5}$")
        self.assertEqual(len(response.json()["questions_and_answers"]), 10)
        for question in response.json()["questions_and_answers"]:
            self.assertNotEqual(question["video_url"], "")

    def test_quiz_detail_not_found(self):
        url = reverse("api:quiz_detail", args=[9999])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_quiz_redeem(self):
        url = reverse("api:quiz_redeem", args=[self.quiz1.code])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_quiz_redeem_invalid_code(self):
        url = reverse("api:quiz_redeem", args=["?????"])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_quiz_redeem_lowercase_and_big_code(self):
        url = reverse("api:quiz_redeem", args=[self.quiz1.code.lower() + "XYZ"])
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_quiz_personalization_suggestions(self):
        url = reverse("api:quiz_personalization_suggestions")
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.json()), 0
        )  # since we dont have questions, change this to test actual functionality

    def test_submit_answers_multiple_choice(self):
        url = reverse("api:quiz_submit_multiple_choice", args=[self.quiz1.id])
        response = self.client.post(
            url,
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
        self.assertEqual(response.status_code, 204)
        self.assertEqual(SessionQuestionUser.objects.count(), 1)
        self.assertEqual(
            SessionQuestionUser.objects.first().choice.id,
            self.quiz1.questions.first().choices.first().id,
        )

    def test_submit_answers_multiple_choice_correct(self):
        url = reverse("api:quiz_submit_multiple_choice", args=[self.quiz1.id])
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "answers": [
                    {
                        "question_id": self.quiz1.questions.first().id,
                        "answer_choice_id": next(
                            choice.id
                            for choice in self.quiz1.questions.first().choices.all()
                            if choice.is_correct
                        ),
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(SessionQuestionUser.objects.count(), 1)

        # check that the user's dynamic score increased
        self.user.quiz_info.refresh_from_db()
        self.assertEqual(self.user.quiz_info.dynamic_score, 1)

    def test_submit_answers_multiple_choice_bad_format(self):
        url = reverse("api:quiz_submit_multiple_choice", args=[self.quiz1.id])
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "answers": [
                    {
                        "question_id": self.quiz1.questions.first().id,
                        "answer_choice_id": "bad format",
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_submit_answers_multiple_choice_too_little_fields(self):
        url = reverse("api:quiz_submit_multiple_choice", args=[self.quiz1.id])
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "answers": [
                    {
                        "question_id": self.quiz1.questions.first().id,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 422)

    async def test_submit_answers_open_ended(self):
        url = reverse("api:quiz_submit_open_ended", args=[self.open_ended_quiz1.id])
        response = await self.async_client.post(
            url,
            content_type="application/json",
            data={
                "question_id": (await self.open_ended_quiz1.questions.afirst()).id,
                "submitted_text": "This is a test answer",
            },
            headers=self.auth_headers1,
        )
        self.assertEqual(response.status_code, 200)
        # get the whole response, since it's a streaming response
        response_text = "".join(
            [chunk.decode("utf-8") async for chunk in response.streaming_content]
        )

        self.assertEqual(await SessionQuestionUser.objects.acount(), 1)
        self.assertEqual(
            (await SessionQuestionUser.objects.afirst()).submitted_text,
            "This is a test answer",
        )
        self.assertEqual((await SessionQuestionUser.objects.afirst()).grade, 0)

        feedback = (await SessionQuestionUser.objects.afirst()).feedback
        for i in range(1, 6):  # Check for chunks 1-5
            self.assertRegex(
                feedback,
                f"Mocked chunk {i} for mock_stream_gpt-4o_0.0_",
                f"Chunk {i} not found in feedback",
            )
        self.assertEqual(feedback, response_text)

    def test_submit_answers_open_ended_too_little_fields(self):
        url = reverse("api:quiz_submit_open_ended", args=[self.open_ended_quiz1.id])
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "question_id": self.open_ended_quiz1.questions.first().id,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_submit_answers_open_ended_question_not_of_quiz(self):
        url = reverse("api:quiz_submit_open_ended", args=[self.open_ended_quiz1.id])
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "question_id": self.quiz2.questions.first().id,
                "submitted_text": "This is a test answer",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_sumbit_answers_open_ended_question_empty_string(self):
        url = reverse("api:quiz_submit_open_ended", args=[self.open_ended_quiz1.id])
        response = self.client.post(
            url,
            content_type="application/json",
            data={
                "question_id": self.open_ended_quiz1.questions.first().id,
                "submitted_text": "",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_dynamic_ranking(self):
        url = reverse("api:user_ranking")
        # query param to get dynamic ranking
        response = self.client.get(
            url,
            {
                "score_type": "dynamic",
                "school_filter": self.user.school.id,
                "course_filter": self.user.chosen_course.name,
                "education_level_filter": self.user.education_level,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_percentage_ranking(self):
        url = reverse("api:user_ranking")
        response = self.client.get(
            url,
            {
                "score_type": "percentage",
                "school_filter": self.user.school.id,
                "course_filter": self.user.chosen_course.name,
                "education_level_filter": self.user.education_level,
                "subject": "Matemática",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_dynamic_ranking_with_answers(self):
        url = reverse("api:user_ranking")

        self.client.post(
            reverse("api:quiz_submit_multiple_choice", args=[self.quiz1.id]),
            content_type="application/json",
            data={
                "answers": [
                    {
                        "question_id": self.quiz1.questions.first().id,
                        "answer_choice_id": next(
                            choice.id
                            for choice in self.quiz1.questions.first().choices.all()
                            if choice.is_correct
                        ),
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
                        "answer_choice_id": next(
                            choice.id
                            for choice in self.quiz2.questions.first().choices.all()
                            if choice.is_correct
                        ),
                    }
                ]
            },
        )

        self.client2.post(
            reverse("api:quiz_submit_multiple_choice", args=[self.quiz1.id]),
            content_type="application/json",
            data={
                "answers": [
                    {
                        "question_id": self.quiz1.questions.first().id,
                        "answer_choice_id": next(
                            choice.id
                            for choice in self.quiz1.questions.first().choices.all()
                            if choice.is_correct
                        ),
                    }
                ]
            },
        )
        response = self.client.get(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

        # check that the user with more answers is ranked first
        self.assertEqual(response.json()[0]["id"], self.user.id)
        self.assertEqual(response.json()[0]["score"], 2)
        self.assertEqual(response.json()[1]["id"], self.user2.id)
        self.assertEqual(response.json()[1]["score"], 1)
