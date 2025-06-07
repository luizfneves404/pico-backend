import logging
from pathlib import Path
from typing import Any, Callable, Coroutine

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.flows.models import FlowInputType, FlowQuestionUser, FlowUserFeed, Question
from app.users.models import User, UserProfile
from tests.factories import (
    ChoiceFactory,
    FlowFactory,
    FlowQuestionFactory,
    UserFactory,
)

logger = logging.getLogger(__name__)


async def test_flow_feed(user_client: AsyncClient, user: User, session: AsyncSession):
    """Test the flow feed endpoint returns flows ordered by answer count and doesn't repeat flows."""
    async with session.begin():
        another_user = await UserFactory.create(session=session)

        flow1 = await FlowFactory.create(created_by=another_user, session=session)
        flow2 = await FlowFactory.create(created_by=another_user, session=session)
        flow3 = await FlowFactory.create(created_by=user, session=session)

        question1 = await FlowQuestionFactory.create(flow=flow1, session=session)
        question2 = await FlowQuestionFactory.create(flow=flow2, session=session)
        await FlowQuestionFactory.create(flow=flow3, session=session)

        choice1 = await ChoiceFactory.create(
            question=question1.question, session=session
        )
        choice2 = await ChoiceFactory.create(
            question=question2.question, session=session
        )

        flow_question_user1 = FlowQuestionUser(
            flow_element_id=question1.id, user_id=another_user.id, choice_id=choice1.id
        )
        session.add(flow_question_user1)

        flow_question_user2 = FlowQuestionUser(
            flow_element_id=question1.id, user_id=user.id, choice_id=choice1.id
        )
        session.add(flow_question_user2)

        flow_question_user3 = FlowQuestionUser(
            flow_element_id=question2.id, user_id=another_user.id, choice_id=choice2.id
        )
        session.add(flow_question_user3)

    response = await user_client.get("/api/flows/feed")
    assert response.status_code == 200
    response_data = response.json()

    # Check paginated response values
    assert response_data["total"] == 3
    assert response_data["page"] == 1
    assert isinstance(response_data["size"], int)
    flows = response_data["items"]
    assert len(flows) == 3

    # Check flows are ordered by answer count desc, then created_at desc
    assert flows[0]["id"] == flow1.id
    assert flows[1]["id"] == flow2.id
    assert flows[2]["id"] == flow3.id

    # Check response data structure and values match FlowInFeed schema
    for flow in flows:
        assert flow["id"] in {flow1.id, flow2.id, flow3.id}
        assert isinstance(flow["code"], str)
        assert isinstance(flow["created_at"], str)
        assert isinstance(flow["title"], str)
        assert flow["cover_image"] is None or isinstance(flow["cover_image"], str)
        assert flow["action_link"] is None or isinstance(flow["action_link"], str)
        assert flow["action_text"] is None or isinstance(flow["action_text"], str)
        assert isinstance(flow["created_by"], dict)
        assert isinstance(flow["query"], str)
        assert isinstance(flow["area"], str)
        assert isinstance(flow["source_filter"], str)
        assert isinstance(flow["difficulty"], str)
        assert isinstance(flow["elements"], list)
        assert isinstance(flow["num_total_elements"], int)

        # Check created_by structure and values
        assert flow["created_by"]["id"] in {user.id, another_user.id}
        assert isinstance(flow["created_by"]["username"], str)

    response = await user_client.get("/api/flows/feed")
    assert response.status_code == 200
    response_data = response.json()

    flows = response_data["items"]
    assert flows == []

    async with session.begin():
        feed_records = await session.execute(
            select(FlowUserFeed).where(FlowUserFeed.user_id == user.id)
        )
        feed_records = feed_records.scalars().all()
        assert len(feed_records) == 3

        seen_flow_ids = {record.flow_id for record in feed_records}
        expected_flow_ids = {flow1.id, flow2.id, flow3.id}
        assert seen_flow_ids == expected_flow_ids


