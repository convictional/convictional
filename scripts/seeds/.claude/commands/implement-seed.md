---
description: Generate seed content files and avatars from an existing story
model: opus
---

# Implement Seed

You orchestrate the implementation phase of demo seed generation: translating an approved story into content files (`.md` with YAML frontmatter), Python orchestration files, and avatar images.

## Validation

A scenario name argument is **required**. If not provided, tell the user:

```
Please specify a scenario name. Usage: /implement-seed {scenario_name}

To see available scenarios with stories, check scripts/seeds/*/story.md
```

Check that `scripts/seeds/{scenario}/story.md` exists. If not:

```
No story found at scripts/seeds/{scenario}/story.md

Run /write-story first to create one, or /write-story {scenario} to iterate on an existing one.
```

Read the story.

## Schema Analysis

Use the `/discover-models` skill to understand the data model:

1. Run `list` to see all models
2. Run `order` to get creation dependencies
3. Run `show` for key models referenced in the story (e.g., Goal, Task, Meeting, Post, EmailMessage, EmailThread, EmailThreadComment, GoalComment, GoalUpdate, PostComment, MeetingCollection, etc.)

**Summarize concisely** — you'll need this for the spawn prompts.

Tell the user:

```
Schema analysis complete. Writing scaffolding files...
```

## Scaffolding

Write `accounts.py` and `__init__.py` directly. These are small files and you have full context (schema + story) to write them correctly.

1. **Read the reference implementation** — `ellery/accounts.py` and `ellery/__init__.py`
2. **Write `accounts.py`** — `People` dataclass and `seed_people()` function. Include `_create_group` helper if the story has groups. Use the story's Cast of Characters for user details (name, email, role, admin status).
3. **Write `__init__.py`** — `ContentSeeder.seed_dir()` calls in dependency order, with appropriate `fields()` context managers. Include the `EmailThread.update_metadata_from_messages()` / `Mailbox.sync()` post-processing block.
4. **Extract people keys** — collect all user keys (e.g., `alice`, `bob`) from `accounts.py` for the spawn prompts.

Tell the user:

```
Scaffolding complete. Launching content writers...
```

## Content Writing (Agent Team)

Content domains are independent — goals don't reference meetings, posts don't reference emails. The only shared dependency is people keys, which you extracted from `accounts.py`. This makes content writing ideal for parallelization.

### 1. Analyze content domains

Read the story and determine which content domains are needed. Not every story has all domains. Only spawn teammates for domains that exist in the story.

Possible domains and their content directories:

| Domain | Directories | What it writes |
|--------|------------|----------------|
| Goals | `goals/` | Goals, subgoals, updates, comments. Deepest nesting. |
| Meetings | `meetings/` | Meeting collections, meetings with attendees and transcripts. |
| Posts | `posts/` | Posts with body content and comment threads. |
| Decisions | `decisions/` | Decision processes, options, criteria. |
| Emails | `emails/` | All email threads, messages, and thread comments. Diverse HTML formatting. |
| Chats | `chats/` | Chat YAML files with messages, reactions, and threading. |
| Documents | `documents/` | Document markdown files with frontmatter + body. |

### 2. Create agent team

```
TeamCreate: {scenario}-seed-writers
```

### 3. Create tasks

Create one task per content domain using TaskCreate. No inter-task dependencies — all tasks can run in parallel.

### 4. Spawn teammates

Launch one teammate per domain using the Agent tool with `team_name` set to `{scenario}-seed-writers`. Each teammate gets a domain-specific spawn prompt built from the template below.

**Spawn all teammates in a single message** to maximize parallelism. Use `subagent_type: "seed-data-writer"` for each.

#### Spawn Prompt Template

Adapt this template for each domain. Replace `{SCENARIO}`, `{DOMAIN}`, `{DIRECTORIES}`, `{RELEVANT_STORY_SECTIONS}`, `{PEOPLE_KEYS}`, and `{SCHEMA_SUMMARY}` with the actual values.

