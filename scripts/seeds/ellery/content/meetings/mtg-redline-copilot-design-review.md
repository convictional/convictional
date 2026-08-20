---
key: mtg-redline-copilot-design-review
model: Meeting
title: Redline Co-pilot Design Review
creator: !ref leo
collection: !ref collection-ellery
scheduled_at: !relative_day {offset: -11, hour: 14, tz: America/New_York}
duration_minutes: 60
attendees:
  - !attendee {user: leo, is_organizer: true}
  - !attendee {user: emma}
  - !attendee {user: jordan}
  - !attendee {user: theo}
  - !attendee {user: priya}
agenda: |
  - Walk the prototype — what the feature looks like in the reviewer flow
  - The retrieval story — where the co-pilot gets its grounding
  - Eval design — what success actually looks like
  - Where it lives in the UI — side panel, inline suggestions, or both?
summary: |
  ## Summary
  Leo walked his Redline Co-pilot prototype with Emma, Jordan, Theo, and Priya in a 60-minute design review. The meeting surfaced three real tensions — where suggestions should live in the UI, whether to require a benchmark set before shipping, and whether the full retrieval architecture is worth its engineering cost. No final decisions were made; Leo took the options to a PRD addendum to bring to Darren.

  ### Key Points
  - **Feature concept:** The co-pilot lives in the reviewer panel, grounded in three sources — the customer playbook, the lawyer's own edit history, and a retrieval layer over similar clauses. It can answer questions or proactively surface suggestions.
  - **Emma pushed for inline over side panel:** Emma argued that side panels get ignored after two weeks of use, based on AI assistant research. "The side panel means invisible." Leo's concern is that inline suggestions feel intrusive; Emma's counter is that invisible means unused. Emma will prototype two inline patterns.
  - **Jordan set a hard requirement on evals:** Jordan wants a benchmark set of 500 representative contract clauses with known correct redlines before any production code ships. "If we don't have that, we can't tell whether the model is actually improving or whether we're shipping on vibes." Leo accepted.
  - **Priya flagged retrieval cost:** Priya estimated the historical edit learning layer at roughly two ML-engineer-months plus infrastructure. She asked whether playbook-only retrieval could get 70% of the experience at 20% of the cost. Leo pushed back but took it as an open question for the PRD addendum.

  ### Challenges & Risks
  - **Retrieval architecture is unresolved:** The team did not decide whether to build the full historical learning layer. This is a significant scope and cost question that Darren and Maren need to weigh in on — Priya noted explicitly that "this isn't a product-only call."
  - **No founders in the room:** The design review happened without Darren or Maren, which means the retrieval scope decision was deferred. Leo committed to bringing the options to Darren by Monday.

  ### Agenda Review
  - **Missed Topics:** Where the co-pilot lives in the UI was debated but not resolved — Emma is prototyping two patterns for the follow-up. Eval design was addressed but the benchmark set is a future work item, not yet built.
---
[Leo]: Thanks for the hour, everyone. I want to walk the prototype and then open it up. This is the version of the co-pilot I think is worth building — and I want to know where each of you has concerns.

[Leo, demoing]: The co-pilot lives in the reviewer panel. The lawyer is working through a contract; the co-pilot is always there, grounded in three things: the playbook for this customer, the lawyer's own history of accepted and rejected edits, and a retrieval layer that pulls similar clauses from our corpus. The lawyer can ask it questions — "should this carve-out include gross negligence" — or the co-pilot can proactively surface a suggestion when it sees something the playbook or the history would flag.

[Emma]: Leo, I want to stop you on the "always there in the side panel" framing. Every piece of research I've seen on AI assistants says the side panel gets ignored after week two. If we want this to be the surface, the suggestions have to be inline in the contract itself. Highlighted. Clickable. The side panel is a conversation log, not a feature surface.

[Leo]: I hear you. My concern with inline-first is that it's more intrusive. Lawyers don't want the model to feel like it's writing the contract for them.

[Emma]: Inline doesn't mean intrusive. It means visible. The side panel means invisible. We'll end up with a feature that tests great in demos and gets abandoned in production.

[Jordan]: I want to pile on Emma's point from a different direction. If we're serious about this feature, the thing we have to measure is acceptance rate of suggestions. If the suggestions aren't visible, we can't measure them. And we should not build this feature without committing to a benchmark set before we ship production code.

[Leo]: What benchmark set?

[Jordan]: A set of, say, five hundred representative contract clauses with known correct redlines, sourced from real customer work. We run every iteration of the model against that set and we track acceptance and false positive rates. If we don't have that, we can't tell whether the model is actually improving or whether we're shipping on vibes.

[Leo]: That's a lot of work.

[Jordan]: It's three weeks of Rhea's time with structure from me. It's less work than shipping a feature that doesn't work and having to debug it from customer complaints. I want the benchmark set to be a hard requirement.

[Priya]: I want to raise a harder question. Leo, the retrieval architecture as you've described it has a real engineering cost. The playbook lookup is easy — we have that. The historical edit learning is the hard part — we're proposing a fine-tuning loop or a retrieval layer over the user's own history. My back-of-envelope is two ML-engineer-months plus infrastructure to ship that. Is there a version of this where we get seventy percent of the experience with twenty percent of the cost — playbook-only retrieval, no historical learning?

[Leo]: My instinct is that the history is what makes this feel magical. Without it, the co-pilot is just a fancy playbook lookup.

[Priya]: I'm not saying you're wrong. I'm saying the decision of "do we spend two ML-engineer-months on the history layer" is a decision the team should make deliberately, not absorb as part of the PRD. The cost matters.

[Leo]: Okay. Let me take that as an action. Jordan — want to co-write a PRD addendum with me on the retrieval design? I want it to be explicit about the two options and what we give up if we take the simpler one.

[Jordan]: I can do that. I'll have a draft by Friday.

[Theo]: One UI question that hasn't come up. If Emma is right and inline is the primary surface — which I think she is — I need to know how the suggestions interact with the existing redline interface. Right now the lawyer clicks a clause, edits it, and moves on. The co-pilot suggestions need to layer on that interaction model, not replace it.

[Emma]: I'll prototype two inline patterns by next week. One is a gentle highlight — the co-pilot has a suggestion, click to see it. The other is proactive — the suggestion is rendered inline as a suggested replacement that the lawyer can accept or dismiss. We test both.

[Leo]: Good. This is the session I wanted. I'll own the PRD addendum with Jordan and we'll reconvene in a week.

[Priya]: One thing before we close. Whatever we decide here, the decision needs to go to Darren and Maren. This isn't a product-only call.

[Leo]: Agreed. I'll bring the options to Darren by Monday.
