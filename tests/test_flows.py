import logging
from typing import Any, Callable, Coroutine

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.flows.models import FlowQuestionUser, FlowUserFeed, Question
from app.users.models import User
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
    assert response_data["page"] == 1
    assert isinstance(response_data["size"], int)
    flows = response_data["items"]
    assert len(flows) == 3

    # Check flows are ordered by answer count desc, then created_at desc
    assert flows[0]["item"]["id"] == flow1.id
    assert flows[1]["item"]["id"] == flow2.id
    assert flows[2]["item"]["id"] == flow3.id

    # Check response data structure and values match FlowInFeed schema
    for flow_item in flows:
        assert flow_item["item_type"] == "flow"
        flow = flow_item["item"]
        assert flow["id"] in {flow1.id, flow2.id, flow3.id}
        assert isinstance(flow["code"], str)
        assert isinstance(flow["created_at"], str)
        assert isinstance(flow["title"], str)
        assert flow["cover_image_url"] is None or isinstance(
            flow["cover_image_url"], str
        )
        assert isinstance(flow["action_link"], str)
        assert isinstance(flow["action_text"], str)
        assert isinstance(flow["created_by"], dict)
        assert isinstance(flow["difficulty"], str)
        assert isinstance(flow["max_num_questions"], int)
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
        assert flow["cover_image_url"] is None or isinstance(
            flow["cover_image_url"], str
        )
        assert isinstance(flow["action_link"], str)
        assert isinstance(flow["action_text"], str)
        assert isinstance(flow["created_by"], dict)
        assert isinstance(flow["difficulty"], str)
        assert isinstance(flow["max_num_questions"], int)
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
    assert response_data["cover_image_url"] == (
        await flow.cover_image.get_url() if flow.cover_image else None
    )
    assert response_data["action_link"] == flow.action_link
    assert response_data["action_text"] == flow.action_text
    assert response_data["created_by"] == {
        "id": user.id,
        "username": user.username,
    }
    assert response_data["difficulty"] == flow.difficulty
    assert response_data["max_num_questions"] == flow.max_num_questions
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
        assert isinstance(element["answer_content_blocks"], list)
        assert isinstance(element["relevant_answers"], list)
        assert element["num_total_answers"] == 1
        assert isinstance(element["choices"], list)
        assert isinstance(element["is_quantitative"], bool)
        assert isinstance(element["major_tags"], list)
        assert isinstance(element["minor_tags"], list)
        assert isinstance(element["difficulty"], str)
        assert isinstance(element["source_type"], str)
        assert (
            element["official_source"] == question.official_source.exam.name
            if question.official_source
            else None
        )
        assert element["source_user"] == (
            {
                "id": question.source_user.id,
                "username": question.source_user.username,
            }
            if question.source_user
            else None
        )
        assert isinstance(element["answer_type"], str)
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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        initial_user_xp = user.xp_score

        creator_result = await session.execute(
            select(User).where(User.id == another_user.id)
        )
        creator = creator_result.scalar_one()
        initial_creator_social_score = creator.social_score

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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        await session.refresh(user)
        xp_increase = user.xp_score - initial_user_xp
        assert xp_increase == xp_increase_response

        # Check that creator's social score increased by 1
        creator_result = await session.execute(
            select(User).where(User.id == another_user.id)
        )
        creator = creator_result.scalar_one()
        await session.refresh(creator)
        assert creator.social_score == initial_creator_social_score + 1


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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        initial_user_xp = user.xp_score

        creator_result = await session.execute(
            select(User).where(User.id == another_user.id)
        )
        creator = creator_result.scalar_one()
        initial_creator_social_score = creator.social_score

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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        await session.refresh(user)
        xp_increase = user.xp_score - initial_user_xp
        assert xp_increase == xp_increase_response

        # Check that creator's social score still increased
        creator_result = await session.execute(
            select(User).where(User.id == another_user.id)
        )
        creator = creator_result.scalar_one()
        await session.refresh(creator)
        assert creator.social_score == initial_creator_social_score + 1


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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        initial_user_xp = user.xp_score

    # Submit another correct answer (should be treated as repeated)
    answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": correct_choice.id,
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 400
    # Verify the repeated correct answer gets no XP
    async with session.begin():
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        await session.refresh(user)
        xp_increase = user.xp_score - initial_user_xp
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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        initial_user_xp = user.xp_score

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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        await session.refresh(user)
        xp_increase = user.xp_score - initial_user_xp
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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        initial_social_score = user.social_score

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
        user_result = await session.execute(select(User).where(User.id == user.id))
        user = user_result.scalar_one()
        await session.refresh(user)
        assert user.social_score == initial_social_score


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
        assert "difficulty" in flow
        assert "created_at" in flow
        assert "max_num_questions" in flow
        assert "num_user_total_answers" in flow
        assert "num_user_correct_answers" in flow


