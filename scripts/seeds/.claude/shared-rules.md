# Shared Rules for Demo Seed Generation

Canonical source of truth for rules that span multiple agents and commands.

## Time References — No T-notation

Never use rocket-launch-style `T+N` / `T−N` notation in content (e.g., "T+0", "T−4 weeks", "T+6 board meeting"). It reads as jargon and makes the seed feel artificial.

Use natural language instead:
- "3 weeks ago" / "two weeks ago"
- "today" / "this Tuesday"
- "in 6 weeks" / "six weeks from now"
- "by the end of the quarter"
- For specific dates in YAML frontmatter, use `!relative_day` or `!days_from_now` — never inline T-notation in prose.

This applies to all content types: goal descriptions, goal updates, post bodies, meeting transcripts, email bodies, chat messages, and STORY.md timelines.

## Competitor & Product-Overlap References

- Never mention Slack or any team chat/messaging tool — Slack is a direct competitor
- Never mention calendar apps — Convictional handles calendaring
- If a service notification example is needed, use non-overlapping tools: GitHub, CI/CD, monitoring, finance apps (Stripe), sales apps (HubSpot)
- Do not create partnership threads, integration requests, or feature references involving competing products

## Goal Titles

- Exactly 1-2 words (preferably 1), a concrete noun or active verb capturing the core outcome
- Examples: "Velocity", "Adoption", "Retention", "Conversion", "Discover", "Integration"
- No generic corporate jargon, no punctuation, no emojis
- Titles must be unique within the organization
- Matches the app's `GenerateGoalTitleJob` prompt in `app/prompts/goals/generate_title_system.md.jinja`

## Goal & Subgoal Descriptions

- Goal `description` contains the full OKR-style objective
- Subgoal descriptions must be measurable key results with numbers, percentages, or deadlines
- Wrong: "API", "Frontend", "Onboarding" (functional decompositions)
- Right: "Reduce API latency to <200ms", "Ship redesigned frontend to 100% of users"
- At least 3 top-level goals, each with 2-4 measurable subgoals

## Email Volume & Diversity

A realistic inbox is **not** 3-5 work-related threads. Every user should have a rich, varied inbox that mirrors what a real professional sees daily. Target **8-15 email threads per user**, drawn from a mix of these categories:

### Required Email Categories

Every scenario must include threads from **at least 5** of these categories, spread across users:

1. **Interpersonal work emails** — Direct conversations between colleagues: status updates, questions, quick requests, feedback exchanges. Casual tone, short messages, sometimes one-liners.
2. **External business conversations** — Threads with clients, vendors, partners, candidates, investors, or consultants. Professional tone with varied formality.
3. **Newsletters & digests** — Industry newsletters, company internal digests, blog subscriptions, weekly roundups. Table-based layouts, brand headers, unsubscribe footers.
4. **Service notifications** — GitHub PR reviews, CI/CD status, monitoring alerts, deployment notifications, expense system alerts. Mimic real service branding with table layouts and status indicators.
5. **Transactional emails** — SaaS onboarding sequences, subscription confirmations, receipts/invoices, password resets, security alerts. Branded table layouts with CTA buttons.
6. **Sales & vendor outreach** — Cold outreach, demo follow-ups, renewal reminders, upsell pitches. Professional signatures with title/company/phone.
7. **Community & events** — Conference invitations, meetup reminders, community forum digests, webinar follow-ups.
8. **Administrative & HR** — Benefits enrollment reminders, policy updates, expense approvals, PTO confirmations.

### Volume Guidelines

- **Primary characters** (protagonists, leads): 10-15 threads each
- **Secondary characters**: 6-10 threads each
- **Total across scenario**: aim for 40-80 email threads minimum
- Not every thread needs collaborator comments — most are just inbox content. Reserve comments/reactions for threads that relate to company goals or decisions.

### Diversity Within Threads

- Vary message count: some threads are single messages (a newsletter), others are 3-5 message conversations
- Vary time spread: some threads are recent (today/yesterday), others are days or weeks old
- Vary read/unread status: most received emails should use default labels (INBOX + UNREAD for received), but some threads should have been seen already — add explicit `labels` field with just `[inbox]` (no unread) on older messages
- Vary length: terse one-liners to detailed multi-paragraph messages
- Vary formality: casual team banter vs. formal executive correspondence vs. automated notifications

## Email Landscape Contract

