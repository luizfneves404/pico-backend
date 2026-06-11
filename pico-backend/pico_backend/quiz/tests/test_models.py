from api.tests.factories import UserFactory
from django.contrib.auth import get_user_model
from django.test import TestCase

from quiz.models import QuestionType, SessionQuestion
from quiz.tests.factories import QuestionFactory, QuizFactory

User = get_user_model()


class SessionQuestionOrderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.session = QuizFactory.create(
            question_type=QuestionType.MULTIPLE_CHOICE, created_by=cls.user
        )
        cls.questions = QuestionFactory.create_batch_multiple_choice(5)

    def test_automatic_ordering_on_create(self):
        """Test that questions are automatically ordered when created individually"""
        # Create session questions one by one
        session_questions = []
        for question in self.questions:
            sq = SessionQuestion.objects.create(session=self.session, question=question)
            session_questions.append(sq)

        # Check that orders are sequential
        for i, sq in enumerate(session_questions):
            self.assertEqual(sq.order, i)

    def test_bulk_create_ordering(self):
        """Test that questions are properly ordered when bulk created"""
        # Create session questions in bulk
        session_questions = [
            SessionQuestion(session=self.session, question=q) for q in self.questions
        ]
        SessionQuestion.objects.bulk_create(session_questions)

        # Retrieve and check orders
        created_questions = SessionQuestion.objects.filter(
            session=self.session
        ).order_by("order")

        for i, sq in enumerate(created_questions):
            self.assertEqual(sq.order, i)

    def test_order_maintained_after_deletion(self):
        """Test that existing orders are maintained when questions are deleted"""
        # Create session questions
        session_questions = []
        for question in self.questions:
            sq = SessionQuestion.objects.create(session=self.session, question=question)
            session_questions.append(sq)

        # Delete the second question
        session_questions[1].delete()

        # Check that remaining questions maintain their original order
        remaining_questions = SessionQuestion.objects.filter(
            session=self.session
        ).order_by("order")
        expected_orders = {
            session_questions[0].id: 0,  # First stays first
            session_questions[2].id: 2,  # Third keeps order 3
            session_questions[3].id: 3,  # Fourth keeps order 4
            session_questions[4].id: 4,  # Fifth keeps order 5
        }

        for sq in remaining_questions:
            self.assertEqual(sq.order, expected_orders[sq.id])

    def test_new_question_added_at_end(self):
        """Test that new questions are added at the end of existing questions"""
        # Create initial questions
        for i in range(3):  # Create first 3 questions
            SessionQuestion.objects.create(
                session=self.session, question=self.questions[i]
            )

        # Add a new question
        new_sq = SessionQuestion.objects.create(
            session=self.session, question=self.questions[3]
        )

        # Check that the new question was added at the end
        self.assertEqual(new_sq.order, 3)

        # Verify all orders are correct
        all_questions = SessionQuestion.objects.filter(session=self.session).order_by(
            "order"
        )
        for i, sq in enumerate(all_questions):
            self.assertEqual(sq.order, i)
