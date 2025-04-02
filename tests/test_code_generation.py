import random

import pytest
from sqlalchemy import Integer, String, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.shared.code_generation import (
    CouldNotGenerateUniqueCodeError,
    HasCode,
)


# Create a separate base class for test-only models
class BaseTest(DeclarativeBase):
    """Base class for test-only models that shouldn't be part of main metadata."""

    pass


# Use TestBase instead of Base
class ModelTest(BaseTest, HasCode):
    """Test model that uses HasCode mixin but is only used in tests."""

    __tablename__ = "test_code_model"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


# Create a fixture to set up and tear down the test table
@pytest.fixture
async def setup_test_table(session: AsyncSession):
    """Create the test table before tests and drop it after."""
    # Create the table directly
    async with session.begin():
        await session.execute(
            text("""
        CREATE TABLE IF NOT EXISTS test_code_model (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50),
            code VARCHAR(10) UNIQUE
        )
        """)
        )

    # Run the tests
    yield

    # Clean up - drop the table after tests
    async with session.begin():
        await session.execute(text("DROP TABLE IF EXISTS test_code_model"))


@pytest.mark.usefixtures("setup_test_table")
class TestCodeGeneration:
    """Tests for the code generation functionality."""

    async def test_code_is_generated_automatically(self, session: AsyncSession):
        """Test that a code is automatically generated when a model is created."""
        # Create a new model instance without specifying a code
        async with session.begin():
            model = ModelTest(name="Test Model")
            session.add(model)

        # Verify that a code was generated
        assert model.code is not None
        assert len(model.code) == 5
        assert model.code.isalnum()

    async def test_custom_code_is_preserved(self, session: AsyncSession):
        """Test that a custom code is preserved when specified."""
        custom_code = "ABC12"
        async with session.begin():
            model = ModelTest(name="Test Model", code=custom_code)
            session.add(model)

        # Verify that the custom code was preserved
        assert model.code == custom_code

    async def test_code_uniqueness(self, session: AsyncSession):
        """Test that generated codes are unique."""
        # Create multiple models
        models: list[ModelTest] = []
        async with session.begin():
            for i in range(10):
                model = ModelTest(name=f"Test Model {i}")
                session.add(model)
                models.append(model)

        # Verify that all codes are unique
        codes: list[str] = [model.code for model in models]
        assert len(codes) == len(set(codes))  # No duplicates

    async def test_code_format(self, session: AsyncSession):
        """Test that generated codes follow the expected format."""
        async with session.begin():
            model = ModelTest(name="Test Model")
            session.add(model)

        # Verify code format
        assert len(model.code) == 5
        assert model.code.isalnum()

        # Verify that the code doesn't contain confusing characters (I, O, Q, 0, 1)
        assert "I" not in model.code
        assert "O" not in model.code
        assert "Q" not in model.code
        assert "0" not in model.code
        assert "1" not in model.code

    async def test_max_attempts_exceeded(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that an exception is raised when max attempts are exceeded."""
        # Create a model with a known code first
        async with session.begin():
            model = ModelTest(name="Test Model", code="ABC12")
            session.add(model)

        # Mock random.choice to always return characters that form "ABC12"
        # This way the retry logic is still tested, not bypassed
        choice_sequence = ["A", "B", "C", "1", "2"]
        choice_index = 0

        def mock_choice(population: list[str]) -> str:
            nonlocal choice_index
            result = choice_sequence[choice_index % 5]
            choice_index += 1
            return result

        # Use context manager to automatically restore the original method after the test
        with monkeypatch.context() as m:
            m.setattr(random, "choice", mock_choice)

            # Attempt to create a new model, which should fail after MAX_ATTEMPTS
            with pytest.raises(CouldNotGenerateUniqueCodeError):
                async with session.begin():
                    new_model = ModelTest(name="Another Test Model")
                    session.add(new_model)

    async def test_code_lookup(self, session: AsyncSession):
        """Test that models can be looked up by their code."""
        # Create a model with a specific code
        async with session.begin():
            model = ModelTest(name="Test Model", code="XYZ89")
            session.add(model)

        # Look up the model by code
        async with session.begin():
            result = await session.execute(
                select(ModelTest).where(ModelTest.code == "XYZ89")
            )
            found_model = result.scalars().first()

        assert found_model is not None
        assert found_model.id == model.id
        assert found_model.name == "Test Model"
