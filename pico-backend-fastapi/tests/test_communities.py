import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.community.models import CommunityUser
from app.users.models import User
from tests.factories import CommunityFactory, CountryFactory, UserFactory


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

            with pytest.raises(IntegrityError) as e:
                await session.flush()
            assert (
                "unique" in str(e.value).lower() or "duplicate" in str(e.value).lower()
            )

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
        assert len(community_data["users"]) == 1
        assert community_data["users"][0]["id"] == user.id
        assert community_data["users"][0]["username"] == user.username
        assert community_data["users"][0]["online_info"]["is_online"] is False
        assert community_data["users"][0]["online_info"]["last_online"] is None


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
            country = await CountryFactory.create(session=session)
            users = await UserFactory.create_batch(
                size=50, session=session, country=country
            )

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


class TestCommunityRankingAPI:
    """Test community ranking API endpoints."""

    async def test_get_community_ranking_xp_score(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test getting community ranking with XP scores."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

            # Create users with different XP scores
            user_high = await UserFactory.create(
                session=session, xp_score=1000, username="highxp"
            )
            user_mid = await UserFactory.create(
                session=session, xp_score=500, username="midxp"
            )
            user_low = await UserFactory.create(
                session=session, xp_score=100, username="lowxp"
            )

            # Add all users to the community
            community_users = [
                CommunityUser(community_id=community.id, user_id=user.id),
                CommunityUser(community_id=community.id, user_id=user_high.id),
                CommunityUser(community_id=community.id, user_id=user_mid.id),
                CommunityUser(community_id=community.id, user_id=user_low.id),
            ]
            for cu in community_users:
                session.add(cu)
            await session.flush()

        response = await user_client.get(
            f"/api/community/{community.id}/ranking?score_type=xp"
        )
        assert response.status_code == 200

        ranking = response.json()
        assert len(ranking) == 4

        # Verify ranking order (highest to lowest)
        assert ranking[0]["id"] == user_high.id
        assert ranking[0]["score"] == 1000
        assert ranking[0]["rank"] == 1
        assert ranking[0]["username"] == "highxp"

        assert ranking[1]["id"] == user_mid.id
        assert ranking[1]["score"] == 500
        assert ranking[1]["rank"] == 2

        assert ranking[2]["id"] == user_low.id
        assert ranking[2]["score"] == 100
        assert ranking[2]["rank"] == 3

        # Original user should be last with 0 score
        assert ranking[3]["id"] == user.id
        assert ranking[3]["score"] == 0
        assert ranking[3]["rank"] == 4

    async def test_get_community_ranking_social_score(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test getting community ranking with social scores."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

            # Create users with different social scores
            user_social_high = await UserFactory.create(
                session=session, social_score=800, username="highsocial"
            )
            user_social_mid = await UserFactory.create(
                session=session, social_score=400, username="midsocial"
            )

            # Add users to community
            community_users = [
                CommunityUser(community_id=community.id, user_id=user.id),
                CommunityUser(community_id=community.id, user_id=user_social_high.id),
                CommunityUser(community_id=community.id, user_id=user_social_mid.id),
            ]
            for cu in community_users:
                session.add(cu)
            await session.flush()

        response = await user_client.get(
            f"/api/community/{community.id}/ranking?score_type=social"
        )
        assert response.status_code == 200

        ranking = response.json()
        assert len(ranking) == 3

        # Verify ranking order for social scores
        assert ranking[0]["id"] == user_social_high.id
        assert ranking[0]["score"] == 800
        assert ranking[0]["rank"] == 1

        assert ranking[1]["id"] == user_social_mid.id
        assert ranking[1]["score"] == 400
        assert ranking[1]["rank"] == 2

        assert ranking[2]["id"] == user.id
        assert ranking[2]["score"] == 0
        assert ranking[2]["rank"] == 3

    async def test_get_community_ranking_asking_user_included_outside_top_10(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test that asking user is included in ranking even if outside top 10."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)
            country = await CountryFactory.create(session=session)

            # Create 12 users with higher XP scores than the asking user, different xp
            # scores
            high_score_users = [
                await UserFactory.create(
                    session=session,
                    xp_score=1000 * i,
                    country=country,
                )
                for i in range(1, 13)
            ]

            # Add all users to community
            community_users = [
                CommunityUser(community_id=community.id, user_id=user.id),
                *[
                    CommunityUser(community_id=community.id, user_id=high_user.id)
                    for high_user in high_score_users
                ],
            ]

            for cu in community_users:
                session.add(cu)
            await session.flush()

        response = await user_client.get(
            f"/api/community/{community.id}/ranking?score_type=xp"
        )
        assert response.status_code == 200

        ranking = response.json()
        # Should include top 10 + asking user (who is rank 13)
        assert len(ranking) == 11

        # First 10 should be the high scorers
        for i in range(10):
            assert ranking[i]["score"] == (12000 - 1000 * i)  # 12000, 11000, 10000, ...
            assert ranking[i]["rank"] == i + 1

        # Last entry should be the asking user
        assert ranking[10]["id"] == user.id
        assert ranking[10]["score"] == 0
        assert ranking[10]["rank"] == 13  # Rank 13

    async def test_get_community_ranking_with_tied_scores(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test ranking behavior with tied scores."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

            # Create users with tied scores
            user_tied1 = await UserFactory.create(
                session=session, xp_score=500, username="tied1"
            )
            user_tied2 = await UserFactory.create(
                session=session, xp_score=500, username="tied2"
            )
            user_unique = await UserFactory.create(
                session=session, xp_score=300, username="unique"
            )

            # Add users to community
            community_users = [
                CommunityUser(community_id=community.id, user_id=user.id),
                CommunityUser(community_id=community.id, user_id=user_tied1.id),
                CommunityUser(community_id=community.id, user_id=user_tied2.id),
                CommunityUser(community_id=community.id, user_id=user_unique.id),
            ]
            for cu in community_users:
                session.add(cu)
            await session.flush()

        response = await user_client.get(
            f"/api/community/{community.id}/ranking?score_type=xp"
        )
        assert response.status_code == 200

        ranking = response.json()
        assert len(ranking) == 4

        # Both tied users should have rank 1
        tied_users = [r for r in ranking if r["score"] == 500]
        assert len(tied_users) == 2
        for tied_user in tied_users:
            assert tied_user["rank"] == 1

        # User with 300 score should have rank 2
        unique_user = next(r for r in ranking if r["score"] == 300)
        assert unique_user["rank"] == 2

    async def test_get_community_ranking_nonexistent_community(
        self, user_client: AsyncClient
    ):
        """Test getting ranking for non-existent community."""
        response = await user_client.get("/api/community/99999/ranking?score_type=xp")
        assert response.status_code == 200
        ranking = response.json()
        assert ranking == []

    async def test_get_community_ranking_invalid_score_type(
        self, user_client: AsyncClient, session: AsyncSession
    ):
        """Test ranking with invalid score type."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

        response = await user_client.get(
            f"/api/community/{community.id}/ranking?score_type=invalid"
        )
        assert response.status_code == 422

    async def test_get_community_ranking_missing_score_type(
        self, user_client: AsyncClient, session: AsyncSession
    ):
        """Test ranking without score_type parameter."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

        response = await user_client.get(f"/api/community/{community.id}/ranking")
        assert response.status_code == 422

    async def test_get_community_ranking_authorization_required(
        self, client: AsyncClient, session: AsyncSession
    ):
        """Test that authorization is required for community ranking endpoint."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

        response = await client.get(
            f"/api/community/{community.id}/ranking?score_type=xp"
        )
        assert response.status_code == 401

    async def test_get_community_ranking_empty_community(
        self, user_client: AsyncClient, session: AsyncSession
    ):
        """Test ranking for community with no users."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)

        response = await user_client.get(
            f"/api/community/{community.id}/ranking?score_type=xp"
        )
        assert response.status_code == 200
        ranking = response.json()

        assert len(ranking) == 0

    async def test_get_community_ranking_response_schema(
        self, user_client: AsyncClient, user: User, session: AsyncSession
    ):
        """Test that ranking response matches expected schema."""
        async with session.begin():
            community = await CommunityFactory.create(session=session)
            community_user = CommunityUser(community_id=community.id, user_id=user.id)
            session.add(community_user)
            await session.flush()

        response = await user_client.get(
            f"/api/community/{community.id}/ranking?score_type=xp"
        )
        assert response.status_code == 200
        ranking = response.json()

        assert len(ranking) == 1
        user_rank = ranking[0]

        # Verify all required fields are present and correct types
        assert isinstance(user_rank["id"], int)
        assert isinstance(user_rank["username"], str)
        assert isinstance(user_rank["rank"], int)
        assert isinstance(user_rank["score"], int)
        assert user_rank["id"] == user.id
        assert user_rank["username"] == user.username
        assert user_rank["rank"] == 1
        assert user_rank["score"] == 0
