# myapp/management/commands/generate_answers_for_user.py

import datetime
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, models
from django.utils import timezone
from quiz.models import Quiz

User = get_user_model()


class Command(BaseCommand):
    help = "Generate answers for a user"

    def add_arguments(self, parser):
        parser.add_argument("user", type=str, help="The username of the user")
        parser.add_argument("date", type=str, help="The date of the answers")

    def handle(self, *args, **options):
        user = User.objects.get(username=options["user"])
        date = options["date"]
        timestamp = timezone.make_aware(
            datetime.datetime.strptime(date, "%Y-%m-%d").replace(hour=10, minute=0),
            timezone.get_current_timezone(),
        )

        quizzes = list(
            Quiz.objects.annotate(question_count=models.Count("questions"))
            .filter(question_count__gt=0)
            .distinct()
        )

        for _ in range(1, 30):
            quiz = random.choice(quizzes)

            # Select a random question from the quiz
            session_questions_in_quiz = list(quiz.session_question_set.all())
            if len(session_questions_in_quiz) == 0:
                print(f"No questions for quiz {quiz.id}")
                continue
            session_question = random.choice(session_questions_in_quiz)

            # Select a random choice for the selected question
            choices_for_question = list(session_question.choices.all())
            if len(choices_for_question) == 0:
                print(f"No choices for question {session_question.id}")
                continue
            choice = random.choice(choices_for_question)

            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO quiz_sessionquestionuser (session_question_id, user_id, choice_id, timestamp, submitted_text, feedback, grade) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        [
                            session_question.id,
                            user.id,
                            choice.id,
                            timestamp,
                            "",
                            "",
                            None,
                        ],
                    )
            except Exception as e:
                print(
                    f"Error inserting answer for session_question_id: {session_question.id}, user_id: {user.id}, choice_id: {choice.id}, timestamp: {timestamp}: {e}"
                )
                continue
            print(
                f"Inserted answer for session_question_id: {session_question.id}, user_id: {user.id}, choice_id: {choice.id}, timestamp: {timestamp}"
            )

        self.stdout.write(self.style.SUCCESS("Successfully generated answers for user"))
