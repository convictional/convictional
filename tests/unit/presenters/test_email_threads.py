import types
from uuid import uuid4

from app.presenters.email_threads import EmailThreadPresenter

creator_id = uuid4()
assignee_id = uuid4()
viewer_id = uuid4()


def _make_presenter(current_user_id, thread_creator_id, assignee=None, external_thread_id=None, can_reply=True):
    workspace = types.SimpleNamespace(
        assignee_id=assignee.id if assignee else None,
        assignee=assignee,
    )
    current_user = types.SimpleNamespace(id=current_user_id)
    creator = types.SimpleNamespace(id=thread_creator_id, display_name="Alice")
    thread = types.SimpleNamespace(
        creator_id=thread_creator_id,
        creator=creator,
        workspace=workspace,
        external_thread_id=external_thread_id,
        can_reply=lambda user: can_reply,
    )
    return EmailThreadPresenter(thread, current_user=current_user)  # type: ignore[arg-type]


def _make_assignee(id, display_name="Bob"):
    return types.SimpleNamespace(id=id, display_name=display_name)


def test_sendable_by_new_thread_creator_is_current_user():
    presenter = _make_presenter(creator_id, creator_id, assignee=_make_assignee(assignee_id))
    assert presenter.sendable_by == "Sendable by you or Bob"


def test_sendable_by_new_thread_assignee_is_current_user():
    presenter = _make_presenter(assignee_id, creator_id, assignee=_make_assignee(assignee_id))
    assert presenter.sendable_by == "Sendable by you or Alice"


def test_sendable_by_new_thread_creator_is_assignee():
    presenter = _make_presenter(creator_id, creator_id, assignee=_make_assignee(creator_id, "Alice"))
    assert presenter.sendable_by == "Sendable by you"


def test_sendable_by_new_thread_third_party_viewer():
    presenter = _make_presenter(viewer_id, creator_id, assignee=_make_assignee(assignee_id), can_reply=False)
    assert presenter.sendable_by == "Sendable by Alice or Bob"


def test_sendable_by_existing_thread_owner():
    presenter = _make_presenter(
        creator_id, creator_id, assignee=_make_assignee(assignee_id), external_thread_id="gmail-123", can_reply=True
    )
    assert presenter.sendable_by == "Sendable by you (owner)"


def test_sendable_by_existing_thread_non_owner():
    presenter = _make_presenter(
        viewer_id, creator_id, assignee=_make_assignee(assignee_id), external_thread_id="gmail-123", can_reply=False
    )
    assert presenter.sendable_by == "Sendable by Alice (owner)"


def test_sendable_by_no_assignee():
    presenter = _make_presenter(creator_id, creator_id, can_reply=True)
    assert presenter.sendable_by == "Sendable by you (owner)"


def test_send_button_tooltip_new_thread():
    presenter = _make_presenter(viewer_id, creator_id, assignee=_make_assignee(assignee_id), can_reply=False)
    assert presenter.send_button_tooltip == "Only the owner or assignee can send this draft"


def test_send_button_tooltip_existing_thread():
    presenter = _make_presenter(
        viewer_id, creator_id, assignee=_make_assignee(assignee_id), external_thread_id="gmail-123", can_reply=False
    )
    assert presenter.send_button_tooltip == "Only the owner can send this draft"
