from httpx._client import AsyncClient

from app.quiz.models import Quiz, SessionQuestionUser
from app.users.models import User

NUM_WEAK_SUBCATEGORIES = 5


async def test_quiz_list(client: AsyncClient, user: User, quiz1: Quiz, quiz2: Quiz):
    # answer questions for the quiz to appear
    await client.post(
        f"/quiz/{quiz1.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz1.questions.afirst()).id,
                    "answer_choice_id": (
                        await (await quiz1.questions.afirst()).choices.afirst()
                    ).id,
                }
            ]
        },
    )
    await client.post(
        f"/quiz/{quiz2.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz2.questions.afirst()).id,
                    "answer_choice_id": (
                        await (await quiz2.questions.afirst()).choices.afirst()
                    ).id,
                }
            ]
        },
    )

    response = await client.get("/quiz")
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_user_quizzes(client: AsyncClient, user: User, user2: User, quiz1: Quiz):
    response = await client.get(f"/users/{user2.id}/quizzes")
    assert response.status_code == 200
    assert len(response.json()) == 0

    # make user2 answer a quiz
    await client.post(
        f"/quiz/{quiz1.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz1.questions.afirst()).id,
                    "answer_choice_id": (
                        await (await quiz1.questions.afirst()).choices.afirst()
                    ).id,
                }
            ]
        },
    )
    response = await client.get(f"/users/{user2.id}/quizzes")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_quiz_create_not_official_chatroom(client: AsyncClient):
    response = await client.post(
        "/quiz",
        json={
            "chatroom_id": -1,
            "query": "What is the capital of France?",
            "area": "",
            "source_filter": "",
            "difficulty": "Fácil",
            "n_questions": 10,
            "question_type": "multiple_choice",
        },
    )
    assert response.status_code == 201
    # check that all of the questions have the same difficulty as the quiz
    questions = response.json()["questions_and_answers"]
    assert len(questions) == 10
    for question in questions:
        assert question["difficulty"] == "Fácil"


async def test_quiz_create_no_query(client: AsyncClient):
    response = await client.post(
        "/quiz",
        json={
            "query": "",
            "area": "",
            "source_filter": "",
            "difficulty": "Difícil",
            "n_questions": 10,
            "question_type": "multiple_choice",
        },
    )
    assert response.status_code == 201
    assert len(response.json()["questions_and_answers"]) == 10
    for question in response.json()["questions_and_answers"]:
        assert question["difficulty"] == "Difícil"


async def test_create_quiz_with_parent_quiz(client: AsyncClient, quiz1: Quiz):
    response = await client.post(
        "/quiz",
        json={
            "parent_quiz_id": quiz1.id,
            "query": "What is the capital of France?",
            "area": "",
            "source_filter": "",
            "difficulty": "Difícil",
            "n_questions": 10,
            "question_type": "multiple_choice",
        },
    )
    assert response.status_code == 201
    assert response.json()["parent_quiz_id"] == quiz1.id
    # check that none of the questions are also on the parent quiz
    assert len(response.json()["questions_and_answers"]) == 10
    parent_quiz_questions = await quiz1.questions.values_list("id", flat=True)
    for question in response.json()["questions_and_answers"]:
        assert question["id"] not in parent_quiz_questions


async def test_create_personalized_quiz(client: AsyncClient, user: User, quiz1: Quiz):
    response = await client.post(
        "/quiz/personalized",
        json={
            "question_type": "multiple_choice",
            "parent_quiz_id": quiz1.id,
        },
    )
    assert response.status_code == 201
    assert response.json()["parent_quiz_id"] == quiz1.id
    assert response.json()["quiz_type"] == "personalized"
    assert len(response.json()["questions_and_answers"]) == user.commitment
    # assert that the questions are not on the parent quiz
    parent_quiz_questions = await quiz1.questions.values_list("id", flat=True)
    for question in response.json()["questions_and_answers"]:
        assert question["id"] not in parent_quiz_questions


