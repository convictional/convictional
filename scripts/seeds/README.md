# Seeds

Realistic demo data scenarios for the Convictional app.

## Quick Start

```bash
make db_seed                             # Seed all scenarios
make db_seed ARGS="ellery"               # Seed a specific scenario
make test_seeds                          # Dry-run all scenarios, rolled back
```

## Creating a New Scenario with Claude

```bash
cd scripts/seeds && claude
```

### Step 1: Write the story

```
/write-story A 20-person climate tech startup navigating its first product pivot
```

Iterate until you're happy, then approve. The story saves to `scripts/seeds/{scenario}/story.md`.

### Step 2: Clear context

Stories can be long. Start a fresh conversation before implementing:

```
/clear
```

### Step 3: Implement the seed

```
/implement-seed {scenario_name}
```

This launches parallel agents to generate content files, avatars, meeting videos, and scaffolding, then runs tests to verify.

## Chat Content Format

Chats live in `content/chats/*.yaml` — one YAML file per chat. The format
mirrors the structured nature of chat data (messages are records, not prose).

```yaml
# content/chats/exec-chat.yaml
key: exec-chat
name: "Exec"
group: exec                   # optional; Group seed key. Omit for DMs/multi.
members: [maren, darren, priya]
messages:
  - key: exec-chat-msg-001
    author: darren
    at: !relative_day {offset: -7, hour: 9, minute: 15}
    content: |
      First board check-in is in 5 weeks.
    reactions:
      thumbs_up: [maren, priya]
  - key: exec-chat-msg-002
    author: maren
    at: !relative_day {offset: -7, hour: 9, minute: 22}
    reply_to: exec-chat-msg-001   # references another message key
    content: |
      Love the frame.
```

Notes:
- `members:` creates `Collaborator` rows on the chat's workspace (mirrors production via `Chat.upsert_collaborators`). The first-listed member is the chat's creator.
- `group:` optionally links the chat to an existing `Group` (via seed key). For chats without a group (DMs/multi), `collaborators_hash` is computed from the member keys for uniqueness.
- `reply_to:` references another message by seed key in the same file.
- `reactions:` keys are `ReactionType` enum string values (`thumbs_up`, `thumbs_down`, `tears_of_joy`, `party_popper`, `frowning_face`, `heart`, `rocket`, `eyes`). Values are lists of user seed keys which are resolved to user IDs.
- After all messages are seeded, `Chat.last_message` and `last_message_at` are updated to point at the final message.

## Document Content Format

Documents live in `content/documents/*.md` — one markdown file per document, using the standard markdown + YAML frontmatter pattern. The paired `Workspace` is auto-created by `WorkspaceMixin`. The document body is stored in a Yjs-backed `LiveDocument` by a post-create hook.

```markdown
---
key: hiring-plan
model: Document
title: "Series A Hiring Plan"
creator: !ref darren
sharing: organization     # or omit for `private` (default)
---

# Hiring Plan

Body content as markdown.
```

Notes:
- `sharing: organization` makes the document visible to the whole org.
- `sharing: private` (default) restricts to collaborators.
- The markdown body becomes the document's initial `LiveDocument` content.
- Use `!ref <user-key>` for the `creator` field (same convention as every other seed file).
- Documents are seeded alongside goals/meetings/posts via `cs.seed_dir("documents")` in the scenario's `__init__.py`.

## Google AI Prerequisites

Avatar and meeting video generation use Google AI APIs. Both are optional — seeds work without them.

**Avatar generation** works with any of these (checked in order):
1. `GEMINI_API_KEY` in `.env.secrets`
2. `GOOGLE_CLOUD_PROJECT` + Application Default Credentials (`gcloud auth application-default login`)
3. Active `gcloud config` project

**Meeting video generation** (Google Veo) requires a `GEMINI_API_KEY` — Vertex AI is not supported for this API. Add it to `.env.secrets`:

```
GEMINI_API_KEY=your_key_here
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey).
