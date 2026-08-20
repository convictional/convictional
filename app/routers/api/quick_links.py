from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl, ValidationError

from app.models.accounts import User
from app.models.commands import QuickLink
from app.routers.dependencies import get_current_user

router = APIRouter(tags=["quick links"])


class QuickLinkRequest(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    open_in_new_tab: bool = False


class QuickLinkResponse(BaseModel):
    id: str
    label: str
    url: str
    open_in_new_tab: bool


def _validate_url(raw: str) -> str:
    try:
        return str(HttpUrl(raw.strip()))
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Please provide a valid HTTP or HTTPS URL.",
        ) from exc


def _response(quick_link: QuickLink) -> QuickLinkResponse:
    return QuickLinkResponse(
        id=str(quick_link.id),
        label=quick_link.label,
        url=quick_link.url or "",
        open_in_new_tab=quick_link.open_in_new_tab,
    )


async def get_owned_quick_link(
    quick_link_id: UUID,
    current_user: User = Depends(get_current_user),
) -> QuickLink:
    quick_link = await QuickLink.get_or_none(
        QuickLink.filters.by_owner(current_user.id) & QuickLink.filters.by_id(quick_link_id)
    )
    if not quick_link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return quick_link


@router.post("/quick_links", response_model=QuickLinkResponse, status_code=status.HTTP_201_CREATED)
async def api_quick_links_create(
    payload: QuickLinkRequest,
    current_user: User = Depends(get_current_user),
) -> QuickLinkResponse:
    quick_link = await QuickLink.create(
        label=payload.label.strip(),
        url=_validate_url(payload.url),
        open_in_new_tab=payload.open_in_new_tab,
        owner_id=current_user.id,
    )
    return _response(quick_link)


@router.get("/quick_links/{quick_link_id}", response_model=QuickLinkResponse)
async def api_quick_links_show(
    quick_link: QuickLink = Depends(get_owned_quick_link),
) -> QuickLinkResponse:
    return _response(quick_link)


@router.patch("/quick_links/{quick_link_id}", response_model=QuickLinkResponse)
async def api_quick_links_update(
    payload: QuickLinkRequest,
    quick_link: QuickLink = Depends(get_owned_quick_link),
) -> QuickLinkResponse:
    quick_link.label = payload.label.strip()
    quick_link.url = _validate_url(payload.url)
    quick_link.open_in_new_tab = payload.open_in_new_tab
    await quick_link.save(update_fields=["label", "url", "open_in_new_tab"])
    return _response(quick_link)


@router.delete("/quick_links/{quick_link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_quick_links_delete(
    quick_link: QuickLink = Depends(get_owned_quick_link),
) -> None:
    await quick_link.delete()
