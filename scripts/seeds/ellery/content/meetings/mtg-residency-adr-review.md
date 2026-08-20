---
key: mtg-residency-adr-review
model: Meeting
title: EU Residency ADR Review
creator: !ref priya
collection: !ref collection-ellery
scheduled_at: !relative_day {offset: -6, hour: 13, tz: America/New_York}
duration_minutes: 45
attendees:
  - !attendee {user: priya, is_organizer: true}
  - !attendee {user: arjun}
  - !attendee {user: theo}
agenda: |
  - Walk Arjun's ADR — region-scoped storage, routing, key management
  - Decide what we build now versus defer to v2
  - Identify the two highest-risk assumptions
  - Commit to an implementation target aligned to Keating's three-week expectation
summary: |
  ## Summary
  Priya, Arjun, and Theo reviewed Arjun's EU data residency ADR in a 45-minute working session. The meeting resolved what to build now versus defer, identified the two highest-risk technical assumptions, and committed ownership for a v1 target of 14 days — timed to meet Keating's implicit expectation for SOC 2 attestability.

  ### Key Points
  - **Scope decided — build now vs. defer:** Region-scoped storage and routing go into v1. Full cross-region admin access policy is deferred to v2. In v1, any cross-region access attempt is denied with a clear audit log. Priya asked Arjun to document this as a limitation, not a feature.
  - **Key rotation flagged as highest-risk assumption:** Arjun's envelope encryption pattern means rotating the master key, not every DEK — so re-wrapping is lazy. But it has not been tested under ingestion load. Theo said: "That's the thing that would keep me up at night." The decision: rotation runs in a low-traffic window and staging tests happen before any rotation schedule is committed.
  - **Tenant migration is manual:** Two existing customers are EU-headquartered but currently in the U.S. region. For the first 90 days, migration is manual and only on request. Theo and Priya agreed that automating too early would bake in the wrong abstractions.
  - **Implementation split confirmed:** Theo owns the routing layer (cleanest path since he's been in the gateway code recently), Arjun owns storage and KMS, Priya shadows the CI test matrix with a focus on cross-region denial coverage.

  ### Challenges & Risks
  - **KMS rotation under load:** Arjun flagged this as his highest-risk assumption — the staging test has to happen before the rotation schedule is set. If a latency regression appears, the approach needs to be revisited.
  - **Routing dependency on schema update:** Theo's gateway work requires a tenant table schema migration from Arjun before it can ship. Arjun committed to having the migration in by the following day.

  ### Agenda Review
  - **Missed Topics:** None — all four agenda items were addressed and decided.
---
[Priya]: Arjun, thank you for the ADR. I read it this morning and I think it's mostly right. I want to push on three places before we commit.

[Arjun]: Go.

[Priya]: One — cross-region access. If Maren, logged in from New York, wants to look at an EU tenant's workspace, what happens?

[Arjun]: In v1, she can't. The request fails at the gateway with a clear audit log entry. If she needs to see it, she has to physically route through a support flow.

[Priya]: I'm fine with that for v1 but I want it documented as a limitation, not a feature. We'll need admin access patterns in v2. Can you write the explicit deferral into the ADR?

[Arjun]: Yes. I'll add a "deferred to v2" section.

[Priya]: Two — key rotation. You're proposing per-region KMS. What's the operational load on that? Specifically, when we rotate the EU region key, does the ingestion pipeline hiccup?

[Arjun]: That's my highest-risk assumption. I think it's fine because the envelope encryption pattern means we're rotating the master key, not every DEK, so the data re-wrap is lazy. But I haven't tested it under ingestion load.

[Theo]: That's the thing that would keep me up at night. If rotation introduces even a ten-second latency spike during peak ingestion, we lose Maren's trust on performance forever.

[Arjun]: Agreed. I'll design the rotation as a low-traffic-window operation and we'll test it in staging before we commit to a rotation schedule.

[Priya]: Let's put a note in the ADR that the rotation schedule is conditional on the staging test. If the test reveals a problem, we revisit.

[Arjun]: Noted.

[Priya]: Three — migration. We have two existing customers whose teams are EU-headquartered but whose tenants are in the U.S. region by default. What's the story for them?

[Arjun]: In v1, manual migration on request only, in the first ninety days. If a customer asks to move, we do it as a support-ticket-level operation. I don't want to build automated migration before we've done it by hand a few times.

[Theo]: That's right. The first five migrations are going to teach us all the edge cases we didn't anticipate. If we automate too early we'll bake in the wrong abstractions.

[Priya]: Agreed. Document as "manual, on request, first ninety days" in the ADR.

[Arjun]: Done.

[Priya]: Implementation split. Theo, can you take the routing layer?

[Theo]: I can. I've been in the gateway code the most recently — it should be a clean addition rather than a refactor.

[Priya]: Arjun owns storage and KMS.

[Arjun]: That's my lane anyway.

[Priya]: I'll shadow the CI test matrix. I want to make sure the test coverage for cross-region denial is tight — that's the thing the SOC 2 auditor is going to ask about.

[Arjun]: I'll write the test matrix before I write any code.

[Priya]: Target: v1 live and attestable by day 14. That's aligned to the Keating commitment. Any blockers?

[Theo]: The gateway work has one dependency — the routing metadata needs a schema update on the tenants table. Arjun, I'll need you to land that before I can ship.

[Arjun]: I'll have the migration in by tomorrow.

[Priya]: Thank you both. Good ADR.