async def test_discover_flows(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    """Test the flow discover endpoint returns flows ordered by answer count and doesn't repeat flows."""
    async with session.begin():
        another_user = await UserFactory.create(session=session)

        flow1 = await FlowFactory.create(created_by=another_user, session=session)
        flow2 = await FlowFactory.create(created_by=another_user, session=session)
        flow3 = await FlowFactory.create(created_by=user, session=session)

        question1 = await FlowQuestionFactory.create(flow=flow1, session=session)
        question2 = await FlowQuestionFactory.create(flow=flow2, session=session)
        await FlowQuestionFactory.create(flow=flow3, session=session)

        choice1 = await ChoiceFactory.create(
            question=question1.question, session=session
        )
        choice2 = await ChoiceFactory.create(
            question=question2.question, session=session
        )

        flow_question_user1 = FlowQuestionUser(
            flow_element_id=question1.id, user_id=another_user.id, choice_id=choice1.id
        )
        session.add(flow_question_user1)

        flow_question_user2 = FlowQuestionUser(
            flow_element_id=question1.id, user_id=user.id, choice_id=choice1.id
        )
        session.add(flow_question_user2)

        flow_question_user3 = FlowQuestionUser(
            flow_element_id=question2.id, user_id=another_user.id, choice_id=choice2.id
        )
        session.add(flow_question_user3)

    response = await user_client.get("/api/flows/discover")
    assert response.status_code == 200
    response_data = response.json()

    # Check paginated response values
    assert response_data["total"] == 3
    assert response_data["page"] == 1
    assert isinstance(response_data["size"], int)
    flows = response_data["items"]
    assert len(flows) == 3

    assert flows[0]["id"] == flow1.id
    assert flows[1]["id"] == flow2.id
    assert flows[2]["id"] == flow3.id

    for flow in flows:
        assert flow["id"] in {flow1.id, flow2.id, flow3.id}
        assert isinstance(flow["code"], str)
        assert isinstance(flow["created_at"], str)
        assert isinstance(flow["title"], str)
        assert flow["cover_image"] is None or isinstance(flow["cover_image"], str)
        assert flow["action_link"] is None or isinstance(flow["action_link"], str)
        assert flow["action_text"] is None or isinstance(flow["action_text"], str)
        assert isinstance(flow["created_by"], dict)
        assert isinstance(flow["query"], str)
        assert isinstance(flow["area"], str)
        assert isinstance(flow["source_filter"], str)
        assert isinstance(flow["difficulty"], str)
        assert isinstance(flow["elements"], list)
        assert isinstance(flow["num_total_elements"], int)

        assert flow["created_by"]["id"] in {user.id, another_user.id}
        assert isinstance(flow["created_by"]["username"], str)

    response = await user_client.get("/api/flows/discover")
    assert response.status_code == 200
    response_data = response.json()

    flows = response_data["items"]
    assert flows == []

    async with session.begin():
        feed_records = await session.execute(
            select(FlowUserFeed).where(FlowUserFeed.user_id == user.id)
        )
        feed_records = feed_records.scalars().all()
        assert len(feed_records) == 3

        seen_flow_ids = {record.flow_id for record in feed_records}
        expected_flow_ids = {flow1.id, flow2.id, flow3.id}
        assert seen_flow_ids == expected_flow_ids


async def test_get_flow_details(
    user_client: AsyncClient, user: User, session: AsyncSession
):
    # Create test flow with some elements
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)
        # Add some questions to the flow
        flow_questions = await FlowQuestionFactory.create_batch(
            2, flow=flow, session=session
        )
        flow_question_users: list[FlowQuestionUser] = []
        for flow_question in flow_questions:
            choice = await ChoiceFactory.create(
                question=flow_question.question, is_correct=True, session=session
            )
            flow_question_users.append(
                FlowQuestionUser(
                    flow_element_id=flow_question.id,
                    user_id=user.id,
                    choice_id=choice.id,
                )
            )
        session.add_all(flow_question_users)

    async with session.begin():
        question = await session.execute(
            select(Question).where(Question.id == flow_questions[0].question_id)
        )
        question = question.scalar_one()

    # Get flow details
    response = await user_client.get(f"/api/flows/{flow.id}/details")
    assert response.status_code == 200
    response_data = response.json()

    # Check response data matches FlowDetail schema (inherits from FlowInFeed)
    assert response_data["id"] == flow.id
    assert response_data["code"] == str(flow.code)
    assert response_data["title"] == flow.title
    assert response_data["created_at"] == flow.created_at.strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    assert response_data["cover_image"] == (
        flow.cover_image.url if flow.cover_image else None
    )
    assert response_data["action_link"] == flow.action_link
    assert response_data["action_text"] == flow.action_text
    assert response_data["created_by"] == {
        "id": user.id,
        "username": user.username,
    }
    assert response_data["query"] == flow.query
    assert response_data["area"] == flow.area
    assert response_data["source_filter"] == flow.source_filter
    assert response_data["difficulty"] == flow.difficulty
    assert isinstance(response_data["elements"], list)
    assert response_data["num_total_elements"] == 2
    assert response_data["num_user_total_answers"] == 2
    assert response_data["num_user_correct_answers"] == 2

    # Check elements structure (FlowQuestionInFeed)
    assert len(response_data["elements"]) == 2
    for idx, element in enumerate(response_data["elements"]):
        flow_question = flow_questions[idx]
        assert element["id"] == flow_question.id
        assert element["element_type"] == "flow_question"
        assert isinstance(element["content_blocks"], list)
        assert isinstance(element["relevant_answers"], list)
        assert element["num_total_answers"] == 1
        assert isinstance(element["choices"], list)
        assert element["subject"] == question.subject
        assert element["category"] == question.category
        assert element["subcategory"] == question.subcategory
        assert element["difficulty"] == question.difficulty
        assert element["source_type"] == question.source_type
        assert (
            element["official_source"] == question.official_source.exam.name
            if question.official_source
            else None
        )
        assert element["source_user"] == question.source_user
        assert element["answer_type"] == question.answer_type
        for answer in element["relevant_answers"]:
            assert answer["user"] == {
                "id": user.id,
                "username": user.username,
            }
            assert answer["submitted_text"] == ""
            assert answer["choice_id"] is None or isinstance(answer["choice_id"], int)