The story's Email Landscape section is the single source of truth for email structure:
- Thread groupings, message counts per thread, sender/receiver order
- External contact identities (name, email address, company, title)
- The seed-data-writer agent must match the story exactly when creating `.md` content files in `content/emails/`
- Thread groupings map to directories (e.g., `content/emails/thread-recruiter/`), messages to numbered `.md` files with inline HTML body (`01-outreach.md`, `02-reply.md`), and thread comments to `comment-*.md` files

## User Groups

- Every scenario must include 2-3 role-based groups in `accounts.py` using the `_create_group` helper pattern from `ellery`
- Groups should reflect the org's functional structure (e.g., Engineering, Leadership, Design, Operations)
- Each user should belong to at least one group

## User Bios

- Every user must have a `bio` field set in `accounts.py`
- Bios should be 1-2 sentences describing the person's role and current focus area
- Professional tone, specific to the scenario narrative

## Post Body Length

- Post body content (`00-body.md`) should be approximately 100 words maximum
- Be direct and concise — real workplace posts don't read like essays
- Focus on the key question, options, or update — cut background context that readers already know

## Group Posts

- Every scenario should assign at least 2-3 posts to groups using `group: !ref <group-key>` in frontmatter
- Match the group to the post's topic — engineering posts to the engineering group, sales posts to the sales group, etc.
- Announcements (`is_announcement: true`) and org-wide social posts (e.g., welcome posts) should remain ungrouped
- The `ensure_post_group_subscriptions` signal auto-subscribes group members when a post is assigned to a group

## Pinned Posts

- Every scenario should have 1-2 pinned posts — enough to anchor the feed without overwhelming it
- Set `pinned_at` in the Post frontmatter: `pinned_at: !relative_day {offset: -7, hour: 9, tz: America/New_York}`
- Good candidates for pinning: announcements, active RFCs, ongoing decisions
- At least one pinned post should also be an announcement (`is_announcement: true`)

## Post Link Previews

- Posts that reference external URLs should include the URL in the body of the original comment (`00-body.md`)
- The `after_create(PostComment)` hook automatically extracts the first URL from the content, fetches real OG metadata via HTTP, and creates a `LinkPreview` record linked to the comment
- No special frontmatter needed — just include the bare URL in the post body (typically at the end)
- The URLs must be real, publicly accessible pages so the unfurler can fetch their metadata
- Aim for at least 3-4 posts per scenario with link previews — pick posts that naturally reference external resources (tools, articles, documentation)
- Not every post needs a link preview — short discussion posts and announcements typically don't have one

## Post Published State

- A `before_create(Post)` hook auto-sets `published_at` so all seeded posts are published by default
- No need to specify `published_at` in front matter unless you want a specific timestamp

## Announcement Posts

- Every scenario should include at least one post with `is_announcement: true`
- Announcements are org-wide communications (company priorities, policy changes, major updates) — pick posts that fit this tone

## Post Decisions

- **Every scenario must include at least 3-5 decision posts** — posts where the discussion culminates in a final decision recorded as a specific PostComment.
- The deciding comment uses `is_decision_comment: true` in its PostComment frontmatter. Typically numbered last in the post's subdirectory (e.g., `05-decision.md`) so the decision lands after the discussion it resolves.
- The `after_create(PostComment)` hook automatically sets `decided_at`, `decided_by_id`, and `decision_comment_id` on the parent Post via `post.decide()`.
- Decision comments should **name the decision clearly, cite the thread's arguments, assign owners, and set concrete next steps** — 3-6 short paragraphs in the commenter's voice. The commenter is usually the CEO or the functional DRI for whatever was decided.
- Pick posts where a decision is narratively earned: cross-functional tradeoffs, roadmap choices, hiring sequencing, go/no-go reviews. Don't mark social/announcement posts as decisions.

## Goal Updates

- Every goal and subgoal should have 3-4 GoalUpdate records showing realistic progress history
- Updates should show progression: earlier updates with lower `progress` values, later ones approaching the current state
- Each update needs `created_at: !relative_day {offset: -N, ...}` to space them over weeks (e.g., -21, -14, -7, -2 days)
- `answer_text` (the markdown body below `---`) should be 1-3 sentences referencing specific work items from the scenario
- At least one goal in the scenario should have an update that transitions from `on_track` to `at_risk` or `off_track` to show realistic variance
- The `creator` should be the goal's owner
- The `question_text` default is set by the `fields(GoalUpdate, question_text=...)` context in `__init__.py` — no need to specify it in frontmatter

## Research Response Emails

