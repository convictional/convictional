from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from tortoise.functions import Coalesce

from app.models.accounts import User
from app.models.workspaces.email.contact import EmailContact
from app.routers.api.schemas import PaginatedResponse
from app.routers.dependencies import get_current_user

router = APIRouter(tags=["inbox"])

MIN_SEARCH_TERM_LENGTH = 2


class EmailContactResponse(BaseModel):
    id: str
    email: str
    name: str | None
    photo_url: str | None


class EmailContactListResponse(PaginatedResponse):
    contacts: list[EmailContactResponse]


@router.get("/email_contacts", response_model=EmailContactListResponse)
async def api_email_contacts_list(
    query: str = Query(..., max_length=200, description="Search term for email contacts"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results to return"),
    current_user: User = Depends(get_current_user),
) -> EmailContactListResponse:
    search_term = query.strip()
    if len(search_term) < MIN_SEARCH_TERM_LENGTH:
        return EmailContactListResponse(contacts=[])

    contacts = (
        await EmailContact.filter(EmailContact.filters.search(search_term, current_user.id))
        .annotate(sort_date=Coalesce("last_interacted_at", datetime.min.replace(tzinfo=UTC)))
        .order_by("-sort_date", "name", "email")
        .limit(limit)
    )

    return EmailContactListResponse(
        contacts=[
            EmailContactResponse(
                id=str(contact.id),
                email=contact.email,
                name=contact.name,
                photo_url=contact.photo_url,
            )
            for contact in contacts
        ]
    )
