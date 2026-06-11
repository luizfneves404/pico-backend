# myapp/management/commands/generate_answers.py

import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import models
from quiz.models import Session, SessionQuestionUser

User = get_user_model()


class Command(BaseCommand):
    help = "Populate SessionQuestionUser for all users"

    def handle(self, *args, **options):
        # Step 1: Create 500 users
        """created_users = []
        for i in range(1, 501):
            username = f"AutomaticCreatedUser{i}"
            password = username  # Example: Set password to username for simplicity
            phone_number = f"555-5555-{i:04d}"
            email = f"{username}@example.com"
            user = User.objects.create(
                username=username, email=email, phone_number=phone_number
            )
            user.set_password(password)
            user.save()
            created_users.append(user)
        self.stdout.write(self.style.SUCCESS(f"Created {len(created_users)} users"))"""
        created_users = User.objects.filter(username__startswith="AutomaticCreatedUser")

        # Step 2: Create SessionQuestionUser for each user
        quizzes = (
            Session.objects.annotate(question_count=models.Count("questions"))
            .filter(question_count__gt=0)
            .distinct()
        )

        for user in created_users:
            for _ in range(1, 30):
                quiz = random.choice(quizzes)

                # Select a random question from the quiz
                session_questions_in_quiz = quiz.session_question_set.all()
                if session_questions_in_quiz.count() == 0:
                    continue
                session_question = random.choice(session_questions_in_quiz)

                # Select a random choice for the selected question
                choices_for_question = session_question.choices.all()
                if choices_for_question.count() == 0:
                    continue
                choice = random.choice(choices_for_question)

                SessionQuestionUser.objects.get_or_create(
                    user=user,
                    session_question=session_question,
                    defaults={"choice": choice},
                )

        self.stdout.write(
            self.style.SUCCESS("SessionQuestionUser populated successfully")
        )
