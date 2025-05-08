import random
from collections import defaultdict

from asgiref.sync import sync_to_async
from django.db import connection

import quiz.question_service as question_service
from quiz.models import SessionQuestionUser

NUM_WEAK_SUBCATEGORIES = 5
NUM_QUESTIONS_FOR_WEAK_SUBCATEGORIES = 200


def update_dynamic_score(user_id: int, n_answers: int):
    sql = """
    UPDATE quiz_userinfo
    SET dynamic_score = dynamic_score + %s
    WHERE user_id = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [n_answers, user_id])


def get_subcategory_data(user_answers) -> list[dict[str, str | int | float]]:
    if not user_answers:
        return []

    subcategory_data = defaultdict(lambda: {"correct": 0, "total_answers": 0})
    for answer in user_answers:
        subcategory = answer["session_question__question__subcategory"]
        if not subcategory:
            continue
        subcategory_data[subcategory]["total_answers"] += 1
        if answer["choice__is_correct"]:
            subcategory_data[subcategory]["correct"] += 1
    total_questions_dict = (
        question_service.get_total_multiple_choice_questions_per_subcategory()
    )
    return [
        {
            "subcategory": subcategory,
            "accuracy": (
                (data["correct"] / data["total_answers"])
                if data["total_answers"] > 0
                else 0.0
            ),
            "questions_done": data["total_answers"],
            "total_questions": total_questions_dict.get(subcategory, 0),
        }
        for subcategory, data in subcategory_data.items()
    ]


def identify_weak_subcategories(user_id: int) -> set[str]:
    user_answers = (
        SessionQuestionUser.objects.filter(user_id=user_id)
        .filter_by_type("multiple_choice")
        .order_by("-timestamp")
    )
    user_answers_for_weak_subcategories = user_answers[
        :NUM_QUESTIONS_FOR_WEAK_SUBCATEGORIES
    ].values("session_question__question__subcategory", "choice__is_correct")

    subcategory_data = get_subcategory_data(user_answers_for_weak_subcategories)

    all_subcategories = set(
        question_service.get_total_multiple_choice_questions_per_subcategory().keys()
    )

    # Sort subcategories by accuracy (ascending), then by questions done (descending), then by total questions (descending)
    sorted_subcategories = sorted(
        subcategory_data,
        key=lambda x: (x["accuracy"], -x["questions_done"], -x["total_questions"]),
    )

    # Get the weakest subcategories from user data
    weak_subcategories = {
        item["subcategory"] for item in sorted_subcategories[:NUM_WEAK_SUBCATEGORIES]
    }

    # Calculate the number of additional subcategories needed
    num_additional_needed = NUM_WEAK_SUBCATEGORIES - len(weak_subcategories)

    remaining_subcategories = all_subcategories - weak_subcategories

    # Adjust the sample size to the number of available remaining subcategories
    num_to_sample = min(num_additional_needed, len(remaining_subcategories))

    additional_subcategories = set(
        random.sample(
            list(remaining_subcategories),
            num_to_sample,
        )
    )

    return weak_subcategories.union(additional_subcategories)


async def aidentify_weak_subcategories(user_id: int) -> set[str]:
    return await sync_to_async(identify_weak_subcategories)(user_id)