async def test_quiz_detail(client: AsyncClient, quiz1: Quiz):
    response = await client.get(f"/quiz/{quiz1.id}")
    assert response.status_code == 200
    assert response.json()["id"] == quiz1.id
    assert response.json()["source_filter"] == quiz1.source_filter
    assert response.json()["difficulty"] == quiz1.difficulty
    assert response.json()["code"] is not None
    assert response.json()["code"].match(r"^[A-Z0-9]{5}$")
    assert len(response.json()["questions_and_answers"]) == 10
    for question in response.json()["questions_and_answers"]:
        assert question["video_url"] != ""


async def test_quiz_detail_not_found(client: AsyncClient):
    response = await client.get("/quiz/9999")
    assert response.status_code == 404


async def test_quiz_redeem(client: AsyncClient, quiz1: Quiz):
    response = await client.get(f"/quiz/redeem/{quiz1.code}")
    assert response.status_code == 200


async def test_quiz_redeem_invalid_code(client: AsyncClient):
    response = await client.get("/quiz/redeem/?????")
    assert response.status_code == 404


async def test_quiz_redeem_lowercase_and_big_code(client: AsyncClient, quiz1: Quiz):
    response = await client.get(f"/quiz/redeem/{quiz1.code.lower()}XYZ")
    assert response.status_code == 200


async def test_quiz_personalization_suggestions(client: AsyncClient):
    response = await client.get("/quiz/personalization-suggestions")
    assert response.status_code == 200
    assert (
        len(response.json()) == 0
    )  # since we dont have questions, change this to test actual functionality


async def test_submit_answers_multiple_choice(client: AsyncClient, quiz1: Quiz):
    response = await client.post(
        f"/quiz/{quiz1.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz1.questions.afirst()).id,
                    "answer_choice_id": (
                        await (await quiz1.questions.afirst()).choices.afirst()
                    ).id,
                }
            ]
        },
    )
    assert response.status_code == 200
    assert await SessionQuestionUser.objects.acount() == 1
    assert (await SessionQuestionUser.objects.afirst()).choice.id == (
        await (await quiz1.questions.afirst()).choices.afirst()
    ).id


async def test_submit_answers_multiple_choice_correct(
    client: AsyncClient, quiz1: Quiz, user: User
):
    response = await client.post(
        f"/quiz/{quiz1.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz1.questions.afirst()).id,
                    "answer_choice_id": next(
                        choice.id
                        for choice in await (
                            await quiz1.questions.afirst()
                        ).choices.all()
                        if choice.is_correct
                    ),
                }
            ]
        },
    )
    assert response.status_code == 200
    assert await SessionQuestionUser.objects.acount() == 1

    # check that the user's dynamic score increased
    await user.quiz_info.arefresh_from_db()
    assert user.quiz_info.dynamic_score == 1


async def test_submit_answers_multiple_choice_bad_format(
    client: AsyncClient, quiz1: Quiz
):
    response = await client.post(
        f"/quiz/{quiz1.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz1.questions.afirst()).id,
                    "answer_choice_id": "bad format",
                }
            ]
        },
    )
    assert response.status_code == 422


async def test_submit_answers_multiple_choice_too_little_fields(
    client: AsyncClient, quiz1: Quiz
):
    response = await client.post(
        f"/quiz/{quiz1.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz1.questions.afirst()).id,
                }
            ]
        },
    )
    assert response.status_code == 422


