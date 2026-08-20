from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.helpers.url import back_navigation
from app.models.accounts import User
from app.models.workspaces.meetings import Meeting, MeetingCollection
from app.presenters.meeting import MeetingPresenter
from app.routers.dependencies import (
    Helpers,
    get_current_user,
    get_helpers,
    get_meeting,
    get_org_users,
    index_meeting,
)
from config.enums import MeetingCollectionFilter

#
# Dependencies
#
#


async def get_meeting_presenter(
    meeting: Meeting = Depends(get_meeting),
    current_user: User = Depends(get_current_user),
    org_users: list[User] = Depends(get_org_users),
):
    return await MeetingPresenter.create(meeting, current_user, org_users)


#
# Routes
#
#

router = APIRouter(tags=["meetings"], dependencies=[Depends(index_meeting, scope="function")])


@router.get("/meetings/upcoming")
async def meetings_upcoming(
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    return helpers.render(
        "meetings/upcoming.html.jinja",
        meetings_upcoming_index_props={
            "googleCalendarLoginUrl": str(
                helpers.url_for("integrations_google_calendar_login").include_query_params(
                    return_to=helpers.url_for("meetings_upcoming")
                )
            ),
        },
    )


# The single meeting list page. It renders three modes from the query string:
# Most Recent (default), Uncategorized (?filter=uncategorized) and a specific
# collection (?collection_id={id}). The collection-show page folds into this one
# — /meetings_collections/{id} redirects here with a collection_id.
@router.get("/meetings")
async def meetings_index(
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
    filter: MeetingCollectionFilter = Query(MeetingCollectionFilter.MOST_RECENT),
    collection_id: UUID | None = Query(None),
):
    collection = None
    if collection_id is not None:
        collection = await MeetingCollection.get_or_none(
            id=collection_id, organization_id=current_user.organization_id
        )
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return helpers.render(
        "meetings/all.html.jinja",
        meetings_list_props={
            # collectionId selects the collection mode (editable header + that
            # collection's meetings). When it's null the island falls back to a
            # pseudo-collection, deriving the "Most Recent" / "Uncategorized"
            # title/description from `uncategorized` — keeping those query-derived
            # strings out of data-props.
            "uncategorized": collection is None and filter == MeetingCollectionFilter.UNCATEGORIZED,
            "collectionId": str(collection.id) if collection else None,
            "collectionsIndexUrl": str(helpers.url_for("meetings_collections_index")),
        },
    )


# One route renders every lifecycle state of a meeting. The React island
# (react-meeting-show) branches on is_upcoming to show the upcoming (agenda /
# recording) view or the completed (recording / transcript) view — see
# MeetingShow.tsx.
@router.get("/meetings/{meeting_id}")
async def meetings_show(
    meeting_presenter: MeetingPresenter = Depends(get_meeting_presenter),
    helpers: Helpers = Depends(get_helpers),
):
    return helpers.render(
        "meetings/show.html.jinja",
        meeting=meeting_presenter,
        back=back_navigation(helpers.request, fallback_route="meetings_index"),
    )


# Legacy alias. The upcoming/completed split is gone (meetings_show handles every
# lifecycle state), but already-sent emails and bookmarks still point here, so
# keep redirecting them to the canonical show page indefinitely.
@router.get("/meetings/{meeting_id}/upcoming")
async def meetings_show_upcoming(meeting_id: UUID, helpers: Helpers = Depends(get_helpers)):
    return helpers.redirect_to(helpers.url_for("meetings_show", meeting_id=meeting_id))
