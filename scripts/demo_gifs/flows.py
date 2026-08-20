from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

from scripts.demo_gifs.scene import HEIGHT, WIDTH, Scene

INVITE_EMAIL = "alex.rivera@example.com"
# How far before the next meeting to freeze the clock, so the nav pill reads "in N min".
MEETING_LEAD_MINUTES = 20


class Flow(ABC):
    # name is the output stem: it becomes {name}.gif, matching static/images/{name}.gif
    name: str
    show_cursor: bool = True  # show the synthetic mouse cursor
    show_keys: bool = False  # show on-screen keycaps for keypresses (keyboard-driven flows)

    @abstractmethod
    async def run(self, scene: Scene) -> None: ...


class CommandPalette(Flow):
    # Keyboard-driven: no cursor, on-screen keycaps show ⌘K and the typed query.
    name = "command_palette"
    show_cursor = False
    show_keys = True

    async def run(self, scene: Scene) -> None:
        await scene.goto()
        await scene.wait('[data-test-id^="mailbox-entry-"]')
        await scene.settle(400)
        await scene.begin()

        await scene.settle(700)
        await scene.press("Meta+k")
        await scene.wait('[data-test-id="command-palette"]')
        await scene.settle(600)

        await scene.type('[data-test-id="palette-input"]', "Keating", delay=110)
        await scene.settle(2200)


class Collaborators(Flow):
    name = "collaborators"

    async def run(self, scene: Scene) -> None:
        # Open directly on an email thread (as the original GIF did), then add a collaborator.
        await scene.goto(await _first_thread_path(scene))
        await scene.wait("#email-thread")
        await scene.settle(400)
        await scene.begin()

        await scene.settle(800)
        await scene.click('[data-test-id="workspace-collaborators"]')
        await scene.wait('[data-test-id="current-collaborators"]')
        await scene.settle(700)

        await scene.click('[data-test-id^="add-collaborator-"] button')
        await scene.settle(1600)


class MeetingNavigationBar(Flow):
    name = "meeting_navigation_bar"

    async def run(self, scene: Scene) -> None:
        # Freeze the clock just before Darren's next meeting so the pill reliably shows an
        # imminent meeting ("in N min") instead of "No meetings today" — its copy is
        # today-scoped and relative to now, which otherwise drifts with wall-clock time.
        start = await _next_meeting_start(scene)
        if start:
            await scene.freeze_clock(start - timedelta(minutes=MEETING_LEAD_MINUTES))

        await scene.goto()
        pill = 'a[href="/meetings/upcoming"]'
        await scene.wait(pill)
        # The pill copy is populated by an async fetch; wait before revealing so the demo
        # opens on the populated pill rather than the bare calendar icon.
        await scene.settle(1800)
        await scene.begin()

        await scene.settle(500)
        await scene.click(pill, pause=1400)
        await scene.wait_url("**/meetings/upcoming")
        # Navigation re-hides the cursor (fresh document); re-place it so it stays visible.
        await scene.move_cursor(WIDTH / 2, HEIGHT * 0.4)
        await scene.settle(1800)


class TeamMembers(Flow):
    name = "team_members"

    async def run(self, scene: Scene) -> None:
        # Start on the inbox and navigate the real path: ⋮ (More options) menu → Team
        # Members (admin-only link) → invite. Mirrors the email's instructions.
        await scene.goto()
        await scene.wait('button[aria-label="More options"]')
        await scene.settle(400)
        await scene.begin()

        await scene.settle(700)
        await scene.click('button[aria-label="More options"]')
        await scene.settle(500)
        await scene.click('a[href="/organization/users"]:has-text("Team Members")')
        await scene.wait_url("**/organization/users")
        await scene.wait("#org-users-list")
        await scene.settle(900)

        await scene.click('input[name="email"]')
        await scene.type('input[name="email"]', INVITE_EMAIL, delay=70)
        await scene.settle(700)
        await scene.click('button[type="submit"]:has-text("Invite")')
        await scene.settle(1800)


async def _next_meeting_start(scene: Scene) -> datetime | None:
    data = await scene.get_json("/api/meetings?scope=member&completed=false&sort=scheduled_at_asc")
    now = datetime.now(UTC)
    for meeting in data.get("meetings", []):
        scheduled_at = meeting.get("scheduled_at")
        if scheduled_at:
            start = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            if start > now:
                return start
    return None


async def _first_thread_path(scene: Scene) -> str:
    data = await scene.get_json("/api/mailbox_entries")
    thread = next(
        (e for e in data.get("entries", []) if e.get("resource_type") == "EmailThread" and e.get("href")),
        None,
    )
    if thread is None:
        raise RuntimeError("No email thread found in mailbox — did you seed the ellery demo data?")
    return thread["href"]


FLOWS: list[Flow] = [
    CommandPalette(),
    Collaborators(),
    MeetingNavigationBar(),
    TeamMembers(),
]
