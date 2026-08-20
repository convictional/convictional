---
key: body
model: PostComment
user: !ref leo
post: !ref post-product-principles
created_at: !relative_day {offset: -15, hour: 16, tz: America/New_York}
updated_at: !relative_day {offset: -15, hour: 16, tz: America/New_York}
---
A first pass at product principles. Not commandments — starting points for arguments.

1. **Lawyer-legible.** If a senior associate can't justify the output to their partner in one sentence, we haven't shipped it yet.
2. **Playbooks over prompts.** Our durable advantage is the depth of the clause-level playbook, not a clever system prompt.
3. **Show the work.** Every AI output is grounded in a clause or a precedent the user can click through to.
4. **No silent magic.** The user always knows which parts of a document the model has read, and which it hasn't.
5. **Good defaults, explicit overrides.** 80% of users never touch settings; the 20% who do have everything they need.

These are v0. I'd rather argue about #2 than anything else — we keep ending up in debates where the answer is "better prompt" and I think it's a trap.
