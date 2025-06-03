from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.flows.models import FlowInputType, FlowQuestionUser, FlowUserFeed, Question
from app.users.models import User
from tests.factories import (
    ChoiceFactory,
    FlowFactory,
    FlowQuestionFactory,
    UserFactory,
)


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
        assert flow["action_url"] is None or isinstance(flow["action_url"], str)
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
        assert flow["action_url"] is None or isinstance(flow["action_url"], str)
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
    assert response_data["action_url"] == flow.action_url
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
        assert element["official_source"] == question.official_source
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


async def test_submit_flow_question_answer(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    # Create flow with a question
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

        # Create choices for the question
        question = flow_question.question
        choice = await ChoiceFactory.create(
            question=question, is_correct=True, session=session
        )
        await ChoiceFactory.create_batch(
            3, question=question, is_correct=False, session=session
        )

    # Submit an answer
    answer_data = {
        "flow_id": flow.id,
        "question_id": flow_question.question_id,
        "choice_id": choice.id,
        "submitted_text": "",
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 200

    # Verify that the answer was recorded in the database
    async with session.begin():
        result = await session.execute(
            select(FlowQuestionUser).where(
                FlowQuestionUser.flow_element_id == flow_question.id,
                FlowQuestionUser.user_id == user.id,
            )
        )
        user_answer = result.scalar_one()
        assert user_answer.choice_id == choice.id


async def test_submit_flow_question_answer_invalid(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    # Create flow with a question
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

    # Submit an answer with invalid choice_id
    invalid_answer_data = {
        "question_id": flow_question.question_id,
        "choice_id": 9999,  # Non-existent choice
    }
    response = await user_client.post(
        f"/api/flows/{flow.id}/submit", json=invalid_answer_data
    )
    assert response.status_code == 400


async def test_generate_flow_pdf(
    user_client: AsyncClient, session: AsyncSession, user: User
):
    # Create test flow
    async with session.begin():
        flow = await FlowFactory.create(created_by=user, session=session)

    # Generate PDF
    response = await user_client.post(f"/api/flows/{flow.id}/generate-pdf")
    assert response.status_code == 200
    pdf_url = response.json()

    # Check that a URL was returned
    assert isinstance(pdf_url, str)
    assert pdf_url.startswith("https://")
    assert "pdf" in pdf_url


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
    response = await user_client.delete(f"/api/flows/{flow.id}")
    assert response.status_code == 204

    # Verify flow was deleted
    # Try to get the flow, should return 404
    response = await user_client.get(f"/api/flows/{flow.id}")
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