async def test_search_flows_basic_functionality(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test basic search functionality returns flows matching the query"""
    async with session.begin():
        # Create flows with specific tags for testing
        flow1 = await FlowFactory.create(
            created_by=user,
            major_tags=["python", "programming"],
            minor_tags=["beginner", "tutorial"],
            session=session,
        )
        flow2 = await FlowFactory.create(
            created_by=user,
            major_tags=["javascript", "web"],
            minor_tags=["frontend", "react"],
            session=session,
        )
        flow3 = await FlowFactory.create(
            created_by=user,
            major_tags=["data", "science"],
            minor_tags=["python", "analysis"],
            session=session,
        )

    # Search for flows containing "python"
    response = await user_client.get("/api/flows/search?query=python")
    assert response.status_code == 200
    response_data = response.json()

    # Check paginated response structure
    assert "page" in response_data
    assert "size" in response_data
    assert "items" in response_data
    assert response_data["page"] == 1
    assert isinstance(response_data["size"], int)

    flows = response_data["items"]
    # Should find flow1 (python in major_tags) and flow3 (python in minor_tags)
    assert len(flows) == 2

    # Verify structure of returned flows matches FlowInSearch schema
    for flow in flows:
        assert "id" in flow
        assert "code" in flow
        assert "created_at" in flow
        assert "title" in flow
        assert "cover_image_url" in flow
        assert "action_link" in flow
        assert "action_text" in flow
        assert "created_by" in flow
        assert "difficulty" in flow
        assert "max_num_questions" in flow
        assert "elements" in flow
        assert "num_total_elements" in flow
        assert "num_user_total_answers" in flow
        assert "num_user_correct_answers" in flow

        # Check created_by structure
        assert "id" in flow["created_by"]
        assert "username" in flow["created_by"]

    # Verify correct flows are returned
    flow_ids = {flow["id"] for flow in flows}
    assert flow1.id in flow_ids
    assert flow3.id in flow_ids
    assert flow2.id not in flow_ids


async def test_search_flows_weighted_scoring(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test that flows with matches in major_tags rank higher than those with matches in minor_tags"""
    async with session.begin():
        # Create flows where search term appears in different tag types
        flow_major = await FlowFactory.create(
            created_by=user,
            major_tags=["machine", "learning"],
            minor_tags=["algorithms", "data"],
            session=session,
        )
        flow_minor = await FlowFactory.create(
            created_by=user,
            major_tags=["statistics", "math"],
            minor_tags=["machine", "probability"],
            session=session,
        )

    # Search for "machine" - should find both flows but flow_major should rank higher
    response = await user_client.get("/api/flows/search?query=machine")
    assert response.status_code == 200
    response_data = response.json()

    flows = response_data["items"]
    assert len(flows) == 2

    # Flow with "machine" in major_tags should be ranked first due to higher weight
    assert flows[0]["id"] == flow_major.id
    assert flows[1]["id"] == flow_minor.id


async def test_search_flows_pagination(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test that pagination works correctly for search results"""
    async with session.begin():
        # Create multiple flows with the same searchable tag
        await FlowFactory.create_batch(
            5, created_by=user, major_tags=["testing"], session=session
        )

    # Test first page with size 2
    response = await user_client.get("/api/flows/search?query=testing&page=1&size=2")
    assert response.status_code == 200
    response_data = response.json()
    print("response_data", response_data)

    assert response_data["page"] == 1
    assert response_data["size"] == 2
    assert len(response_data["items"]) == 2

    # Test second page with size 2
    response = await user_client.get("/api/flows/search?query=testing&page=2&size=2")
    assert response.status_code == 200
    response_data = response.json()
    print("response_data", response_data)

    assert response_data["page"] == 2
    assert response_data["size"] == 2
    assert len(response_data["items"]) == 2

    # Test third page with size 2 (should have 1 item)
    response = await user_client.get("/api/flows/search?query=testing&page=3&size=2")
    assert response.status_code == 200
    response_data = response.json()
    print("response_data", response_data)
    assert response_data["page"] == 3
    assert response_data["size"] == 2
    assert len(response_data["items"]) == 1

    # Test page beyond available results
    response = await user_client.get("/api/flows/search?query=testing&page=4&size=2")
    assert response.status_code == 200
    response_data = response.json()

    assert response_data["page"] == 4
    assert response_data["size"] == 2
    assert len(response_data["items"]) == 0


async def test_search_flows_no_results(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test search with query that matches no flows"""
    async with session.begin():
        # Create some flows with known tags
        await FlowFactory.create(
            created_by=user,
            major_tags=["python", "programming"],
            minor_tags=["beginner"],
            session=session,
        )

    # Search for something that doesn't exist
    response = await user_client.get("/api/flows/search?query=nonexistentterm")
    assert response.status_code == 200
    response_data = response.json()

    assert response_data["page"] == 1
    assert isinstance(response_data["size"], int)
    assert response_data["items"] == []


async def test_search_flows_empty_query(user_client: AsyncClient):
    """Test search with empty query parameter"""
    response = await user_client.get("/api/flows/search?query=")
    assert response.status_code == 200
    response_data = response.json()

    # Empty query should return no results
    assert response_data["items"] == []


async def test_search_flows_missing_query_parameter(user_client: AsyncClient):
    """Test search endpoint without query parameter"""
    response = await user_client.get("/api/flows/search")
    # Should return 422 due to missing required query parameter
    assert response.status_code == 422


async def test_search_flows_case_insensitive(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test that search is case insensitive"""
    async with session.begin():
        flow = await FlowFactory.create(
            created_by=user,
            major_tags=["Python", "Programming"],
            minor_tags=["BEGINNER"],
            session=session,
        )

    # Search with different cases
    test_queries = [
        "python",
        "PYTHON",
        "Python",
        "programming",
        "PROGRAMMING",
        "beginner",
        "BEGINNER",
    ]

    for query in test_queries:
        response = await user_client.get(f"/api/flows/search?query={query}")
        assert response.status_code == 200
        response_data = response.json()

        # Should find the flow regardless of case
        flow_ids = {flow["id"] for flow in response_data["items"]}
        assert flow.id in flow_ids


async def test_search_flows_partial_match(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test that search supports partial matching"""
    async with session.begin():
        flow = await FlowFactory.create(
            created_by=user,
            major_tags=["machine-learning", "artificial-intelligence"],
            minor_tags=["deep-learning"],
            session=session,
        )

    # Test partial matches
    partial_queries = ["machine", "learning", "artificial", "intelligence", "deep"]

    for query in partial_queries:
        response = await user_client.get(f"/api/flows/search?query={query}")
        assert response.status_code == 200
        response_data = response.json()

        # Should find the flow with partial match
        flow_ids = {flow["id"] for flow in response_data["items"]}
        assert flow.id in flow_ids


async def test_search_flows_multiple_terms(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test search with multiple terms"""
    async with session.begin():
        flow1 = await FlowFactory.create(
            created_by=user,
            major_tags=["python", "web", "development"],
            minor_tags=["flask", "django"],
            session=session,
        )
        await FlowFactory.create(
            created_by=user,
            major_tags=["javascript", "web", "frontend"],
            minor_tags=["react", "vue"],
            session=session,
        )
        await FlowFactory.create(
            created_by=user,
            major_tags=["data", "science"],
            minor_tags=["analysis", "visualization"],
            session=session,
        )

    # Search for flows containing both "web" and "development"
    response = await user_client.get("/api/flows/search?query=web development")
    assert response.status_code == 200
    response_data = response.json()

    flows = response_data["items"]
    # Should find flows that match the search terms
    assert len(flows) >= 1

    # Verify we get relevant results
    flow_ids = {flow["id"] for flow in flows}
    # flow1 should definitely be found as it has both "web" and "development"
    assert flow1.id in flow_ids


async def test_search_flows_different_users(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test that search returns flows from different users"""
    async with session.begin():
        another_user = await UserFactory.create(session=session)

        # Create flows from different users with same searchable content
        flow1 = await FlowFactory.create(
            created_by=user, major_tags=["shared", "topic"], session=session
        )
        flow2 = await FlowFactory.create(
            created_by=another_user, major_tags=["shared", "content"], session=session
        )

    # Search should find flows from both users
    response = await user_client.get("/api/flows/search?query=shared")
    assert response.status_code == 200
    response_data = response.json()

    flows = response_data["items"]
    flow_ids = {flow["id"] for flow in flows}

    assert flow1.id in flow_ids
    assert flow2.id in flow_ids

    # Verify creator information is included correctly
    for flow in flows:
        creator = flow["created_by"]
        assert creator["id"] in {user.id, another_user.id}
        if creator["id"] == user.id:
            assert creator["username"] == user.username
        else:
            assert creator["username"] == another_user.username


async def test_search_flows_with_flow_elements(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    """Test that search works correctly for flows with elements"""
    async with session.begin():
        flow = await FlowFactory.create(
            created_by=user,
            major_tags=["algorithms"],
            minor_tags=["sorting"],
            session=session,
        )

        # Add some flow questions to the flow
        await FlowQuestionFactory.create_batch(3, flow=flow, session=session)

    response = await user_client.get("/api/flows/search?query=algorithms")
    assert response.status_code == 200
    response_data = response.json()

    found_flow = response_data["items"][0]

    # Verify the flow data includes elements information
    assert found_flow["id"] == flow.id
    assert "elements" in found_flow
    assert "num_total_elements" in found_flow
    assert found_flow["num_total_elements"] == 3
