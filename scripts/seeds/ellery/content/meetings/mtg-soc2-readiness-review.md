---
key: mtg-soc2-readiness-review
model: Meeting
title: SOC 2 Readiness Review
creator: !ref priya
collection: !ref collection-ellery
scheduled_at: !relative_day {offset: -4, hour: 11, tz: America/New_York}
duration_minutes: 45
attendees:
  - !attendee {user: priya, is_organizer: true}
  - !attendee {user: arjun}
  - !attendee {user: maren}
agenda: |
  - Audit scope — what's in, what's deferred to Type II
  - Gap analysis — controls we have, controls we need to build
  - Credible timeline — what can we commit to in 3 weeks for Keating?
  - Evidence collection — who owns which artifacts
summary: |
  ## Summary
  Priya, Arjun, and Maren met with Brandt Soh from Halden & Rossi for a 45-minute SOC 2 readiness review. Brandt's read was encouraging — Ellery's technical controls are real for a Series A company — but the policy documentation is thin. The meeting produced a clear gap list, named owners for each item, and a credible 3-week path to a Type I report timed to Keating's implicit expectation.

  ### Key Points
  - **Brandt's overall read:** Ellery is further along than most Series A companies. The technical controls exist. What's missing is the documentation that turns "we do this" into "we demonstrably do this, on a schedule, with evidence, reviewed by a named person."
  - **Five-item gap list:** Documented access review cadence, formal onboarding/offboarding checklist, vendor risk management policy, a versioned incident response runbook (one exists but isn't versioned), and EU encryption-at-rest attestation (conditional on the residency ADR work already underway).
  - **Ownership assigned:** Arjun owns the technical artifact — a control matrix for Brandt to walk through the following Monday. Maren owns the four paperwork items, targeting drafts in 7 days using Halden & Rossi templates. Priya owns the timeline and weekly check-in with Brandt.
  - **Type II planning flagged:** Brandt noted that Keating will ask when the Type II observation window starts. Starting it the day Type I is complete puts a Type II report ready around the time the renewal conversation begins.

  ### Challenges & Risks
  - **Policy draft deadline is the critical path:** Brandt was explicit — if Maren's drafts slip past day 10, the 3-week Type I timeline falls apart. Maren proposed a Wednesday red-team session with Priya and Arjun before sending anything to Brandt.
  - **EU attestation is dependent:** The encryption-at-rest attestation for the EU region can't happen until the residency ADR implementation is live. Arjun confirmed that work is on track for 2 weeks — inside the 3-week window.

  ### Agenda Review
  - **Missed Topics:** None — all four agenda items were covered.
---
[Priya]: Brandt, thanks for making the time. You've seen our current state — what's your honest read?

[Brandt]: Honest read: you're further along than most Series A companies I walk through this with. The technical controls are real. What you're missing is the paperwork around the controls — the stuff that turns "we do this" into "we demonstrably do this, on a schedule, with evidence, reviewed by a named person."

[Priya]: Give me the specifics.

[Brandt]: I have five. One — your access reviews are happening, but they aren't on a documented cadence and I don't see evidence of who approved what. Two — onboarding and offboarding is done well but there's no checklist artifact. Three — vendor risk management is informal. You evaluate vendors but there's no policy. Four — incident response — you have a runbook, but it lives in a doc somewhere and it isn't versioned. Five — encryption at rest for the EU region isn't attested because you haven't built the EU region yet. That last one I'll treat as conditional on the residency work.

[Arjun]: The EU piece is on the critical path for Keating anyway. We're going to have the storage and routing in place in 2 weeks. The attestation will follow.

[Brandt]: Good. Then the five-item list collapses to four paperwork items plus one implementation dependency.

[Maren]: Let me take the paperwork. Access review cadence, onboarding/offboarding checklist, vendor risk policy, incident response. I can draft those in the next week. I'll use the Halden & Rossi templates you sent last month as a starting point.

[Brandt]: That's the right move. I'll review your drafts in flight — don't wait for them to be finished before you send them.

[Priya]: What's the realistic timeline to Type I?

[Brandt]: If Maren's drafts are in in 7 days and we close them by day ten, we can start the audit window and have a Type I report in 3 weeks. That's tight but not crazy. The thing that slips is if any of the technical controls turn out to have gaps we haven't found yet. Do you have a control matrix I can walk through with Arjun next week?

[Arjun]: I can have one by Monday. It'll be honest — I'll flag everything I'm not sure about rather than pretend we're cleaner than we are.

[Brandt]: That's the only way this works.

[Priya]: Keating's expecting Type I in 3 weeks. They haven't said it in those words but it's the implicit commitment. I want to make sure we can hit it.

[Brandt]: You can hit it. You can't hit it if the policy drafts slip past the ten-day mark. That's the thing to watch.

[Maren]: Priya, let's block an hour on Wednesday for me to walk the draft policy set. I want you and Arjun to red-team it before it goes to Brandt.

[Priya]: On the calendar.

[Brandt]: One more thing — you should start thinking about Type II. The Type I is a point-in-time attestation. Keating will buy against it, but they're going to ask when the Type II window starts. Six months of observation is standard. If you start the window the day you finish Type I, you'll have a Type II ready around the time the renewal conversation starts. That's the right rhythm.

[Priya]: We'll plan for that explicitly. Thanks, Brandt.

[Brandt]: Good meeting. See you Monday for the control matrix walk.