- Every user must have one research response email in their inbox
- Sender is always `"Convictional Research <research@convictional.com>"`
- Subject format: `[Research] {question}` where the question references a real decision or outcome from the scenario
- HTML body must match the production format: heading, blockquoted question, findings with superscript footnote citations, horizontal rule, disclaimer, references list
- Citations must reference real seeded content (posts, meetings, email threads, goals) by title — each research email should cite at least 3 different content types
- Every research email must include at least one meeting citation
- Citation links must use the `seed:` URL format so they resolve to real content: `href="seed:posts/post-key"`, `href="seed:meetings/meeting-key"`, `href="seed:email_threads/thread-key"`, `href="seed:goals/goal-key"`. The `ContentSeeder` resolves these to actual app URLs using deterministic UUIDs.
- Create as `content/emails/thread-research-{user}/01-response.md` directories

## Emoji Reactions on Comments

- Most `EmailThreadComment` records on email thread workspaces should include emoji reactions
- `PostComment` and `GoalComment` records can also include emoji reactions
- Use `ReactionType` from `config.enums`: `thumbs_up`, `thumbs_down`, `tears_of_joy`, `party_popper`, `frowning_face`, `heart`, `rocket`, `eyes`
- Vary reaction types across comments
- In stories, describe who reacts and the tone of their reaction

## Post Notification Inbox Items

Post notification inbox items are **native `PostMailboxEntry` records, not emails.** Do NOT create static `thread-post-*` email threads and do NOT create static `.md` files for these.

The scenario's `__init__.py` calls `cs.sync_post_mailbox_entries(org)` at the end of seeding:

```python
await cs.sync_post_mailbox_entries(people.org)
```

It automatically:
- Queries every seeded Post in the organization
- Calls `Mailbox.sync(post)` on each, which creates a `PostMailboxEntry` for every subscriber
- Each entry links directly to the Post (`resource_gid = gid://convictional/Post/<id>`), so the inbox UI renders it as a clickable post card rather than an email row

## Meeting Summaries

Seeded meeting summaries must match the structured format the app's own summary-generation prompt produces (`app/prompts/extract_meeting_metadata/generate_summary.md.jinja`) — otherwise seeded meetings look different from real ones in the UI. Use this exact structure in the YAML `summary:` field:

```
## Summary
[Single paragraph: significance + key outcomes + who-what-why.]

### Key Points
- **[Topic]:** Concrete point backed by quote or example + why it matters + decision. 2-3 sentences max.

### Challenges & Risks
- **[Challenge]:** Evidence + implications + proposed solutions or disagreements.

### Agenda Review
- **Missed Topics:** [list, or "None — all items addressed"]
```

- Always include `## Summary` and `### Key Points`.
- Omit `### Challenges & Risks` entirely if there's no real content.
- Include `### Agenda Review` only when the meeting has an `agenda:` in frontmatter.
- Attribution reads naturally: "Priya raised...", "Maren and Darren agreed...", "Arjun flagged..."
- 1-2 direct quotes per summary max — use strategically.
- Flesch-Kincaid grade level 4.0 or lower.

## Chat Volume & Structure

- Target **5-8 chats** per scenario: a mix of group chats (tied to Groups) and DMs.
- **Group chats:** 15-40 messages each. Every Group should have one chat; an "All-Hands" chat covering all users is encouraged.
- **DMs:** 10-20 messages each. Use DMs for the highest-signal 1:1 relationships (founders, deal coordinators, mentor/mentee).
- **Cross-thread coverage:** every major narrative thread should surface in at least one chat. The Exec chat is the natural crossroads.
- **Read status:** chat membership is now `Collaborator` on the chat's workspace; per-collaborator read state is no longer modeled at the chat level (read tracking moved to workspace `Visit` records, which the seed system does not yet author). Don't try to seed an "unread" feel — assume "caught up" for now.
- **Reactions:** use sparingly — 1 in 4-6 messages gets a reaction. Over-reacting feels unnatural. Use ReactionType enum string values (`thumbs_up`, `heart`, etc.) not emoji glyphs.

## Document Count & Diversity

- Target **15-25 documents** per scenario.
- **Cover all major narrative threads:** every top-level goal/thread should have at least 2-3 documents.
- **Document types to include at least one of:**
  - Planning docs (hiring plan, quarterly roadmap, OKRs)
  - Process / operating docs (rituals, rhythms, how-we-work)
  - Decision / strategy docs (option memos, decision briefs)
  - Research / analysis docs (user interviews, competitive, gap analyses)
  - Retros / postmortems (what happened, what we learned)
  - Templates & scorecards (interview guides, job scorecards, demo scripts)
- **Body length:** ~200-500 words for substantive docs; some shorter scorecard/template docs are fine.
- **Tone:** professional, internal-voice. Not blog-y. Think "real doc a real team wrote while scrambling."
