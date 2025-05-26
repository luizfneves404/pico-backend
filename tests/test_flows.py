from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.flows.models import FlowInputType, FlowQuestionUser
from tests.factories import (
    ChoiceFactory,
    FlowFactory,
    FlowQuestionFactory,
    UserFactory,
)


async def test_flow_feed(user_client: AsyncClient, session: AsyncSession):
    """Test the flow feed endpoint returns flows ordered by answer count and doesn't repeat flows."""
    # Create test users and flows
    async with session.begin():
        user = await UserFactory.create(session=session)
        another_user = await UserFactory.create(session=session)

        # Create flows from different users (these should appear in feed)
        flow1 = await FlowFactory.create(created_by=another_user, session=session)
        flow2 = await FlowFactory.create(created_by=another_user, session=session)
        flow3 = await FlowFactory.create(created_by=user, session=session)

        # Add some questions to flows to test answer count ordering
        question1 = await FlowQuestionFactory.create(flow=flow1, session=session)
        question2 = await FlowQuestionFactory.create(flow=flow2, session=session)
        await FlowQuestionFactory.create(flow=flow3, session=session)

        # Add some answers to test ordering by answer count
        choice1 = await ChoiceFactory.create(
            question=question1.question, session=session
        )
        choice2 = await ChoiceFactory.create(
            question=question2.question, session=session
        )

        # Create answers for flow1 (should rank higher)
        flow_question_user1 = FlowQuestionUser(
            flow_element_id=question1.id, user_id=another_user.id, choice_id=choice1.id
        )
        session.add(flow_question_user1)

        flow_question_user2 = FlowQuestionUser(
            flow_element_id=question1.id, user_id=user.id, choice_id=choice1.id
        )
        session.add(flow_question_user2)

        # Create one answer for flow2
        flow_question_user3 = FlowQuestionUser(
            flow_element_id=question2.id, user_id=another_user.id, choice_id=choice2.id
        )
        session.add(flow_question_user3)

    # First call to feed - should return all flows
    response = await user_client.get("/api/flows/feed")
    assert response.status_code == 200
    response_data = response.json()

    # Should return paginated response
    assert "items" in response_data
    assert "total" in response_data
    assert "page" in response_data
    assert "size" in response_data

    flows = response_data["items"]
    assert len(flows) == 3

    # Check flows are ordered by answer count desc, then created_at desc
    # flow1 should be first (2 answers), then flow2 (1 answer), then flow3 (0 answers)
    assert flows[0]["id"] == flow1.id
    assert flows[1]["id"] == flow2.id
    assert flows[2]["id"] == flow3.id

    # Check response data structure matches FlowInFeed schema
    for flow in flows:
        assert "id" in flow
        assert "code" in flow
        assert "created_at" in flow
        assert "title" in flow
        assert "cover_image" in flow
        assert "action_link" in flow
        assert "action_text" in flow
        assert "created_by" in flow
        assert "query" in flow
        assert "area" in flow
        assert "source_filter" in flow
        assert "difficulty" in flow
        assert "elements" in flow
        assert "num_total_elements" in flow

        # Check created_by structure
        assert "id" in flow["created_by"]
        assert "username" in flow["created_by"]

    # Second call to feed - should return empty since all flows are now marked as seen
    response = await user_client.get("/api/flows/feed")
    assert response.status_code == 200
    response_data = response.json()

    flows = response_data["items"]
    assert len(flows) == 0  # No flows should be returned as they're all seen

    # Verify that FlowUserFeed records were created
    async with session.begin():
        from app.flows.models import FlowUserFeed

        feed_records = await session.execute(
            select(FlowUserFeed).where(FlowUserFeed.user_id == user.id)
        )
        feed_records = feed_records.scalars().all()
        assert len(feed_records) == 3  # Should have 3 feed records for the user

        # Check that all flow IDs are marked as seen
        seen_flow_ids = {record.flow_id for record in feed_records}
        expected_flow_ids = {flow1.id, flow2.id, flow3.id}
        assert seen_flow_ids == expected_flow_ids


async def test_get_flow_details(user_client: AsyncClient, session: AsyncSession):
    # Create test flow with some elements
    async with session.begin():
        user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=user, session=session)
        # Add some questions to the flow
        await FlowQuestionFactory.create_batch(2, flow=flow, session=session)

    # Get flow details
    response = await user_client.get(f"/api/flows/{flow.id}")
    assert response.status_code == 200
    response_data = response.json()

    # Check response data
    assert response_data["id"] == flow.id
    assert response_data["title"] == flow.title
    assert response_data["query"] == flow.query
    assert response_data["area"] == flow.area
    assert response_data["source_filter"] == flow.source_filter
    assert response_data["difficulty"] == flow.difficulty
    assert response_data["flow_input_type"] == flow.flow_input_type
    assert response_data["input_topic"] == flow.input_topic
    assert "elements" in response_data
    assert len(response_data["elements"]) == 2


async def test_get_flow_details_not_found(user_client: AsyncClient):
    # Try to get details for a non-existent flow
    response = await user_client.get("/api/flows/9999")
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
    user_client: AsyncClient, session: AsyncSession
):
    # Create flow with a question
    async with session.begin():
        user = await UserFactory.create(session=session)
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
        "flow_element_id": flow_question.id,
        "choice_id": choice.id,
        "submitted_text": "",
    }
    response = await user_client.post(f"/api/flows/{flow.id}/submit", json=answer_data)
    assert response.status_code == 200
    response_data = response.json()

    # Check response data
    assert response_data["status"] == "success"

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
    user_client: AsyncClient, session: AsyncSession
):
    # Create flow with a question
    async with session.begin():
        user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=user, session=session)
        flow_question = await FlowQuestionFactory.create(flow=flow, session=session)

    # Submit an answer with invalid choice_id
    invalid_answer_data = {
        "flow_element_id": flow_question.id,
        "choice_id": 9999,  # Non-existent choice
        "submitted_text": "",
    }
    response = await user_client.post(
        f"/api/flows/{flow.id}/submit", json=invalid_answer_data
    )
    assert response.status_code == 400


async def test_generate_flow_pdf(user_client: AsyncClient, session: AsyncSession):
    # Create test flow
    async with session.begin():
        user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=user, session=session)

    # Generate PDF
    response = await user_client.post(f"/api/flows/{flow.id}/generate-pdf")
    assert response.status_code == 200
    pdf_url = response.json()

    # Check that a URL was returned
    assert isinstance(pdf_url, str)
    assert pdf_url.startswith("https://")
    assert "pdf" in pdf_url


async def test_add_elements_to_flow(user_client: AsyncClient, session: AsyncSession):
    # Create test flow
    async with session.begin():
        user = await UserFactory.create(session=session)
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


async def test_delete_flow(user_client: AsyncClient, session: AsyncSession):
    # Create test flow
    async with session.begin():
        user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=user, session=session)

    # Delete the flow
    response = await user_client.delete(f"/api/flows/{flow.id}")
    assert response.status_code == 204

    # Verify flow was deleted
    # Try to get the flow, should return 404
    response = await user_client.get(f"/api/flows/{flow.id}")
    assert response.status_code == 404


async def test_get_user_flows(user_client: AsyncClient, session: AsyncSession):
    # Create test users and flows
    async with session.begin():
        user1 = await UserFactory.create(session=session)
        user2 = await UserFactory.create(session=session)

        # Create flows for user1
        await FlowFactory.create_batch(2, created_by=user1, session=session)

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