```
You are a seed data writer specializing in {DOMAIN} content. Your task is to
write content files (.md with YAML frontmatter) for the `content/{DIRECTORIES}/`
subdirectory of the `scripts/seeds/{SCENARIO}/` package.

## Reference Material (read these first)
- `scripts/seeds/.claude/agents/seed-data-writer.md` — full conventions for
  content file format, YAML tags, directory structure, and pitfalls
- `scripts/seeds/.claude/shared-rules.md` — rules for goal titles, email
  volume, reactions
- `scripts/seeds/ellery/content/{DOMAIN}/` — reference examples for
  your domain
- `scripts/seeds/content_seeder.py` — how ContentSeeder processes files
- `scripts/seeds/hooks.py` — auto-creation hooks to understand (don't
  duplicate)

## Story
Read `scripts/seeds/{SCENARIO}/story.md` for the full narrative. Focus on
the sections relevant to your domain: {RELEVANT_STORY_SECTIONS}.

## People Keys
The following user keys are available for `!ref` references:
{PEOPLE_KEYS}

## Model Schema
{SCHEMA_SUMMARY}

## Critical Pitfall: Enum/Key Collision
NEVER use these words as file `key` values — they collide with enum value
resolution in ContentSeeder: sent, received, draft, private, organization,
on_track, at_risk, off_track, positive, negative, neutral, human, ai, pending,
approved, strong, medium, weak. Prefix with `msg-` or similar.

## Your Output
Write all .md files for `content/{DIRECTORIES}/`. Follow the directory nesting
conventions from the reference implementation. Do not write accounts.py,
__init__.py, or content for other domains.
```

#### Domain-specific prompt additions

**Goals writer** — Remind about goal title rules (1-2 words), subgoal descriptions must be measurable key results, directory nesting for parent/child goals, GoalUpdate and GoalComment models. Every goal and subgoal needs 3-4 GoalUpdate records with `created_at` timestamps spaced over weeks showing realistic progress (see shared-rules.md).

**Meetings writer** — Remind about MeetingCollection ordering (numeric prefix `00-`), `!attendee` tag for attendees, meeting body is transcript content. For recurring upcoming meetings, create templates in `content/meetings/recurring/` — these files omit `key` and `scheduled_at`, and instead specify `weekdays` (list of 0=Mon..6=Sun), `hour`, `minute`, and `tz`. The `ContentSeeder.seed_recurring_meetings()` method generates instances across the next 14 days with dynamic keys. See `ellery/content/meetings/recurring/` for examples.

**Posts writer** — Remind about Post/PostComment structure: the post `.md` creates the record, `00-body.md` inside its subdirectory is the first PostComment (the post body), subsequent numbered files are replies. Use `is_decision_comment: true` on a PostComment to mark it as the deciding comment. Posts are auto-published by a hook (no need for `published_at`). PostComments support `reactions` in frontmatter. Some posts should include `group: !ref <group-key>` for group assignment (see shared-rules.md).

**Decisions writer** — Remind about DecisionProcess/Option/Criterion/Evaluation models. Evaluations are auto-created by signals — use `Evaluation.filter(...).update(rating=...)` pattern. Note this in the prompt and remind them to check the reference implementation and `docs/seeds.md`.

**Emails writer** — Remind about email HTML diversity requirements (interpersonal, newsletters, notifications, transactional, sales outreach), volume targets from shared-rules.md, inline HTML bodies, thread directory structure, and EmailThreadComment model for thread comments. **Do NOT create post-notification email threads** (`thread-post-*` directories) — post notifications are native PostMailboxEntry records, not emails, and are synced by `cs.sync_post_mailbox_entries()` in `__init__.py`. **DO create research response emails** — one per user in `thread-research-{user}/` directories matching the production format (see seed-data-writer.md and shared-rules.md).

**Chats writer** — Chats are YAML files (not markdown) in `content/chats/`. Each file defines one Chat with `key`, `name`, optional `group`, `members` (user keys), and `messages`. Each message needs `key` (deterministic ID, prefix with chat key to avoid collisions), `author` (user key), `content`, and optional `at` (use `!relative_day`), `reply_to` (another message key in the same file), `reactions` (ReactionType enum string values → user keys, e.g. `thumbs_up: [alice, bob]`; do NOT use emoji glyphs). Mix group chats and DMs. DMs have no `name` or `group` — just 2 members. Don't reference Slack/competing chat tools (see shared-rules.md). Target 5-8 chats, ~20 messages per group chat, ~12 per DM.