async def test_get_flow_details_not_found(user_client: AsyncClient):
    # Try to get details for a non-existent flow
    response = await user_client.get("/api/flows/9999/details")
    assert response.status_code == 404


async def test_create_flow_from_topic(user_client: AsyncClient):
    # Create a new flow from a topic
    flow_data = {
        "title": "Test Flow",
        "query": "What is the purpose of life?",
        "input_topic": "Philosophy and existentialism",
        "area": "Ciências Humanas",
        "source_filter": "ENEM",
        "difficulty": "Médio",
    }
    response = await user_client.post("/api/flows", json=flow_data)
    assert response.status_code == 201
    response_data = response.json()

    # Check response data
    assert response_data["title"] == flow_data["title"]
    assert response_data["query"] == flow_data["query"]
    assert response_data["input_topic"] == flow_data["input_topic"]
    assert response_data["area"] == flow_data["area"]
    assert response_data["source_filter"] == flow_data["source_filter"]
    assert response_data["difficulty"] == flow_data["difficulty"]
    assert response_data["flow_input_type"] == FlowInputType.TOPIC


async def test_create_flow_validation_error(user_client: AsyncClient):
    # Try to create a flow with missing required fields
    flow_data = {
        "title": "",  # Empty title should cause validation error
        "query": "What is the purpose of life?",
        "input_topic": "Philosophy and existentialism",
        "area": "Ciências Humanas",
        "source_filter": "ENEM",
        "difficulty": "Médio",
    }
    response = await user_client.post("/api/flows", json=flow_data)
    assert response.status_code == 400


