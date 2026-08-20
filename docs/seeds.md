# Seeds

Seeds create realistic, pre-populated scenarios for development and testing. They live in `scripts/seeds/`.
All seed content is authored fiction, checked into the repository as markdown and YAML. The default
scenario is `ellery`: an 11-person company with goals, meetings, chats, documents, posts, and email threads.

## Running seeds

```
make db_seed ARGS="--list"                        # list scenarios
make db_seed ARGS="ellery"                        # run specific scenario
make db_seed                                      # run all scenarios
make test_seeds                                   # validate without persisting (preferred)
```

Use `make test_seeds` when iterating on seed data — it dry-runs all scenarios in a transaction and rolls back, so it's fast and won't affect your dev database.

Seeding is additive and idempotent: record IDs derive from the scenario namespace plus a seed key, so
re-running updates records in place rather than duplicating them. Use `make db_reset` when you want a clean
slate instead.

## Superusers

Superuser is granted per address via the `SUPERUSER_EMAILS` setting (comma-separated), not by anything a seed writes, so a scenario cannot create one on its own. `.env.development` lists `darren@ellery.ai`, the Ellery CEO, which is what makes the superuser-gated surfaces (the `/api` docs, the organization system prompt, `/background_jobs`) reachable after `make db_seed ARGS="ellery"`. Add your own address to that list if you want to sign in as yourself and still reach them.

## Creating a scenario

1. Create a package under `scripts/seeds/` (e.g., `my_scenario/`)
2. Add a `__init__.py` that exposes an `async def seed()` function
3. Run with `make db_seed ARGS="my_scenario"`

Reference `ellery/` for the canonical structure:

```python
# ellery/__init__.py
from scripts.seeds.seeder import fields


async def seed():
    people = await seed_people()
    with fields(organization=people.org):
        goals = await seed_goals(people)
        await seed_tasks(people, goals)
        await seed_meetings(people)
        ...
```

- `accounts.py` — creates org, users, groups; returns a dataclass of references
- Each other module (`goals.py`, `tasks.py`, etc.) takes `people` and optionally returns references for downstream modules

## API

### `create(Model, "key", **kwargs)`

```python
from scripts.seeds.seeder import create

goal = await create(Goal, "north-star", title="Ship v2", creator=alice)
```

- Generates a deterministic UUID from the scenario namespace + key — re-running returns the existing record
- Merges global defaults → model defaults → kwargs (kwargs win)
- Resolves FK instances to `_id` fields (e.g., `creator=user` → `creator_id=user.id`)
- Auto-runs User onboarding setup
- Indexes search content after all scenarios complete

### `fields(model=None, **kwargs)`

Context manager for temporary defaults. Scope to a model or omit for global defaults:

```python
with fields(organization=org):
    with fields(Goal, sharing=Sharing.ORGANIZATION, status=GoalStatus.ON_TRACK):
        goal = await create(Goal, "my-goal", title="Ship it", creator=alice)
```

### `prefix(key_prefix)`

Context manager that auto-prefixes keys. Prefixes nest:

```python
post = await create(Post, "post-rfc", title="RFC: API versioning", creator=bob)
with prefix("post-rfc"), fields(PostComment, post=post):
    await create(PostComment, "body", user=bob, content="...")  # key → "post-rfc-body"
    await create(PostComment, "carol", user=carol, content="...")  # key → "post-rfc-carol"
```

## Email content

Emails live in `content/emails/<thread-key>/*.md`, one directory per thread and one file per
record, seeded via `cs.seed_dir("emails")`. Each file is frontmatter plus an HTML body:

```markdown
---
key: arjun-github-01-approved
model: EmailMessage
thread: !ref thread-arjun-github
user: !ref arjun
message_type: received
sender: "GitHub <notifications@github.com>"
to:
  - !ref arjun
subject: "[ellery/platform] PR #2418 approved"
received_at: !relative_day {offset: -2, hour: 14, tz: America/New_York}
---

<p>Body as HTML.</p>
```

- The `EmailThread` is created on demand by a `before_create(EmailMessage)` hook from the
  `thread:` ref, so there is no separate thread file.
- `model: EmailThreadComment` in the same directory attaches an in-app comment to the thread.

See `scripts/seeds/README.md` for the chat and document content formats.

## Pitfalls

- **Create group members before goals** — `GroupMember` post_save subscribes members to goals owned by that group. If members don't exist yet, they won't get subscribed.
- **MeetingAttendee is Pydantic** — Pass `MeetingAttendee(...)` instances to the `attendees` list field, not database records.
