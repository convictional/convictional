from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status

from app.models.workspaces.email.contact import EmailContact
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_email_contacts_search(client: AppClient):
    """Test the email contacts search endpoint"""
    user = await create_user()

    with client.current_user_as(user):
        # Test empty state
        response = await client.get("/api/email_contacts?query=test")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {"contacts": [], "has_more": False, "next_cursor": None}

        # Create test contacts
        await EmailContact.create(
            email="john.doe@example.com",
            name="John Doe",
            user_id=user.id,
            organization_id=user.organization_id,
        )
        await EmailContact.create(
            email="jane.smith@example.com",
            name="Jane Smith",
            user_id=user.id,
            organization_id=user.organization_id,
        )

        # Test search by name
        response = await client.get("/api/email_contacts?query=john")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["email"] == "john.doe@example.com"
        assert data["contacts"][0]["name"] == "John Doe"

        # Test search by email
        response = await client.get("/api/email_contacts?query=jane.smith")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["email"] == "jane.smith@example.com"


@pytest.mark.asyncio
async def test_email_contacts_search_user_isolation(client: AppClient):
    """Test that users can only see their own contacts"""
    user1 = await create_user()
    user2 = await create_user()

    # Create contacts for each user
    await EmailContact.create(
        email="user1@example.com",
        name="User One",
        user_id=user1.id,
        organization_id=user1.organization_id,
    )
    await EmailContact.create(
        email="user2@example.com",
        name="User Two",
        user_id=user2.id,
        organization_id=user2.organization_id,
    )

    # Test user1 can only see their contacts
    with client.current_user_as(user1):
        response = await client.get("/api/email_contacts?query=user")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["email"] == "user1@example.com"

    # Test user2 can only see their contacts
    with client.current_user_as(user2):
        response = await client.get("/api/email_contacts?query=user")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["contacts"]) == 1
        assert data["contacts"][0]["email"] == "user2@example.com"


@pytest.mark.asyncio
async def test_email_contacts_search_ordered_by_recency(client: AppClient):
    """Test that search results are ordered by interaction recency"""
    user = await create_user()

    recent_contact = await EmailContact.create(
        email="recent@example.com",
        name="Recent Contact",
        user_id=user.id,
        organization_id=user.organization_id,
    )
    recent_contact.last_interacted_at = datetime.now(UTC)
    await recent_contact.save(update_fields=["last_interacted_at"])

    old_contact = await EmailContact.create(
        email="old@example.com",
        name="Old Contact",
        user_id=user.id,
        organization_id=user.organization_id,
    )
    old_contact.last_interacted_at = datetime.now(UTC) - timedelta(days=30)
    await old_contact.save(update_fields=["last_interacted_at"])

    very_old_contact = await EmailContact.create(
        email="veryold@example.com",
        name="Very Old Contact",
        user_id=user.id,
        organization_id=user.organization_id,
    )
    very_old_contact.last_interacted_at = datetime.now(UTC) - timedelta(days=60)
    await very_old_contact.save(update_fields=["last_interacted_at"])

    with client.current_user_as(user):
        response = await client.get("/api/email_contacts?query=contact")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["contacts"]) == 3

        emails = [c["email"] for c in data["contacts"]]
        assert emails[0] == "recent@example.com"
        assert emails[1] == "old@example.com"
        assert emails[2] == "veryold@example.com"


@pytest.mark.asyncio
async def test_email_contacts_search_prioritizes_interacted_over_null(client: AppClient):
    """Test that contacts with last_interacted_at are prioritized over those with NULL"""
    user = await create_user()

    await EmailContact.create(
        email="never@example.com",
        name="Never Interacted",
        user_id=user.id,
        organization_id=user.organization_id,
        last_interacted_at=None,
    )

    interacted_contact = await EmailContact.create(
        email="interacted@example.com",
        name="Interacted Once",
        user_id=user.id,
        organization_id=user.organization_id,
    )
    interacted_contact.last_interacted_at = datetime.now(UTC) - timedelta(days=365)
    await interacted_contact.save(update_fields=["last_interacted_at"])

    with client.current_user_as(user):
        response = await client.get("/api/email_contacts?query=interacted")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["contacts"]) == 2

        emails = [c["email"] for c in data["contacts"]]
        assert emails[0] == "interacted@example.com"
        assert emails[1] == "never@example.com"