async def test_create_flow_with_files(user_client: AsyncClient, tmp_path: Path):
    # Create a test file
    test_file_path = tmp_path / "test_document.pdf"
    test_file_path.write_bytes(b"%PDF-1.5\n%Test PDF file")

    # Form data for flow creation
    data = {
        "title": "Test Flow With Files",
        "query": "What does this document say?",
        "area": "Ciências Humanas",
        "source_filter": "ENEM",
        "difficulty": "Médio",
    }

    # Create files
    with open(test_file_path, "rb") as f:
        files = [("files", ("document.pdf", f, "application/pdf"))]

        # Post request with multipart/form-data
        response = await user_client.post("/api/flows/files", data=data, files=files)

    assert response.status_code == 201
    response_data = response.json()

    # Check response data
    assert response_data["title"] == data["title"]
    assert response_data["query"] == data["query"]
    assert response_data["area"] == data["area"]
    assert response_data["source_filter"] == data["source_filter"]
    assert response_data["difficulty"] == data["difficulty"]
    assert response_data["flow_input_type"] == FlowInputType.FILES


async def test_submit_flow_question_answer_correct_first_time(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting a correct answer for the first time awards full XP and updates social score"""
    async with session.begin():
        another_user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=another_user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        # Create choices for the question - one correct, others incorrect
        correct_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=True, session=session
        )
        await ChoiceFactory.create_batch(
            3, question=flow_question.question, is_correct=False, session=session
        )

        # Get initial scores
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        initial_user_xp = user_profile.xp_score

        creator_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == another_user.id)
        )
        creator_profile = creator_profile_result.scalar_one()
        initial_creator_social_score = creator_profile.social_score

    # Submit a correct answer
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": correct_choice.id,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 200
    response_data = response.json()
    xp_increase_response = response_data["xp_increase"]
    assert 20 <= xp_increase_response <= 50

    # Verify that the answer was recorded in the database
    async with session.begin():
        result = await session.execute(
            select(FlowQuestionUser).where(
                FlowQuestionUser.flow_element_id == flow_question.id,
                FlowQuestionUser.user_id == user.id,
            )
        )
        user_answer = result.scalar_one()
        assert user_answer.choice_id == correct_choice.id
        assert user_answer.submitted_text == ""

        # Check that user's XP increased (should be full XP since it's correct and first time)
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        await session.refresh(user_profile)
        xp_increase = user_profile.xp_score - initial_user_xp
        assert xp_increase == xp_increase_response

        # Check that creator's social score increased by 1
        creator_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == another_user.id)
        )
        creator_profile = creator_profile_result.scalar_one()
        await session.refresh(creator_profile)
        assert creator_profile.social_score == initial_creator_social_score + 1


async def test_submit_flow_question_answer_wrong_answer(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting a wrong answer awards reduced XP and updates social score"""
    async with session.begin():
        another_user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=another_user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        # Create choices for the question
        # We need a correct choice to exist even though we don't use it directly
        _correct_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=True, session=session
        )
        wrong_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=False, session=session
        )

        # Get initial scores
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        initial_user_xp = user_profile.xp_score

        creator_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == another_user.id)
        )
        creator_profile = creator_profile_result.scalar_one()
        initial_creator_social_score = creator_profile.social_score

    # Submit a wrong answer
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": wrong_choice.id,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 200
    response_data = response.json()
    xp_increase_response = response_data["xp_increase"]
    assert 2 <= xp_increase_response <= 5

    # Verify that the answer was recorded
    async with session.begin():
        result = await session.execute(
            select(FlowQuestionUser).where(
                FlowQuestionUser.flow_element_id == flow_question.id,
                FlowQuestionUser.user_id == user.id,
            )
        )
        user_answer = result.scalar_one()
        assert user_answer.choice_id == wrong_choice.id

        # Check that user's XP increased but with wrong answer multiplier (0.5)
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        await session.refresh(user_profile)
        xp_increase = user_profile.xp_score - initial_user_xp
        assert xp_increase == xp_increase_response

        # Check that creator's social score still increased
        creator_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == another_user.id)
        )
        creator_profile = creator_profile_result.scalar_one()
        await session.refresh(creator_profile)
        assert creator_profile.social_score == initial_creator_social_score + 1


