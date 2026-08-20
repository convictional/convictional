from http.cookies import Morsel, SimpleCookie

import httpx
import pytest
from fastapi import status

from app.routers.dependencies import INBOX_SORT_PREFERENCE_COOKIE
from config.enums import Integration
from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_mailbox_view, create_user

STALE_ID = "00000000-0000-0000-0000-000000000000"


def _parse_set_cookie(response: httpx.Response, name: str) -> Morsel | None:
    jar: SimpleCookie = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        jar.load(header)
    return jar.get(name)


def _is_cleared(morsel: Morsel) -> bool:
    # A cleared cookie has either max-age=0 or an expiry in the past, and an empty value.
    return morsel.value == "" and (morsel["max-age"] == "0" or morsel["expires"] != "")


async def _show(client: AppClient, stored: str | None = None) -> httpx.Response:
    client.cookies.delete(INBOX_SORT_PREFERENCE_COOKIE)
    cookies = {INBOX_SORT_PREFERENCE_COOKIE: stored} if stored is not None else None
    return await client.get("/api/users/me/mailbox_focus", cookies=cookies)


@pytest.mark.asyncio
async def test_mailbox_focus_show_resolves_stored_preference(client: AppClient):
    # Onboarding complete so the getting-started default doesn't fire and the stored
    # preference is the only variable under test.
    user = await create_user(integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    goal = await create_goal(organization_id=user.organization_id, owner_id=user.id, creator_id=user.id)

    with client.current_user_as(user):
        response = await _show(client, "sort=oldest")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "sort": "oldest",
            "mailbox_view_template": None,
            "goal_id": None,
            "mailbox_view_id": None,
        }

        # newest is the default, so it resolves to the default focus (bare inbox URL, no params).
        assert (await _show(client, "sort=newest")).json() == {
            "sort": None,
            "mailbox_view_template": None,
            "goal_id": None,
            "mailbox_view_id": None,
        }

        # No stored preference and onboarding complete is also the default focus.
        assert (await _show(client)).json()["sort"] is None

        assert (await _show(client, "mailbox_view_template=urgent_important")).json()["mailbox_view_template"] == (
            "urgent_important"
        )

        body = (await _show(client, f"mailbox_view_template=by_goal&goal_id={goal.id}")).json()
        assert body["mailbox_view_template"] == "by_goal"
        assert body["goal_id"] == str(goal.id)

        assert (await _show(client, f"mailbox_view_id={view.id}")).json()["mailbox_view_id"] == str(view.id)

        # None of the resolvable cases touch the stored preference.
        assert _parse_set_cookie(await _show(client, "sort=oldest"), INBOX_SORT_PREFERENCE_COOKIE) is None


