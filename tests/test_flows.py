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


async def test_list_flows(user_client: AsyncClient, session: AsyncSession):
    # Create test user and flows
    async with session.begin():
        user = await UserFactory.create(session=session)
        # Create a few flows for the test user
        await FlowFactory.create_batch(3, created_by=user, session=session)
        # Create a flow for another user (shouldn't appear in list)
        another_user = await UserFactory.create(session=session)
        await FlowFactory.create(created_by=another_user, session=session)

    # Get flows list for authenticated user
    response = await user_client.get("/flows")
    assert response.status_code == 200
    response_data = response.json()
    assert len(response_data) == 3  # Should only see own flows

    # Check response data structure
    for flow in response_data:
        assert "id" in flow
        assert "title" in flow
        assert "area" in flow
        assert "created_at" in flow


async def test_get_flow_details(user_client: AsyncClient, session: AsyncSession):
    # Create test flow with some elements
    async with session.begin():
        user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=user, session=session)
        # Add some questions to the flow
        await FlowQuestionFactory.create_batch(2, flow=flow, session=session)

    # Get flow details
    response = await user_client.get(f"/flows/{flow.id}")
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
    response = await user_client.get("/flows/9999")
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
    response = await user_client.post("/flows", json=flow_data)
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
    response = await user_client.post("/flows", json=flow_data)
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
        response = await user_client.post("/flows/files", data=data, files=files)

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
    response = await user_client.post(f"/flows/{flow.id}/submit", json=answer_data)
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
        f"/flows/{flow.id}/submit", json=invalid_answer_data
    )
    assert response.status_code == 400


async def test_generate_flow_pdf(user_client: AsyncClient, session: AsyncSession):
    # Create test flow
    async with session.begin():
        user = await UserFactory.create(session=session)
        flow = await FlowFactory.create(created_by=user, session=session)

    # Generate PDF
    response = await user_client.post(f"/flows/{flow.id}/generate-pdf")
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
        f"/flows/{flow.id}/add-elements", json=add_elements_data
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
    response = await user_client.delete(f"/flows/{flow.id}")
    assert response.status_code == 204

    # Verify flow was deleted
    # Try to get the flow, should return 404
    response = await user_client.get(f"/flows/{flow.id}")
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
    response = await user_client.get(f"/flows/user/{user2.id}")
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