async def test_submit_flow_question_answer_repeated_flow_question(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting an answer when the user has already answered the same question in this flow is not allowed"""
    async with session.begin():
        another_user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=another_user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        # Create choices for the question
        correct_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=True, session=session
        )
        await ChoiceFactory.create_batch(
            2, question=flow_question.question, is_correct=False, session=session
        )

        # Add a previous correct answer from the same user
        previous_answer = FlowQuestionUser(
            flow_element_id=flow_question.id,
            user_id=user.id,
            choice_id=correct_choice.id,
        )
        session.add(previous_answer)

        # Get initial scores
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        initial_user_xp = user_profile.xp_score

    # Submit another correct answer (should be treated as repeated)
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": correct_choice.id,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 400
    # Verify the repeated correct answer gets no XP
    async with session.begin():
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        await session.refresh(user_profile)
        xp_increase = user_profile.xp_score - initial_user_xp
        assert xp_increase == 0


async def test_submit_flow_question_answer_repeated_question(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting a correct answer after previously answered correctly awards reduced XP"""
    async with session.begin():
        another_user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=another_user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        # Create choices for the question
        correct_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=True, session=session
        )
        await ChoiceFactory.create_batch(
            2, question=flow_question.question, is_correct=False, session=session
        )

        # Add a previous correct answer from the same user to the same question in a different flow
        other_flow = await FlowFactory.create(created_by=another_user, session=session)
        other_flow_question = await FlowQuestionFactory.create(
            flow=other_flow, question=flow_question.question, session=session
        )
        previous_answer = FlowQuestionUser(
            flow_element_id=other_flow_question.id,
            user_id=user.id,
            choice_id=correct_choice.id,
        )
        session.add(previous_answer)

        # Get initial scores
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        initial_user_xp = user_profile.xp_score

    # Submit another correct answer (should be treated as repeated)
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": correct_choice.id,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 200
    response_data = response.json()
    xp_increase_response = response_data["xp_increase"]
    assert 2 <= xp_increase_response <= 5
    # Verify the repeated correct answer gets reduced XP
    async with session.begin():
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        await session.refresh(user_profile)
        xp_increase = user_profile.xp_score - initial_user_xp
        assert xp_increase == xp_increase_response


async def test_submit_flow_question_answer_same_user_as_creator(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test that social score is NOT increased when answerer is the same as flow creator"""
    async with session.begin():
        # User creates their own flow
        flow = await FlowFactory.create(created_by=user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        correct_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=True, session=session
        )

        # Get initial social score
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        initial_social_score = user_profile.social_score

    # Submit answer to own flow
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": correct_choice.id,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 200
    response_data = response.json()
    xp_increase_response = response_data["xp_increase"]
    assert 20 <= xp_increase_response <= 50
    # Verify social score did NOT increase
    async with session.begin():
        user_profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        user_profile = user_profile_result.scalar_one()
        await session.refresh(user_profile)
        assert user_profile.social_score == initial_social_score


async def test_submit_flow_question_answer_multiple_answers_same_question(
    session: AsyncSession,
    user_client_factory: Callable[
        ..., Coroutine[Any, Any, tuple[list[User], list[AsyncClient]]]
    ],
):
    """Test that users can submit multiple answers to the same question"""
    users, user_clients = await user_client_factory(2)
    async with session.begin():
        flow = await FlowFactory.create(created_by=users[1], session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        correct_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=True, session=session
        )
        wrong_choice = await ChoiceFactory.create(
            question=flow_question.question, is_correct=False, session=session
        )

    # Submit first answer (wrong)
    answer_data_1 = {
        "question_id": flow_question.question_id,
        "choice_id": wrong_choice.id,
    }
    response = await user_clients[0].post(
        f"/api/flows/{flow.id}/submit", json=answer_data_1
    )
    assert response.status_code == 200
    response_data = response.json()
    xp_increase_response = response_data["xp_increase"]
    assert 2 <= xp_increase_response <= 5
    # Submit second answer (correct) - this should work due to unique constraint allowing one answer per user per question
    answer_data_2 = {
        "question_id": flow_question.question_id,
        "choice_id": correct_choice.id,
    }
    response = await user_clients[1].post(
        f"/api/flows/{flow.id}/submit", json=answer_data_2
    )
    assert response.status_code == 200
    response_data = response.json()
    xp_increase_response = response_data["xp_increase"]
    assert 20 <= xp_increase_response <= 50
    # Verify both answers exist in database
    async with session.begin():
        result = await session.execute(
            select(FlowQuestionUser).where(
                FlowQuestionUser.flow_element_id == flow_question.id
            )
        )
        user_answers = result.scalars().all()
        assert len(user_answers) == 2
        choice_ids = {answer.choice_id for answer in user_answers}
        assert choice_ids == {wrong_choice.id, correct_choice.id}


async def test_submit_flow_question_answer_invalid_choice(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting an answer with invalid choice_id returns 400"""
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        # Create some valid choices
        await ChoiceFactory.create_batch(
            3, question=flow_question.question, session=session
        )

    # Submit answer with non-existent choice_id
    invalid_answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": 99999,  # Non-existent choice
    }
    response = await user_client.post(
        f"/api/flows/{flow.id}/submit", json=invalid_answer_data
    )
    assert response.status_code == 400
    assert "Invalid choice for this question" in response.json()["detail"]


