"""LEGACY — email-only notification coverage for Document, Meeting.

Email is out of scope for the notifications spec (see `docs/notifications-spec.md`): the
system's two surfaces are inbox and push. But Document / Meeting have no native inbox
surface yet, so email is currently their *only* notification channel — the legacy path the
inbox is meant to replace — and regressions there are real. This module protects that
legacy behavior until those resources move onto the inbox.

It is deliberately quarantined: it reads the fake email sink directly (never the
inbox/push surfaces), and reuses the generic `Scenario` only to build the cast. DELETE
this module and `test_legacy_email.py` once Document/Meeting have inbox UIs and are
covered by the inbox/push suite.
"""

from enum import StrEnum

from app.models.accounts import User
from app.models.workspaces.documents import Document
from app.models.workspaces.meetings import Meeting
from config.enums import Sharing
from infra.email import fake_delivery
from tests.helpers.app import AppClient
from tests.helpers.factories import create_document, create_meeting, create_user
from tests.integration.notifications.scenarios import Scenario


class Email(StrEnum):
    EMAILED = "emailed"
    NOT_EMAILED = "not_emailed"


EMAILED = Email.EMAILED
NOT_EMAILED = Email.NOT_EMAILED


def email_outcome(user: User) -> Email:
    return Email.EMAILED if fake_delivery.by_recipient(user.email) else Email.NOT_EMAILED


def assert_emails(expected: dict[str, Email], actual: dict[str, Email]) -> None:
    lines = [
        f"  {key:20} expected {exp.value:11}  got {actual[key].value}"
        for key, exp in expected.items()
        if actual[key] != exp
    ]
    assert not lines, "email delivery mismatches (persona → email):\n" + "\n".join(lines)


#
# Adapter — fires the event over the real HTTP API as the acting user.
#


async def emit_document_comment(
    client: AppClient, document, actor: User, *, content: str, comment_mark_id: str = "mark-1"
) -> str:
    # Document comments thread by `comment_mark_id` (the annotation anchor), not a parent
    # link — two comments sharing a mark are the same thread. Reply within a thread by
    # passing the same `comment_mark_id`.
    with client.current_user_as(actor):
        resp = await client.post(
            f"/api/documents/{document.id}/comments",
            json={"content": content, "quoted_text": "some text", "comment_mark_id": comment_mark_id},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def emit_meeting_agenda_update(client: AppClient, meeting, actor: User, *, agenda: str = "Q3 agenda") -> None:
    with client.current_user_as(actor):
        resp = await client.patch(f"/api/meetings/{meeting.id}", json={"agenda": agenda})
    assert resp.status_code == 200, resp.text


class EmailScenario(Scenario):
    """A Scenario whose only surface is email. Reuses generic cast setup; asserts on the
    email sink. People get no push device — these resources never push."""

    async def add(self, key: str, **traits) -> User:
        traits.setdefault("device", False)
        return await super().add(key, **traits)

    async def expect_emails(self, **expected: Email) -> None:
        actual = {key: email_outcome(self.people[key]) for key in expected}
        assert_emails(expected, actual)


class DocumentScenario(EmailScenario):
    record_type = Document.record_type

    @classmethod
    async def new(cls, client: AppClient) -> "DocumentScenario":
        organization_id = (await client.get_default_user()).organization_id
        creator = await create_user(name="creator", organization_id=organization_id, time_zone="UTC")
        scenario = cls(client, organization_id)
        scenario.people["creator"] = creator
        scenario.resource = await create_document(
            creator_id=creator.id, organization_id=organization_id, sharing=Sharing.ORGANIZATION
        )
        await scenario.resource.fetch_related("workspace")
        return scenario

    async def comment(self, *, by: str, mentioning: str | None = None, comment_mark_id: str = "mark-1") -> str:
        content = f"thoughts? @[{self.people[mentioning].name}]" if mentioning else "please review"
        return await emit_document_comment(
            self.client, self.resource, self.people[by], content=content, comment_mark_id=comment_mark_id
        )


class MeetingScenario(EmailScenario):
    record_type = Meeting.record_type

    @classmethod
    async def new(cls, client: AppClient) -> "MeetingScenario":
        organization_id = (await client.get_default_user()).organization_id
        creator = await create_user(name="creator", organization_id=organization_id, time_zone="UTC")
        scenario = cls(client, organization_id)
        scenario.people["creator"] = creator
        scenario.resource = await create_meeting(creator_id=creator.id, organization_id=organization_id)
        await scenario.resource.fetch_related("workspace")
        return scenario

    async def update_agenda(self, *, by: str) -> None:
        await emit_meeting_agenda_update(self.client, self.resource, self.people[by])
