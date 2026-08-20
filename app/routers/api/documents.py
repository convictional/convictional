from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from tortoise.functions import Coalesce, Max
from tortoise.query_utils import Prefetch
from tortoise.queryset import Q

from app.helpers.users import user_avatar_url
from app.models.accounts import User
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.workspace import ViewStateResolver
from app.models.workspaces.documents import Document, DocumentComment
from app.routers.api.schemas import PaginatedResponse, UserResponse
from app.routers.api.streams import register_live_document_handler
from app.routers.dependencies import get_current_user, get_document, index_document
from config.enums import DocumentFilter, Sharing
from infra.db import Pagination, transaction

router = APIRouter(dependencies=[Depends(index_document, scope="function")], tags=["documents"])


class DocumentListItemResponse(BaseModel):
    id: str
    title: str
    author_display_name: str
    last_viewed_at: datetime | None
    updated_at: datetime
    comment_count: int
    sharing: Sharing
    collaborator_count: int
    source_url: str


class DocumentListResponse(PaginatedResponse):
    documents: list[DocumentListItemResponse]


class DocumentShowResponse(BaseModel):
    id: str
    title: str
    sharing: Sharing
    creator: UserResponse
    updated_at: datetime
    workspace_id: str
    is_collaborator: bool
    is_creator: bool
    # First five approved collaborators, for the avatar group. The full list
    # is loaded on demand by the WorkspaceCollaborators island.
    collaborators: list[UserResponse]
    collaborator_count: int
    request_access_url: str
    upload_url: str


class DocumentContentResponse(BaseModel):
    # Live-document markdown rendering. Collaborators normally consume content
    # over the Yjs channel; this endpoint exists for the read-only show island
    # (non-collaborators) and any consumer that doesn't need CRDT sync.
    markdown: str


class DocumentCreateRequest(BaseModel):
    # Empty title is allowed (defaults to "Untitled document"); max_length mirrors
    # DocumentUpdateRequest so a title can't be created longer than it can be edited.
    title: str = Field(default="", max_length=1000)
    content: str = ""


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    sharing: Sharing | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("must set at least one field")
        return self


def _user_response(user: User) -> UserResponse:
    return UserResponse(id=str(user.id), display_name=user.display_name, picture=user_avatar_url(user))


def _make_show_response(document: Document, current_user: User, request: Request) -> DocumentShowResponse:
    collaborators = list(document.workspace.collaborators)
    return DocumentShowResponse(
        id=str(document.id),
        title=document.title,
        sharing=document.sharing,
        creator=_user_response(document.creator),
        updated_at=document.updated_at,
        workspace_id=str(document.workspace_id),
        is_collaborator=document.collaboration.is_collaborator(current_user),
        is_creator=document.creator_id == current_user.id,
        collaborators=[_user_response(c.user) for c in collaborators[:5]],
        collaborator_count=len(collaborators),
        request_access_url=str(
            request.url_for("workspace_collaborators_request_access", workspace_id=document.workspace_id)
        ),
        upload_url=str(request.url_for("attachments_upload", workspace_id=document.workspace_id)),
    )


async def _load_list_items(documents: list[Document], current_user_id: UUID) -> list[DocumentListItemResponse]:
    if not documents:
        return []

    view_states = await ViewStateResolver.for_user(current_user_id, [d.workspace_id for d in documents])

    items = []
    for document in documents:
        items.append(
            DocumentListItemResponse(
                id=str(document.id),
                title=document.title,
                author_display_name="Me" if document.creator_id == current_user_id else document.creator.display_name,
                last_viewed_at=view_states[document.workspace_id].last_viewed_at,
                updated_at=document.updated_at,
                comment_count=len(document.document_comments),
                sharing=document.sharing,
                collaborator_count=len(document.workspace.collaborators),
                source_url=f"/documents/{document.id}",
            )
        )
    return items


@router.get("/documents", response_model=DocumentListResponse)
async def api_documents_index(
    cursor: str | None = Query(None),
    document_filter: DocumentFilter = Query(DocumentFilter.MINE, alias="filter"),
    current_user: User = Depends(get_current_user),
):
    base_filter = Document.filters.by_organization(current_user.organization_id)
    match document_filter:
        case DocumentFilter.MINE:
            base_filter &= Document.filters.owned_by_me(current_user.id)
        case DocumentFilter.OTHERS:
            base_filter &= Document.filters.owned_by_others(current_user.id)
        case _:  # ANYONE — every document the user can access, regardless of owner
            base_filter &= Document.filters.available_to(current_user.id)

    last_viewed_by_me = Max(
        "workspace__visits__updated_at",
        _filter=Q(workspace__visits__user_id=current_user.id),
    )
    queryset = (
        Document.filter(base_filter)
        .prefetch_related(
            "workspace__collaborators",
            "creator",
            Prefetch("document_comments", queryset=DocumentComment.filter(resolved_at__isnull=True)),
        )
        .annotate(last_viewed_sort=Coalesce(last_viewed_by_me, datetime.min.replace(tzinfo=UTC)))
        .order_by("-last_viewed_sort", "-updated_at")
    )
    pagination = await Pagination.create(Document, cursor=cursor, queryset=queryset)
    items = await _load_list_items(pagination.results, current_user.id)

    return DocumentListResponse(
        documents=items,
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


@router.post("/documents", response_model=DocumentShowResponse, status_code=status.HTTP_201_CREATED)
async def api_documents_create(
    body: DocumentCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    async with transaction() as connection:
        document = Document(
            title=body.title.strip() or "Untitled document",
            organization_id=current_user.organization_id,
            creator_id=current_user.id,
            sharing=Sharing.PRIVATE,
        )
        await document.save(using_db=connection)

        if body.content.strip():
            await LiveDocument.set_initial_content(document.live_document_topic, body.content, using_db=connection)

    # Saving creates the workspace and adds the creator as a collaborator (post_save
    # signals); re-fetch the same relations get_document loads so the show response
    # reflects that fresh collaboration state.
    await document.fetch_related("workspace__collaborators__user__avatar_file", "creator")
    return _make_show_response(document, current_user, request)


@router.get("/documents/{document_id}", response_model=DocumentShowResponse)
async def api_documents_show(
    request: Request,
    document: Document = Depends(get_document),
    current_user: User = Depends(get_current_user),
):
    return _make_show_response(document, current_user, request)


@router.get("/documents/{document_id}/content", response_model=DocumentContentResponse)
async def api_documents_content(
    document: Document = Depends(get_document),
    _current_user: User = Depends(get_current_user),
):
    markdown = await document.get_live_document_markdown()
    return DocumentContentResponse(markdown=markdown)


@router.patch("/documents/{document_id}", response_model=DocumentShowResponse)
async def api_documents_update(
    body: DocumentUpdateRequest,
    request: Request,
    document: Document = Depends(get_document),
    current_user: User = Depends(get_current_user),
):
    if not document.collaboration.is_collaborator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    update_fields = []
    if body.title is not None:
        document.title = body.title
        update_fields.append("title")
    if body.sharing is not None:
        document.sharing = body.sharing
        update_fields.append("sharing")
    await document.save(update_fields=update_fields)

    return _make_show_response(document, current_user, request)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_documents_delete(
    document: Document = Depends(get_document),
    current_user: User = Depends(get_current_user),
):
    if document.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    await document.soft_delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Handle this surface's live-document (Yjs) broadcasts.
register_live_document_handler("document")
