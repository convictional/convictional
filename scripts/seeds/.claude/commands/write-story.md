---
description: Write or iterate on a demo seed story (creative phase)
model: opus
---

# Write Story

You orchestrate the creative phase of demo seed generation: writing and iterating on seed stories. Stories are the narrative blueprint that guides seed code implementation.

## Initial Response

Determine your mode based on the argument provided:

### Creation Mode (argument is a scenario description)

If the argument does NOT match an existing scenario directory under `scripts/seeds/`, treat it as a new scenario description and proceed to Schema Analysis.

### Iteration Mode (argument matches an existing scenario)

If the argument matches an existing scenario directory that contains a `story.md`:

1. Read `scripts/seeds/{scenario}/story.md`
2. Present a brief summary of the existing story to the user
3. Ask: "What would you like to change about this story?"
4. Wait for the user's response, then proceed to Story Writing with the existing story and change requests

### No Argument

If no argument was provided, ask the user:

```
What kind of demo seed scenario would you like to create?

Describe the company — industry, size, stage, key tensions, or themes. For example:
- "A 30-person fintech startup struggling with alignment between engineering and product"
- "A 100-person nonprofit deciding how to allocate limited resources across programs"
- "A fast-growing e-commerce company navigating its first leadership transition"
```

Then wait for the user's input before proceeding.

## Schema Analysis

Use the `/discover-models` skill to understand the data model. Run `list` to see all models, then `order` to get creation dependencies. Skip this step in iteration mode if the changes are purely narrative (e.g., adjusting character descriptions or plot details).

**Summarize concisely** (model names, key relationships, creation order) to pass to the story writer.

Tell the user:

```
Schema analysis complete. I found [N] models across [domains]. Moving on to story writing.
```

## Story Constraints

Before prompting the story writer, read `scripts/seeds/.claude/shared-rules.md` and paste the relevant rules into your prompt. Always include these constraints (both modes):

```
Story constraints (from shared-rules.md):
[paste the Goal Titles, Subgoal Titles, Goal & Subgoal Descriptions, and Emoji Reactions sections from shared-rules.md]

Additional story requirements:
- Every character must have at least one email thread directly related to a company goal.
- The story MUST include an "Email Landscape" section as Section 9 (after Avatar Style). This section should describe the email activity for each character, organized by character heading. For each character, describe the email threads they participate in — both internal threads with other characters and external threads with outside contacts. For external contacts, specify their full identity: name, email address, company, and title. Describe thread structure (groupings, message count, sender/receiver order, content themes) but do not specify HTML file slugs — email content lives inline in `.md` content files.
- **Email volume and diversity are critical.** A realistic inbox is not 3-5 work threads. Target 10-15 threads per primary character, 6-10 per secondary character, 40-80 total. Include at least 5 of these categories across users: (1) interpersonal work emails, (2) external business conversations, (3) newsletters & digests, (4) service notifications (GitHub, CI/CD, monitoring, expense alerts), (5) transactional emails (SaaS onboarding, receipts, security alerts), (6) sales & vendor outreach, (7) community & events, (8) administrative & HR. Most threads are just inbox content — reserve collaborator comments for threads tied to goals/decisions.
- **Every character must have at least one post-notification email** in their inbox linked to a Post via `resource_ref`, spread across different posts (see shared-rules.md for details).
- The story MUST include a "Chat Landscape" section. Describe the internal chats that exist: which Groups have chats, which 1:1 DMs are active, what the recurring vibes/topics are, and roughly how many messages. Don't write message content — just structure.
- The story MUST include a "Document Landscape" section. List the documents that exist in the workspace (planning docs, process docs, design docs, retros, research notes, etc.), organized by narrative thread. Specify `title` and `creator` for each, and a 1-sentence description of what the doc contains. Don't write full document bodies — just the inventory.
```

## Story Writing

Launch the `seed-story-writer` agent using the Task tool. Include the appropriate context in the prompt:

**For creation mode:**

```
Here is the model schema summary:

[paste schema summary]

The user wants a demo seed scenario for: [user's scenario description]

[paste story constraints from above]

Craft a compelling seed story following your full instructions.
```

**For iteration mode:**

```
Here is the existing seed story:

[paste existing story]

The user wants the following changes: [user's change requests]

Revise the story to incorporate these changes while maintaining narrative coherence.

[paste story constraints from above]

Ensure the revised story follows these constraints (fix if currently violated).
```

## Present and Iterate

When the agent completes, **present the full story to the user** and ask for approval:

```
Here's the seed story:

[story content]

Does this story work for you? Feel free to suggest changes to characters, narrative beats, email threads, or emphasis.
```

**STOP and wait for user approval.** If changes are requested, re-launch the story writer agent with the feedback. Loop until the user approves.

## Save

Once approved:

1. For new scenarios, derive a directory name from the company name (lowercase, underscores). Confirm the name with the user.
2. Create the directory if needed: `scripts/seeds/{scenario_name}/`
3. Write the story to `scripts/seeds/{scenario_name}/story.md`

## Handoff

Tell the user:

```
Story saved to scripts/seeds/{scenario_name}/story.md

When you're ready to generate the seed content files, run:
/implement-seed {scenario_name}
```

## Important Rules

- **The user checkpoint after story writing is mandatory.** Never skip it.
- **Always include the Email Landscape section requirement** when prompting the story writer. This section is the contract between the story and the implementation phase.
- **If any agent fails**, report what happened and ask the user how to proceed.
- **In iteration mode**, you can make small narrative adjustments yourself instead of re-launching the agent, but for substantial changes always use the agent.
