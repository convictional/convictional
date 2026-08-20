---
key: mtg-keating-deal-review
model: Meeting
title: Keating Deal Review
creator: !ref tessa
collection: !ref collection-ellery
scheduled_at: !relative_day {offset: -1, hour: 16, tz: America/New_York}
duration_minutes: 30
attendees:
  - !attendee {user: tessa, is_organizer: true}
  - !attendee {user: mateo}
  - !attendee {user: darren}
  - !attendee {user: maren}
agenda: |
  - Pricing revision — are we holding the pilot-credit structure?
  - CISO's three open questions from the security questionnaire
  - Legal terms — DPA status and path to signature
  - Exec air cover — what do we need from Darren this week?
summary: |
  ## Summary
  Tessa ran a tight 30-minute deal review with Mateo, Darren, and Maren to clear the four open Keating items — pricing, CISO security questions, DPA status, and exec air cover. The meeting resolved the pricing debate in favor of holding the pilot credit, routed all three CISO questions to named owners, and confirmed Maren will send Amira Saleh a clean DPA draft within two days.

  ### Key Points
  - **Pricing decision — hold the pilot credit:** Mateo pushed to drop the pilot credit now that the exec demo went well, arguing it would signal confidence. Tessa disagreed, saying it would reopen the platform fee negotiation. Darren sided with Tessa: "If we lose a month of momentum over a line item, we lose the deal." Mateo accepted.
  - **CISO questions routed:** Three open security questionnaire items were assigned — Q44 (retrieval architecture, per-tenant isolation) to Priya, Q47 (EU data handling) to Arjun, Q51 (training data provenance) to Maren with Rhea assisting.
  - **DPA on track:** Maren confirmed Amira's five redlines are workable. Three are cosmetic, one is a reasonable breach notification ask, and one data residency commitment needs careful language to align with what Ellery has actually built. Maren will send a clean draft by day 2.
  - **Exec air cover confirmed:** Darren committed to a "why I'm confident in this deal" note for the board pre-read by Friday, and unconditional availability for a Peter call next Tuesday if requested.

  ### Challenges & Risks
  - **Data residency language:** Maren flagged that Amira's data residency language commits Ellery to something not yet fully built. She will push back carefully, framing it as "aligning language with our implementation roadmap" — but this is the one DPA term that could cause friction.

  ### Agenda Review
  - **Missed Topics:** None — all four agenda items were addressed.
---
[Tessa]: Okay, thirty minutes, let's go. Pricing first. Mateo — you want to drop the pilot credit.

[Mateo]: I do. The exec demo went well, Peter's question about redline customization was softball by his standards, and Amira sent the redlines back without touching the commercial terms. I think we're overinsuring. Dropping the pilot credit puts us at a cleaner number and honestly it's the number we should have opened with.

[Tessa]: I disagree. The pilot credit was how we got them to stop negotiating the platform fee. If we pull it now, we reopen that conversation.

[Mateo]: Or we signal confidence.

[Tessa]: Or we signal inconsistency. Darren — what's your read?

[Darren]: I'm with Tessa. If we lose a month of momentum over a line item, we lose the deal. The pilot credit costs us thirty-five thousand dollars on a deal that's going to be multiples of that at renewal. Hold it.

[Mateo]: Fair. Holding.

[Tessa]: CISO's open questions. Q44 is the one about retrieval — where does the model look when it suggests a redline, and how do we prove it's not pulling from another customer's data.

[Mateo]: Priya, can you own the answer?

[Priya — from the doorway]: I can. I'll write it up today and send to Mateo for packaging. The honest answer is that retrieval is per-tenant and we have the tests to prove it, but the CISO wants the architecture diagram and the test evidence. I'll include both.

[Tessa]: Q47 is EU data handling.

[Priya]: Arjun is the best person on that. I'll loop him in.

[Tessa]: Q51 is training data provenance. Maren?

[Maren — dialing in]: I can take that with Rhea. Our training data is our playbooks plus public filings — no customer data. I'll write a one-pager that the CISO can hand to their privacy counsel. Two days.

[Darren]: Good.

[Tessa]: Legal terms. Maren, DPA status?

[Maren]: Amira's redlines are workable. Three of the five changes are cosmetic, the fourth is a reasonable ask about breach notification timing, the fifth is a data residency commitment I want to push back on slightly — not because I disagree, but because the language they wrote commits us to something we haven't technically built yet. I want to align our commitment to the residency ADR Priya and Arjun walked last week.

[Darren]: Can you write the pushback so it doesn't sound like we're retreating?

[Maren]: Yes. It'll read like "we're aligning language with our implementation roadmap." I'll send Amira a clean draft by day 2.

[Tessa]: What do we need from Darren this week?

[Darren]: What do you want?

[Tessa]: Two things. One — a short "why I'm confident in this deal" note I can include in the pre-read for the board. Two — availability for a fifteen-minute Peter call next Tuesday if he asks for one.

[Darren]: I'll have the note by Friday. Peter call — yes, unconditional.

[Tessa]: Thirty minutes.
