import random

from api.models import User
from django.db import transaction

import quiz.duel_service as duel_service
from quiz.models import Choice, Duel, SessionQuestion, SessionQuestionUser


def do_random_turn(user: User, duel: Duel, correct_chance: float = 0.2) -> None:
    """
    Have a user, which is generally a bot, take their turn in a duel by answering questions with a specified chance of getting them correct.

    Args:
        user: The user taking the turn
        duel: The duel instance
        correct_chance: Float between 0 and 1 representing probability of choosing correct answer. Default is 0.2.
    """

    session_question_user = (
        SessionQuestionUser.objects.filter(
            session_question__session_id=duel.id,
            user_id=user.id,
        )
        .select_related("session_question")
        .order_by("session_question__order")
        .last()
    )

    if session_question_user:
        session_questions = (
            SessionQuestion.objects.filter(
                session_id=duel.id,
                order__gt=session_question_user.session_question.order,
            )
            .prefetch_related("question__choices")
            .order_by("order")[: duel.n_questions_per_round]
        )
    else:
        session_questions = (
            SessionQuestion.objects.filter(session_id=duel.id)
            .prefetch_related("question__choices")
            .order_by("order")
        )[: duel.n_questions_per_round]

    question_ids: list[int] = []
    choice_ids: list[int] = []

    for sq in session_questions:
        question_ids.append(sq.question_id)

        choices: list[Choice] = list(sq.question.choices.all())

        correct_choice: Choice | None = next((c for c in choices if c.is_correct), None)

        if not correct_choice:
            correct_choice = random.choice(choices)

        incorrect_choices: list[Choice] = [c for c in choices if not c.is_correct]

        if random.random() < correct_chance:
            # Choose correct answer
            choice_ids.append(correct_choice.id)
        else:
            # Choose random incorrect answer
            choice_ids.append(random.choice(incorrect_choices).id)

    with transaction.atomic():
        for question_id, answer_choice_id in zip(question_ids, choice_ids):
            duel_service.mark_question_seen(user.id, duel.id, question_id)
            duel_service.submit_answer(user, duel.id, question_id, answer_choice_id)
