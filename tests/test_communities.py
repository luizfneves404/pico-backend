from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.community.models import CommunityUser
from app.community.schemas import CommunityOut
from app.users.models import User
from tests.factories import CommunityFactory, UserFactory


class TestCommunityCreation:
    """Test community creation operations."""

    async def test_create_community_via_factory(self, session: AsyncSession):
        """Test creating a community using the factory."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

        assert community.id is not None
        assert community.name.startswith("Community")
        assert community.subtitle.startswith("Join Community")
        assert community.created_at is not None

    async def test_create_multiple_communities(self, session: AsyncSession):
        """Test creating multiple communities."""
        async with session.begin():
            communities = await CommunityFactory.create_batch(size=5, session=session)

        assert len(communities) == 5
        community_names = [c.name for c in communities]
        assert len(set(community_names)) == 5  # All names should be unique

        for community in communities:
            assert community.id is not None
            assert community.name.startswith("Community")
            assert community.subtitle.startswith("Join Community")

    async def test_create_community_with_custom_data(self, session: AsyncSession):
        """Test creating a community with custom name and subtitle."""
        async with session.begin():
            community = await CommunityFactory.create(
                session=session,
                name="Computer Science Students",
                subtitle="Connect with fellow CS students and share knowledge!",
            )

        assert community.name == "Computer Science Students"
        assert (
            community.subtitle == "Connect with fellow CS students and share knowledge!"
        )


class TestCommunityUserRelationships:
    """Test community and user relationship operations."""

    async def test_add_user_to_community(self, session: AsyncSession):
        """Test adding a user to a community."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)
            user = await UserFactory.create(session=session)

            # Add user to community
            community_user = CommunityUser(community_id=community.id, user_id=user.id)
            session.add(community_user)
            await session.flush()

        # Verify relationship exists
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(
                    CommunityUser.community_id == community.id,
                    CommunityUser.user_id == user.id,
                )
            )
            community_user_record = result.scalar_one()
            assert community_user_record is not None
            assert community_user_record.community_id == community.id
            assert community_user_record.user_id == user.id

    async def test_add_multiple_users_to_community(self, session: AsyncSession):
        """Test adding multiple users to a single community."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)
            users = await UserFactory.create_batch(size=3, session=session)

            # Add all users to community
            for user in users:
                community_user = CommunityUser(
                    community_id=community.id, user_id=user.id
                )
                session.add(community_user)
            await session.flush()

        # Verify all relationships exist
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(CommunityUser.community_id == community.id)
            )
            community_users = list(result.scalars())
            assert len(community_users) == 3

            user_ids = {cu.user_id for cu in community_users}
            expected_user_ids = {user.id for user in users}
            assert user_ids == expected_user_ids

    async def test_add_user_to_multiple_communities(self, session: AsyncSession):
        """Test adding a single user to multiple communities."""
        async with session.begin():
            user = await UserFactory.create(session=session)
            communities = await CommunityFactory.create_batch(size=3, session=session)

            # Add user to all communities
            for community in communities:
                community_user = CommunityUser(
                    community_id=community.id, user_id=user.id
                )
                session.add(community_user)
            await session.flush()

        # Verify all relationships exist
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(CommunityUser.user_id == user.id)
            )
            community_users = list(result.scalars().all())
            assert len(community_users) == 3

            community_ids = {cu.community_id for cu in community_users}
            expected_community_ids = {community.id for community in communities}
            assert community_ids == expected_community_ids

    async def test_duplicate_user_community_relationship(self, session: AsyncSession):
        """Test that duplicate relationships are prevented by unique constraint."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)
            user = await UserFactory.create(session=session)

            # Add user to community first time
            community_user1 = CommunityUser(community_id=community.id, user_id=user.id)
            session.add(community_user1)
            await session.flush()

            # Try to add the same relationship again
            community_user2 = CommunityUser(community_id=community.id, user_id=user.id)
            session.add(community_user2)

            try:
                await session.flush()
                assert False, "Should have raised an integrity error"
            except Exception as e:
                # Should fail due to unique constraint
                assert "unique" in str(e).lower() or "duplicate" in str(e).lower()

    async def test_remove_user_from_community(self, session: AsyncSession):
        """Test removing a user from a community."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)
            user = await UserFactory.create(session=session)

            # Add user to community
            community_user = CommunityUser(community_id=community.id, user_id=user.id)
            session.add(community_user)
            await session.flush()

        # Remove user from community
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(
                    CommunityUser.community_id == community.id,
                    CommunityUser.user_id == user.id,
                )
            )
            community_user_record = result.scalar_one()
            await session.delete(community_user_record)
            await session.flush()

        # Verify relationship no longer exists
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(
                    CommunityUser.community_id == community.id,
                    CommunityUser.user_id == user.id,
                )
            )
            community_user_record = result.scalar_one_or_none()
            assert community_user_record is None


class TestCommunityAPI:
    """Test community API endpoints."""

    async def test_get_my_communities_empty(self, user_client: AsyncClient):
        """Test getting communities when user has none."""
        response = await user_client.get("/api/community/me")
        assert response.status_code == 200
        communities = response.json()
        assert communities == []

    async def test_get_my_communities_with_communities(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test getting communities when user belongs to some."""
        async with session.begin():
            # Create communities
            communities = await CommunityFactory.create_batch(size=3, session=session)

            # Add user to two of the communities
            for community in communities[:2]:
                community_user = CommunityUser(
                    community_id=community.id, user_id=user.id
                )
                session.add(community_user)
            await session.flush()

        response = await user_client.get("/api/community/me")
        assert response.status_code == 200
        user_communities = response.json()

        assert len(user_communities) == 2
        community_ids = {c["id"] for c in user_communities}
        expected_ids = {communities[0].id, communities[1].id}
        assert community_ids == expected_ids

        # Verify response structure
        for community_data in user_communities:
            assert "id" in community_data
            assert "name" in community_data
            assert "subtitle" in community_data
            assert isinstance(community_data["id"], int)
            assert isinstance(community_data["name"], str)
            assert isinstance(community_data["subtitle"], str)

    async def test_get_my_communities_authorization_required(self, client: AsyncClient):
        """Test that authorization is required for the endpoint."""
        response = await client.get("/api/community/me")
        assert response.status_code == 401

    async def test_community_response_schema(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test that community response matches expected schema."""
        async with session.begin():
            community = await CommunityFactory.create(
                session=session,
                name="Test Community",
                subtitle="A test community for students",
            )

            community_user = CommunityUser(community_id=community.id, user_id=user.id)
            session.add(community_user)
            await session.flush()

        response = await user_client.get("/api/community/me")
        assert response.status_code == 200
        communities = response.json()

        assert len(communities) == 1
        community_data = communities[0]

        # Verify all required fields are present and correct
        assert community_data["id"] == community.id
        assert community_data["name"] == "Test Community"
        assert community_data["subtitle"] == "A test community for students"

        # Verify no extra fields are present
        expected_keys = {"id", "name", "subtitle"}
        actual_keys = set(community_data.keys())
        assert actual_keys == expected_keys


class TestCommunitySchemas:
    """Test community schema serialization."""

    async def test_community_out_from_orm_model(self, session: AsyncSession):
        """Test CommunityOut schema creation from ORM model."""
        async with session.begin():
            community = await CommunityFactory.create(
                session=session,
                name="Schema Test Community",
                subtitle="Testing schema conversion",
            )

        community_out = CommunityOut.from_orm_model(community)

        assert community_out.id == community.id
        assert community_out.name == "Schema Test Community"
        assert community_out.subtitle == "Testing schema conversion"

    async def test_community_out_serialization(self, session: AsyncSession):
        """Test CommunityOut schema JSON serialization."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

        community_out = CommunityOut.from_orm_model(community)
        community_dict = community_out.model_dump()

        assert "id" in community_dict
        assert "name" in community_dict
        assert "subtitle" in community_dict
        assert isinstance(community_dict["id"], int)
        assert isinstance(community_dict["name"], str)
        assert isinstance(community_dict["subtitle"], str)


class TestCommunityDeletion:
    """Test community deletion and cascade behavior."""

    async def test_delete_community_cascade_relationships(self, session: AsyncSession):
        """Test that deleting a community removes associated relationships."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)
            users = await UserFactory.create_batch(size=2, session=session)

            # Add users to community
            for user in users:
                community_user = CommunityUser(
                    community_id=community.id, user_id=user.id
                )
                session.add(community_user)
            await session.flush()

        # Verify relationships exist
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(CommunityUser.community_id == community.id)
            )
            community_users = list(result.scalars())
            assert len(community_users) == 2

        # Delete the community
        async with session.begin():
            await session.delete(community)
            await session.flush()

        # Verify relationships are gone (cascade delete)
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(CommunityUser.community_id == community.id)
            )
            community_users = list(result.scalars())
            assert len(community_users) == 0

        # Verify users still exist
        async with session.begin():
            for user in users:
                await session.refresh(user)
                assert user.id is not None

    async def test_delete_user_cascade_relationships(self, session: AsyncSession):
        """Test that deleting a user removes associated community relationships."""
        async with session.begin():
            communities = await CommunityFactory.create_batch(size=2, session=session)
            user = await UserFactory.create(session=session)

            # Add user to communities
            for community in communities:
                community_user = CommunityUser(
                    community_id=community.id, user_id=user.id
                )
                session.add(community_user)
            await session.flush()

        # Verify relationships exist
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(CommunityUser.user_id == user.id)
            )
            community_users = list(result.scalars().all())
            assert len(community_users) == 2

        # Delete the user
        async with session.begin():
            await session.delete(user)
            await session.flush()

        # Verify relationships are gone (cascade delete)
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(CommunityUser.user_id == user.id)
            )
            community_users = list(result.scalars().all())
            assert len(community_users) == 0

        # Verify communities still exist
        async with session.begin():
            for community in communities:
                await session.refresh(community)
                assert community.id is not None


class TestCommunityBoundaryConditions:
    """Test edge cases and boundary conditions."""

    async def test_community_with_long_names(self, session: AsyncSession):
        """Test communities with maximum length names and subtitles."""
        long_name = "A" * 255  # Maximum allowed length
        long_subtitle = "B" * 255  # Maximum allowed length

        async with session.begin():
            community = await CommunityFactory.create(
                session=session, name=long_name, subtitle=long_subtitle
            )

        assert community.name == long_name
        assert community.subtitle == long_subtitle
        assert len(community.name) == 255
        assert len(community.subtitle) == 255

    async def test_community_with_special_characters(self, session: AsyncSession):
        """Test communities with special characters in names."""
        special_name = "Comunidade José & María! 🎓📚"
        special_subtitle = "Bem-vindos à nossa comunidade! 👋 Join us @ example.com"

        async with session.begin():
            community = await CommunityFactory.create(
                session=session, name=special_name, subtitle=special_subtitle
            )

        assert community.name == special_name
        assert community.subtitle == special_subtitle

    async def test_large_community_membership(self, session: AsyncSession):
        """Test a community with many users."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)
            users = await UserFactory.create_batch(size=50, session=session)

            # Add all users to community
            for user in users:
                community_user = CommunityUser(
                    community_id=community.id, user_id=user.id
                )
                session.add(community_user)
            await session.flush()

        # Verify all relationships exist
        async with session.begin():
            result = await session.execute(
                select(CommunityUser).where(CommunityUser.community_id == community.id)
            )
            community_users = list(result.scalars())
            assert len(community_users) == 50