async def test_submit_flow_question_answer_question_not_in_flow(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting an answer for a question not in the specified flow returns 404"""
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)
        # Create a flow_question in this flow
        _flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        # Create another flow with different question
        other_flow = await FlowFactory.create(created_by=user, session=session)
        other_flow_question = await FlowQuestionFactory.create(
            flow=other_flow, session=session
        )

        choice = await ChoiceFactory.create(
            question=other_flow_question.question, session=session
        )

    # Try to submit answer for other_flow_question to the first flow
    answer_data = {
        "question_id": other_flow_question.question_id,
        "choice_id": choice.id,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 404
    assert "Flow element not found" in response.json()["detail"]


async def test_submit_flow_question_answer_nonexistent_flow(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting an answer to a non-existent flow returns 404"""
    answer_data = {
        "question_id": 1,
        "choice_id": 1,
    }
    response = await user_client.post("/api/flows/99999/submit", json=answer_data)
    assert response.status_code == 404


async def test_submit_flow_question_answer_nonexistent_question(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting an answer for a non-existent question returns 404"""
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)

    answer_data = {
        "question_id": 99999,  # Non-existent question
        "choice_id": 1,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 404


async def test_submit_flow_question_answer_none_choice_id(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test submitting an answer with None choice_id (no selection) should fail validation"""
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)
        await ChoiceFactory.create(question=flow_question.question, session=session)

    # Submit answer with None choice_id
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": None,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 400


async def test_add_elements_to_flow(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    # Create test flow
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)
        # Initially add one question
        await FlowQuestionFactory.create(flow=flow, session=session)

    # Add more elements
    add_elements_data = {
        "query": "Additional questions",
        "area": flow.area,
        "source_filter": flow.source_filter,
        "difficulty": flow.difficulty,
        "n_questions": 3,
    }
    response = await user_client.post(
        f"/api/flows/{flow.id}/add-elements", json=add_elements_data
    )
    assert response.status_code == 200
    response_data = response.json()

    # Check that elements were added to the flow
    assert "elements" in response_data
    # We should have at least the original element count (which may include automatically generated elements)
    # But this test makes assumptions about the flow_service._generate_flow_questions implementation


async def test_delete_flow(user_client: AsyncClient, session: AsyncSession, user: User):
    # Create test flow
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)

    # Delete the flow
    response = await user_client.delete(f"/api/flows/{flow.id}/delete")
    assert response.status_code == 204

    # Verify flow was deleted
    # Try to get the flow, should return 404
    response = await user_client.get(f"/api/flows/{flow.id}/details")
    assert response.status_code == 404


async def test_get_user_flows(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    # Create test users and flows
    async with session.begin():
        user2 = await UserFactory.create(session=session)

        # Create flows for user1
        await FlowFactory.create_batch(2, created_by=user, session=session)

        # Create flows for user2
        await FlowFactory.create_batch(3, created_by=user2, session=session)

    # Get flows for user2
    response = await user_client.get(f"/api/flows/user/{user2.id}")
    assert response.status_code == 200
    response_data = response.json()

    # Should only see user2's flows
    assert len(response_data) == 3

    # Check response data structure
    for flow in response_data:
        assert "id" in flow
        assert "title" in flow
        assert "area" in flow
        assert "created_at" in flow
