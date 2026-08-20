from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from app.models.accounts import Group, User
from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.posts import Post
from app.routers.api.schemas import GroupResponse, PostMailboxEntryResponse
from app.routers.api.streams import register_live_document_handler
from app.routers.dependencies import (
    create_post_indexer,
    get_all_org_groups,
    get_current_user,
    get_draft_post,
    get_mailbox_entry_for_resource,
)

router = APIRouter(dependencies=[Depends(create_post_indexer(), scope="function")], tags=["posts"])


class PostDraftShowResponse(BaseModel):
    id: str
    title: str
    group: GroupResponse | None
    is_announcement: bool
    can_announce: bool
    is_creator: bool
    can_delete: bool
    workspace_id: str
    org_groups: list[GroupResponse]
    # The editor re-sources these client-side (data-props is gone): the attachment
    # upload endpoint for the composer, and the mailbox entry when opened from the
    # inbox so the header renders its mailbox variant.
    upload_url: str
    mailbox_entry: PostMailboxEntryResponse | None


class PostDraftUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    group_id: UUID | None = None
    is_announcement: bool = False

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("at least one of title, group_id, is_announcement is required")
        return self


class PostDraftUpdateResponse(BaseModel):
    id: str
    title: str


@router.get("/posts/{post_id}/draft", response_model=PostDraftShowResponse)
async def api_post_drafts_show(
    request: Request,
    post: Post = Depends(get_draft_post),
    current_user: User = Depends(get_current_user),
    org_groups: list[Group] = Depends(get_all_org_groups),
    mailbox_entry: MailboxEntry | None = Depends(get_mailbox_entry_for_resource),
):
    org_group_responses = [GroupResponse(id=str(g.id), name=g.name) for g in org_groups]
    # The post's group is always one of the org's groups, so reuse the list we
    # already loaded instead of a second round-trip for its label.
    group = next((g for g in org_group_responses if g.id == str(post.group_id)), None) if post.group_id else None

    return PostDraftShowResponse(
        id=str(post.id),
        title=post.title,
        group=group,
        is_announcement=post.is_announcement,
        can_announce=current_user.is_admin,
        is_creator=post.creator_id == current_user.id,
        can_delete=post.deletable_by(current_user),
        workspace_id=str(post.workspace_id),
        org_groups=org_group_responses,
        upload_url=str(request.url_for("attachments_upload", workspace_id=post.workspace_id)),
        mailbox_entry=PostMailboxEntryResponse.from_entry(mailbox_entry) if mailbox_entry else None,
    )


@router.patch("/posts/{post_id}/draft", response_model=PostDraftUpdateResponse)
async def api_post_drafts_update(
    body: PostDraftUpdateRequest,
    post: Post = Depends(get_draft_post),
    current_user: User = Depends(get_current_user),
):
    if post.creator_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    # group_id and is_announcement are a coupled pair the picker always sends
    # together; title arrives on its own from the editor's debounced save. Apply
    # only the fields the client actually sent so a title save can't clobber the
    # group selection (and vice versa).
    fields_set = body.model_fields_set
    update_fields: list[str] = []

    if "title" in fields_set and body.title is not None:
        post.title = body.title
        update_fields.append("title")

    if "group_id" in fields_set or "is_announcement" in fields_set:
        is_announcement = body.is_announcement and current_user.is_admin
        group_id = None if is_announcement else body.group_id
        if group_id is not None:
            # Without this, a cross-org group_id would silently re-parent the draft
            # into a foreign org's collaborator graph via the post-save signal
            # (mirrors the guard in api_posts_update).
            if not await Group.exists(id=group_id, organization_id=post.organization_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="group_id does not belong to this organization",
                )
        post.is_announcement = is_announcement
        post.group_id = group_id
        update_fields += ["is_announcement", "group_id"]

    # A body like {"title": null} clears no fields; skip the write so we don't fire
    # a full-row UPDATE (and the post-save signal) for a no-op (Tortoise treats an
    # empty update_fields list as "update every column").
    if update_fields:
        await post.save(update_fields=update_fields)

    return PostDraftUpdateResponse(id=str(post.id), title=post.title)


# Handle this surface's live-document (Yjs) broadcasts.
register_live_document_handler("post_draft")