@pytest.mark.asyncio
async def test_mailbox_focus_show_heals_unusable_preference(client: AppClient):
    # A preference that can't be rendered resolves to the default focus AND is cleared, so it
    # stops being re-resolved for the rest of the cookie's year-long life.
    user = await create_user(integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    other_user = await create_user()  # creates its own org
    other_view = await create_mailbox_view(user_id=other_user.id, organization_id=other_user.organization_id)

    unusable = [
        "garbage_key=wat",  # unknown key
        "sort=",  # no value
        "no_separator",  # not a key=value pair
        "sort=sideways",  # not a MailboxSort
        "mailbox_view_template=not_a_template",  # unknown template
        "mailbox_view_template=by_goal&goal_id=not-a-uuid",
        f"mailbox_view_template=by_goal&goal_id={STALE_ID}",  # deleted goal
        "mailbox_view_id=not-a-uuid",
        f"mailbox_view_id={STALE_ID}",  # deleted saved view
        f"mailbox_view_id={other_view.id}",  # another org's saved view
    ]

    with client.current_user_as(user):
        for stored in unusable:
            response = await _show(client, stored)
            assert response.status_code == status.HTTP_200_OK, stored
            assert response.json() == {
                "sort": None,
                "mailbox_view_template": None,
                "goal_id": None,
                "mailbox_view_id": None,
            }, stored
            morsel = _parse_set_cookie(response, INBOX_SORT_PREFERENCE_COOKIE)
            assert morsel is not None and _is_cleared(morsel), stored


@pytest.mark.asyncio
async def test_mailbox_focus_show_defaults_new_users_into_onboarding(client: AppClient):
    # The onboarding "Getting started" focus is the default for a user with no stored preference
    # whose Google setup is unfinished; connecting both integrations stops it.
    user = await create_user()

    with client.current_user_as(user):
        assert (await _show(client)).json()["mailbox_view_template"] == "getting_started"

        # Connecting only Gmail is not enough — still incomplete.
        await user.add_integration(Integration.GMAIL)
        assert (await _show(client)).json()["mailbox_view_template"] == "getting_started"

        await user.add_integration(Integration.RECALL_AI_CALENDAR)
        assert (await _show(client)).json()["mailbox_view_template"] is None

        # An explicitly stored focus always wins over the onboarding default.
        await user.remove_integration(Integration.GMAIL)
        assert (await _show(client, "sort=newest")).json()["mailbox_view_template"] is None


@pytest.mark.asyncio
async def test_mailbox_focus_update_stores_preference(client: AppClient):
    user = await create_user()
    view = await create_mailbox_view(user_id=user.id, organization_id=user.organization_id)
    goal = await create_goal(organization_id=user.organization_id, owner_id=user.id, creator_id=user.id)

    cases = [
        ({"sort": "oldest"}, "sort=oldest"),
        # Clearing the focus is stored as the explicit default sort, not as an absent preference.
        ({"sort": "newest"}, "sort=newest"),
        ({"mailbox_view_template": "getting_started"}, "mailbox_view_template=getting_started"),
        ({"mailbox_view_id": str(view.id)}, f"mailbox_view_id={view.id}"),
        (
            {"mailbox_view_template": "by_goal", "goal_id": str(goal.id)},
            f"mailbox_view_template=by_goal&goal_id={goal.id}",
        ),
    ]

    with client.current_user_as(user):
        for body, expected in cases:
            client.cookies.delete(INBOX_SORT_PREFERENCE_COOKIE)
            response = await client.patch("/api/users/me/mailbox_focus", json=body)
            assert response.status_code == status.HTTP_204_NO_CONTENT, body
            assert response.content == b""
            morsel = _parse_set_cookie(response, INBOX_SORT_PREFERENCE_COOKIE)
            assert morsel is not None, body
            assert morsel.value == expected
            # The client never reads or writes this cookie itself.
            assert morsel["httponly"]

        # A stored focus round-trips through the GET.
        assert (await client.get("/api/users/me/mailbox_focus")).json() == {
            "sort": None,
            "mailbox_view_template": "by_goal",
            "goal_id": str(goal.id),
            "mailbox_view_id": None,
        }


@pytest.mark.asyncio
async def test_mailbox_focus_update_rejects_unstorable_focus(client: AppClient):
    user = await create_user()

    with client.current_user_as(user):
        for body in (
            {},  # nothing to store
            {"sort": "sideways"},
            {"goal_id": STALE_ID},  # a goal alone isn't a focus
            {"mailbox_view_template": "not_a_template"},
        ):
            response = await client.patch("/api/users/me/mailbox_focus", json=body)
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, body
            assert _parse_set_cookie(response, INBOX_SORT_PREFERENCE_COOKIE) is None


@pytest.mark.asyncio
async def test_mailbox_focus_requires_authentication(client: AppClient):
    with client.logged_out():
        assert (await client.get("/api/users/me/mailbox_focus")).status_code == status.HTTP_401_UNAUTHORIZED
        response = await client.patch("/api/users/me/mailbox_focus", json={"sort": "oldest"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
