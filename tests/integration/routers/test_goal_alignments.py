from uuid import uuid4

import pytest
from starlette import status

from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_user


# The index and show pages now mount React islands that fetch their own data from the JSON API
# (GET /api/goal_alignments and GET /api/goals/{goal_id}/alignments). The page routes only render
# the mount div, so these tests assert the mount is present rather than server-rendered content.
# Alignment behavior (create/delete/pin/search/timeline) is covered by the API tests in
# tests/integration/routers/api/test_goal_alignments.py.
@pytest.mark.asyncio
async def test_index_renders_island_mount(client: AppClient):
    user = await create_user(email="test@convictional.com")
    client.current_user = user

    response = await client.get("/goal_alignments")

    assert response.status_code == status.HTTP_200_OK
    assert 'id="react-goal-alignments-index"' in response.text


@pytest.mark.asyncio
async def test_show_renders_island_mount(client: AppClient):
    user = await create_user(email="test@convictional.com")
    client.current_user = user
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, title="Revenue Growth")

    response = await client.get(f"/goals/{goal.id}/alignments")

    assert response.status_code == status.HTTP_200_OK
    # The island bootstraps from data-props carrying the goal id. Scope the check to the
    # mount's opening tag: the server-rendered badge href also contains goal.id, so a bare
    # `str(goal.id) in response.text` would pass even if the data-props prop were dropped.
    mount_tag = response.text.split('id="react-goal-alignments-show"', 1)[1].split(">", 1)[0]
    assert "goalId" in mount_tag and str(goal.id) in mount_tag
    # The goal badge stays server-rendered above the island.
    assert "Revenue Growth" in response.text


@pytest.mark.asyncio
async def test_show_redirects_for_missing_goal(client: AppClient):
    user = await create_user(email="test@convictional.com")
    client.current_user = user

    response = await client.get(f"/goals/{uuid4()}/alignments")

    # Redirects to the index, which the client follows (follow_redirects=True).
    assert response.status_code == status.HTTP_200_OK
    assert 'id="react-goal-alignments-index"' in response.text
