---
key: mtg-engineering-hiring-deepdive
model: Meeting
title: Engineering Hiring Deep-Dive
creator: !ref priya
collection: !ref collection-ellery
scheduled_at: !relative_day {offset: -10, hour: 11, tz: America/New_York}
duration_minutes: 60
attendees:
  - !attendee {user: priya, is_organizer: true}
  - !attendee {user: darren}
  - !attendee {user: arjun}
agenda: |
  - Approve the SRE-first ordering for the three engineering hires
  - Profile for the integrations engineer (scope, bar, ideal background)
  - Sourcing plan for each role and who owns the loop
summary: |
  ## Summary
  Priya, Darren, and Arjun met to align on the order and shape of three engineering hires. The meeting confirmed SRE first and ML engineer second, but left the integrations engineer role unresolved for one more week while Darren and Tessa align on whether it should be a platform engineer or a customer-facing solutions engineer.

  ### Key Points
  - **SRE-first ordering approved:** Priya made the case that the ingestion pipeline is the thing most likely to break under enterprise load, not Keating feature requests. Arjun backed it directly: "I'd rather hire someone whose job is to sleep worrying about that than keep asking Theo to context-switch." Darren gave a soft yes.
  - **ML engineer profile clarified:** When Darren asked whether the ML hire should prioritize evals at scale or applied ML in messy domains, Priya said she'd take applied ML if forced to choose — "evals we can build on top of; judgment in messy domains is harder to import."
  - **Integrations engineer deferred:** Darren is not convinced the role should be a platform integrations engineer rather than a founding SE who can scope customer work and build it. He and Tessa will sync before the req goes live.

  ### Challenges & Risks
  - **Engineer vs. SE tension:** Arjun flagged that the SE path carries a real risk — "I'd rather have an engineer who can refuse a bad architecture than an SE who can close a deal" — given that Ellery is integrating with eleven different contract management systems. The team did not resolve this.
  - **Scope creep risk on integrations hire:** Darren's concern is that a pure platform engineer leaves Tessa short on enterprise calls. A one-week delay is manageable, but if the framing stays unresolved it could slip the req further.

  ### Agenda Review
  - **Missed Topics:** Integrations engineer profile and sourcing plan for that role were not finalized — deferred pending Darren-Tessa sync.
---
[Priya]: Thanks for making the time. I want to walk the three engineering hires and get us aligned on ordering — because I've been living in Lever for two weeks and I'd like to stop debating this with myself.

[Darren]: Go for it.

[Priya]: The proposal is SRE first, ML engineer second, integrations engineer third. I know the instinct is to hire for whatever is on fire — and right now what's on fire is Keating asks — but the thing that will actually hurt us in the next ninety days is the ingestion pipeline under enterprise load. We need an SRE in the door before we have a customer with a 24/7 expectation.

[Arjun]: I'll reinforce that. The pipeline is fine for eighteen mid-market customers. It is not fine for Keating plus two more AmLaw deals behind them. I'd rather hire someone whose job is to sleep worrying about that than keep asking Theo to context-switch between product work and on-call.

[Darren]: I hear you both, and I think I'm a soft yes on SRE first. What I want to push back on is the integrations engineer as written. Tessa and I have been going back and forth on whether that role is really a platform integrations engineer or whether it's closer to a founding SE — someone who can sit on customer calls, scope the work, and then also build it.

[Priya]: Those are different people.

[Darren]: I know. That's the thing I want another week on. If we hire someone who only writes integration code, I think we leave Tessa short-handed on the enterprise calls where customers ask "what will this look like in our stack." If we hire an SE, we get someone who can do the discovery, but they might not be the strongest engineer we'd otherwise recruit.

[Arjun]: My concern with the SE path is that the code quality on integrations work is going to get real hairy real fast. We're plugging into eleven different contract management systems. I'd rather have an engineer who can refuse a bad architecture than an SE who can close a deal.

[Priya]: Let me frame it differently. What if we ship the SRE req now — I have a draft JD — and we give ourselves one more week to align on the integrations role? I'd rather delay by a week than hire for the wrong shape.

[Darren]: That works. One more week. I'll get with Tessa tomorrow.

[Priya]: Great. Arjun — can you write the "what breaks first" memo I asked you about? I want candidates to walk in understanding exactly what they'd be signing up for.

[Arjun]: I can have it done by Friday. I'll keep it to one page.

[Darren]: One more thing, Priya — the ML engineer profile. You want someone who's done evals at scale, or someone who's shipped applied ML in a messy domain?

[Priya]: Both, ideally. Realistically, we take whichever one shows up first and is great. But I'd lean applied ML if I have to choose. Evals we can build on top of. Judgment in messy domains is harder to import.

[Darren]: Agreed. Let's go.