async def test_submit_answers_open_ended(client: AsyncClient, open_ended_quiz1: Quiz):
    response = await client.post(
        f"/quiz/{open_ended_quiz1.id}/submit-open-ended",
        json={
            "question_id": (await open_ended_quiz1.questions.afirst()).id,
            "submitted_text": "This is a test answer",
        },
    )
    assert response.status_code == 200
    # get the whole response, since it's a streaming response
    response_text = "".join(
        [chunk.decode("utf-8") async for chunk in response.streaming_content]
    )

    assert await SessionQuestionUser.objects.acount() == 1
    assert (
        await SessionQuestionUser.objects.afirst()
    ).submitted_text == "This is a test answer"
    assert (await SessionQuestionUser.objects.afirst()).grade == 0

    feedback = (await SessionQuestionUser.objects.afirst()).feedback
    for i in range(1, 6):  # Check for chunks 1-5
        assert feedback.match(
            f"Mocked chunk {i} for mock_stream_gpt-4o_0.0_",
            f"Chunk {i} not found in feedback",
        )
    assert feedback == response_text


async def test_submit_answers_open_ended_too_little_fields(
    client: AsyncClient, open_ended_quiz1: Quiz
):
    response = await client.post(
        f"/quiz/{open_ended_quiz1.id}/submit-open-ended",
        json={
            "question_id": (await open_ended_quiz1.questions.afirst()).id,
        },
    )
    assert response.status_code == 422


async def test_submit_answers_open_ended_question_not_of_quiz(
    client: AsyncClient, open_ended_quiz1: Quiz, quiz2: Quiz
):
    response = await client.post(
        f"/quiz/{open_ended_quiz1.id}/submit-open-ended",
        json={
            "question_id": (await quiz2.questions.afirst()).id,
            "submitted_text": "This is a test answer",
        },
    )
    assert response.status_code == 400


async def test_submit_answers_open_ended_question_empty_string(
    client: AsyncClient, open_ended_quiz1: Quiz
):
    response = await client.post(
        f"/quiz/{open_ended_quiz1.id}/submit-open-ended",
        json={
            "question_id": (await open_ended_quiz1.questions.afirst()).id,
            "submitted_text": "",
        },
    )
    assert response.status_code == 422


async def test_dynamic_ranking(client: AsyncClient, user: User):
    response = await client.get(
        "/users/ranking",
        params={
            "score_type": "dynamic",
            "school_filter": user.school.id,
            "course_filter": user.chosen_course.name,
            "education_level_filter": user.education_level,
        },
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_percentage_ranking(client: AsyncClient, user: User):
    response = await client.get(
        "/users/ranking",
        params={
            "score_type": "percentage",
            "school_filter": user.school.id,
            "course_filter": user.chosen_course.name,
            "education_level_filter": user.education_level,
            "subject": "Matemática",
        },
    )
    assert response.status_code == 200
    assert len(response.json()) == 0


async def test_dynamic_ranking_with_answers(
    client: AsyncClient, user: User, user2: User, quiz1: Quiz, quiz2: Quiz
):
    await client.post(
        f"/quiz/{quiz1.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz1.questions.afirst()).id,
                    "answer_choice_id": next(
                        choice.id
                        for choice in await (
                            await quiz1.questions.afirst()
                        ).choices.all()
                        if choice.is_correct
                    ),
                }
            ]
        },
    )

    await client.post(
        f"/quiz/{quiz2.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz2.questions.afirst()).id,
                    "answer_choice_id": next(
                        choice.id
                        for choice in await (
                            await quiz2.questions.afirst()
                        ).choices.all()
                        if choice.is_correct
                    ),
                }
            ]
        },
    )

    await client.post(
        f"/quiz/{quiz1.id}/submit-multiple-choice",
        json={
            "answers": [
                {
                    "question_id": (await quiz1.questions.afirst()).id,
                    "answer_choice_id": next(
                        choice.id
                        for choice in await (
                            await quiz1.questions.afirst()
                        ).choices.all()
                        if choice.is_correct
                    ),
                }
            ]
        },
    )

    response = await client.get("/users/ranking")
    assert response.status_code == 200
    assert len(response.json()) == 2

    # check that the user with more answers is ranked first
    assert response.json()[0]["id"] == user.id
    assert response.json()[0]["score"] == 2
    assert response.json()[1]["id"] == user2.id
    assert response.json()[1]["score"] == 1
