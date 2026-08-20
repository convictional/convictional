from types import SimpleNamespace
from typing import cast

import pytest

from app.helpers.workspaces import resource_label
from app.models.collaboration.workspace import WorkspaceMixin


# Resource-shaped duck types — using SimpleNamespace keeps this a true unit
# test (no Tortoise/DB init). The Goal-specific branch is exercised end-to-end
# in tests/integration/routers/test_workspace_collaborators.py
# (test_request_collaborator_access_subject_falls_back_to_description).
def _resource(**attrs) -> WorkspaceMixin:
    return cast(WorkspaceMixin, SimpleNamespace(**attrs))


@pytest.mark.parametrize(
    ("resource", "expected"),
    [
        # Title set wins.
        (_resource(title="Q3 Planning"), "Q3 Planning"),
        # Whitespace-only title gets the placeholder.
        (_resource(title="   "), "(untitled)"),
        (_resource(title=""), "(untitled)"),
        (_resource(title=None), "(untitled)"),
        # Internal whitespace (incl. newlines that would otherwise break an
        # RFC 5322 Subject header) is collapsed.
        (_resource(title="Q3\nPlanning\t  Sync"), "Q3 Planning Sync"),
    ],
)
def test_resource_label(resource, expected):
    assert resource_label(resource) == expected
