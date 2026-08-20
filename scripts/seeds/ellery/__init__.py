import os
from datetime import UTC, datetime
from pathlib import Path

from app.models.collaboration.mailbox import Mailbox
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.goals import Goal, GoalUpdate
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post
from config.enums import GoalStatus, Sharing
from scripts.seeds.content_seeder import ContentSeeder
from scripts.seeds.ellery.accounts import seed_people
from scripts.seeds.ellery.alignments import seed_alignments
from scripts.seeds.seeder import fields

CONTENT_DIR = Path(__file__).parent / "content"


async def seed():
    people = await seed_people()
    cs = ContentSeeder(content_dir=CONTENT_DIR)

    with fields(organization=people.org):
        with fields(Goal, sharing=Sharing.ORGANIZATION, status=GoalStatus.ON_TRACK, activated_at=datetime.now(UTC)):
            with fields(GoalUpdate, question_text="How is this goal progressing?"):
                await cs.seed_dir("goals")

        with fields(Meeting, sharing=Sharing.ORGANIZATION):
            await cs.seed_dir("meetings")
            await cs.seed_recurring_meetings()

        with fields(Post, sharing=Sharing.ORGANIZATION):
            await cs.seed_dir("posts")

        # Alignments link goals to seeded Posts/Meetings, so they run after both exist.
        await seed_alignments(people)

        await cs.seed_chats()
        await cs.seed_dir("documents")

        await cs.seed_dir("emails")

        # Mailbox sync is a last-mile replay of production signal behavior (post
        # subscribers get PostMailboxEntry rows, chat members get ChatMailboxEntry,
        # email threads refresh metadata + workspace collaborators). Skip under
        # ENV=test: it adds 10+s of deep prefetch work to the parametric scenario
        # test and the test only validates that the seed data itself is consistent.
        if os.environ.get("ENV") != "test":
            await cs.sync_post_mailbox_entries(people.org)
            await cs.sync_chat_mailbox_entries(people.org)

    if os.environ.get("ENV") != "test":
        for thread in await EmailThread.filter(organization=people.org):
            await thread.update_metadata_from_messages()
            await thread.fetch_related("workspace__collaborators__user", "messages__attachments")
            await Mailbox.sync(thread)
