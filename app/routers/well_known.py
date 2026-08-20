from fastapi import APIRouter, status
from fastapi.responses import JSONResponse, Response

from config import settings

router = APIRouter()


# In-app routes that should open the iOS app via Universal Links when tapped on
# `convictional.com`. Anything not enumerated here falls through to Safari —
# that's intentional for the apex (`/` redirects between marketing and product
# depending on auth state), legal pages (`/policies/*` served by the LB
# pointing at the marketing site), and the auth-entry pages (`/login`,
# `/signup`). The allowlist mirrors the user-tappable, auth-gated product
# surface: inbox/mailbox views, primary resources, and the global ID
# redirect that notification links use.
#
# Android (when it lands) does NOT use this list — Android's
# Digital Asset Links file (`/.well-known/assetlinks.json`) carries no path
# information; per-path filtering for Android lives in `intent-filter`
# entries in AndroidManifest.xml. The Expo config will need to mirror this
# list there, but the constant stays iOS-shaped because the syntax (glob
# patterns) is iOS-specific.
APPLE_APP_SITE_ASSOCIATION_PATHS: list[str] = [
    # Mailbox views (inbox lives at `/`, which we intentionally do not
    # deep-link; the named views below are the linkable surfaces).
    "/archived",
    "/sent",
    "/drafts",
    "/assigned_to_me",
    "/snoozed",
    # Primary resources.
    "/email_threads/*",
    "/posts/*",
    "/goals/*",
    "/documents/*",
    "/chats/*",
    "/meetings/*",
    "/meetings_collections/*",
    "/workspaces/*",
    # Groups: only the index is GET-routable (membership routes are
    # POST-only). Listing `/groups/*` would silently catch nothing.
    "/groups",
    # Profile editing. Narrower than the original `/profile/*` because the
    # only other GET under that prefix is `/profile/{user_id}/avatar`, which
    # 302-redirects to a GCS signed image URL — not something a user expects
    # to open in the app from an email link.
    "/profile/edit",
    # Global ID redirect — notification links resolve through here.
    "/gid/*",
    # Search + notifications index.
    "/search",
    "/notifications",
    # NOTE: `/organization/*` is intentionally absent — the admin-only pages
    # under it (`/organization/users`, `/organization/updates_configuration`) are
    # server admin-gated (`Depends(get_admin_user)`), so a non-admin tapping such
    # a link would get a 403 inside the WebView with no recovery affordance.
    # `/organization/edit` is now the client-routed SPA settings page; it gates
    # admins in the route's beforeLoad rather than at the server, so it is also
    # left out here rather than special-cased.
    #
    # `/people/*` is absent — the only GET (`/people/{user_id}/card`) renders
    # an HTMX fragment template intended for in-page swap-in, not a full
    # page with chrome.
]


# Universal Links contract: iOS fetches this file once at app-install time
# (and on subsequent updates) from the apex of every domain listed in
# `ios.associatedDomains`. The response body lists the (Team ID, bundle ID)
# pairs allowed to claim Universal Link routing for the enumerated paths.
#
# Returns 404 when `settings.apple_team_id` is unset — iOS treats a missing
# AASA file as "no association," which is the correct behavior in dev where
# we don't have a real team ID configured. Production must set
# `APPLE_TEAM_ID` for app links to bind.
@router.get("/.well-known/apple-app-site-association", include_in_schema=False)
async def apple_app_site_association() -> Response:
    if not settings.apple_team_id:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    body = {
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": f"{settings.apple_team_id}.{settings.ios_bundle_id}",
                    "paths": APPLE_APP_SITE_ASSOCIATION_PATHS,
                }
            ],
        }
    }
    return JSONResponse(
        body,
        media_type="application/json",
        headers={"Cache-Control": "no-cache"},
    )