**Documents writer** — Documents are markdown files in `content/documents/` using the standard YAML frontmatter + body pattern. Required frontmatter: `key`, `model: Document`, `title`, `creator: !ref <user-key>`. Optional: `sharing: organization` (default is private). The body is the document markdown — it becomes the initial LiveDocument content via a post-create hook. Target a mix of planning docs, process docs, design docs, retrospectives, research notes. Every document should be narratively meaningful — tied to the story's threads.

### 5. Avatar generation teammate

Avatars only depend on the story (Cast of Characters + Avatar Style) and people keys — not on content files. Spawn an avatar teammate **in the same message** as the content writers.

First check if avatars already exist:

```bash
ls scripts/seeds/{scenario}/avatars/*.png
```

If they already exist, skip this teammate. Otherwise, create a task and spawn a teammate with this prompt:

```
You are generating avatar images for the `scripts/seeds/{SCENARIO}/` demo
seed scenario.

Read `scripts/seeds/{SCENARIO}/story.md` — specifically the "Cast of
Characters" section for character descriptions and the "Avatar Style" section
for the art style.

Use the `/generate-avatar` skill to generate one avatar per character.
Run sequentially to avoid rate limits. The avatar files go in
`scripts/seeds/{SCENARIO}/avatars/{key}.png` where {key} is the
character's lowercased first name.

Characters to generate:
{LIST OF PEOPLE KEYS}

If generation fails (e.g. no GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT), report
the error — avatars are optional and the seed works without them.
```

### 6. Meeting video generation teammate

If the story includes meetings, spawn a video generation teammate **in the same message** as content writers and avatar generation.

First check if the video already exists:

```bash
ls scripts/seeds/{scenario}/assets/meeting_recording.mp4
```

If it already exists, skip this teammate. Otherwise, create a task and spawn a teammate with this prompt:

```
You are generating a meeting recording video for the `scripts/seeds/{SCENARIO}/` demo
seed scenario.

Use the `/generate-meeting-video` skill to generate a meeting recording video.
Run: scripts/seeds/{SCENARIO}/assets/meeting_recording.mp4 --scenario {SCENARIO}

If generation fails (e.g. no GEMINI_API_KEY or GOOGLE_CLOUD_PROJECT), report
the error — meeting videos are optional and the seed works without them.
```

### 7. Wait for completion

Monitor teammate progress. Answer questions if teammates message you. If a teammate encounters issues, help resolve them.

### 8. Clean up

After all teammates complete, delete the team.

## Verification

Validate every URL in post bodies returns 2xx — dead URLs still burn the `_unfurl_link_preview` hook's 8-second HTTP timeout and can push the CI demo seed test past its 15-second budget:

```bash
LOG_LEVEL=info make script ARGS="scripts/seeds/.claude/skills/validate-urls/scripts/validate_urls.py {scenario}"
```

If any URL fails, fix or remove it before proceeding.

Then run the test suite:

```bash
make test_seeds
```

If tests pass, report success:

```
All tests pass. The {scenario} seed scenario is ready.

Files created:
[list all files]
```

If tests fail, analyze the errors and fix the content files directly. Re-run tests after fixing.

## Important Rules

- **Validation, Schema Analysis, and Scaffolding run sequentially** — each depends on the previous phase's output. Content writing and avatar generation run in parallel via the team.
- **The lead writes Python scaffolding, the team writes content** — do not start writing content files yourself. Wait for teammates to finish.
- **Each teammate owns specific content directories** — no overlap between teammates.
- **If a teammate fails**, you can fix files directly or respawn a new teammate with error context.
- **Pass domain-specific schema summaries** to each teammate — only the models that teammate needs, not the full dump.
- **Spawn all teammates in a single message** to maximize parallelism.
- **Missing Email Landscape is not an error** — the seed will work without email content, it just won't have body content for email records.
