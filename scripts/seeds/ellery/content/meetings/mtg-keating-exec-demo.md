---
key: mtg-keating-exec-demo
model: Meeting
title: Keating & Marsh Exec Demo
creator: !ref tessa
collection: !ref collection-ellery
scheduled_at: !relative_day {offset: -5, hour: 14, tz: America/New_York}
duration_minutes: 60
attendees:
  - !attendee {user: tessa, is_organizer: true}
  - !attendee {user: darren}
  - !attendee {user: mateo}
  - !attendee {user: maren}
agenda: |
  - Darren warm-up (5m) — framing, brief company state
  - Mateo demo (30m) — redline co-pilot + playbooks on a real Keating-style contract
  - Maren Q&A (15m) — legal credibility and contract-type coverage questions
  - Peter's questions (10m)
summary: |
  ## Summary
  Ellery ran its most important Keating session to date — a 60-minute exec demo for Peter Nakagawa and Amira Saleh, two of the Keating partners driving the buying decision. Darren, Mateo, and Maren ran the session across four agenda segments and left with clear positive signals. Peter and Amira asked hard questions and got direct answers. The relationship ended the meeting feeling more like a partnership conversation than a vendor pitch.

  ### Key Points
  - **Demo landed on the key moment:** Mateo ran the redline co-pilot on an anonymized pharma vendor agreement. Peter stopped the demo when the model caught a non-obvious limitation-of-liability carve-out — "Stop there. How did the model know that?" Mateo's explanation of the dual-signal (playbook + training corpus) satisfied both partners.
  - **Maren anchored on trust:** Amira pushed on training data sourcing and customer data separation. Maren was direct: "We do not train on customer contract data. Ever. That's the commitment, it's in the DPA, and it's the commitment I'd personally lose sleep over if we broke." Amira accepted the answer.
  - **"Model is never the final word":** Peter asked what happens when the model gets it wrong. Maren's answer — that every suggestion is a suggestion and the lawyer always has final say — was the framing Peter needed. He confirmed, "Okay. The lawyer is always the final word."
  - **Darren reframed the relationship:** Peter's closing question — "What's the one thing you want us to stop doing?" — gave Darren an opening to reposition the deal as a partnership, not a vendor transaction. Peter responded: "Good answer." Amira: "It's the right answer."

  ### Challenges & Risks
  - **Deal still in motion:** The demo went well, but three CISO security questions remain open and the DPA is still in redline. The team left energized but aware the deal is not closed.

  ### Agenda Review
  - **Missed Topics:** None — all four segments ran as planned.
---
[Darren]: Peter, Amira — thank you for the hour. Before Mateo takes you through the product, I want to set a brief frame. Ellery exists because we believe contract work is the highest-leverage place to put AI inside a legal org. Not because it's impressive — because lawyers do the same ten redlines every week, and that's the work AI should take off their plate. The rest of the hour is Mateo showing you what that looks like in practice, Maren fielding the legal questions, and you telling us what would make this actually work for Keating. Over to Mateo.

[Mateo]: Thanks, Darren. I'm going to load an anonymized vendor agreement — I've picked something shaped like the work your team would do, pharma adjacent, third-party vendor, data handling clauses. You'll see Ellery open the contract in the reviewer, pull in your playbook — and here, for the demo, I've loaded a playbook modeled on the one Keating's DPA team uses, which Amira was generous enough to share a redacted version of — and then start running.

[Mateo, demo running]: First thing you'll notice — the model doesn't redline everything. It suggests edits only where it's high confidence and the playbook has a clear position. You can see here on the limitation-of-liability clause — the model's flagged the carve-out language because it doesn't match the playbook's carve-out for gross negligence. That's the kind of thing a junior associate misses if they've only read the clause three times.

[Peter]: Stop there for a second. How did the model know that?

[Mateo]: Great question. The model has two inputs on this clause — your playbook, which encodes the position Keating wants to hold, and the training corpus, which gives the model the pattern-matching for "limitation of liability clauses usually have a gross negligence carve-out." When both signals agree, it suggests the edit. When they disagree, it flags without suggesting.

[Peter]: And if we didn't have a playbook?

[Mateo]: You'd still get the flag, because the pattern is common enough that the model knows it. You wouldn't get a suggested edit, because we don't want to suggest language Keating hasn't endorsed.

[Amira]: That's the right default.

[Mateo, continuing]: A few more quick ones. Data handling section — the model's caught a residency ambiguity and is suggesting the Keating-preferred language. Assignment clause — clean, no flag. Notices clause — flag, because the addresses block is the one Keating wants standardized. I'll pause there — I could do this for thirty minutes, but I'd rather spend the time on your questions.

[Amira]: Maren, I have a few. The training data question first. Where does the model learn what a "usually carved-out" liability clause looks like?

[Maren]: Our training corpus is public filings — SEC, SEDAR, UK Companies House — plus the playbooks customers share with us under the same confidentiality terms your own team would demand. We do not train on customer contract data. Ever. That's the commitment, it's in the DPA, and it's the commitment I'd personally lose sleep over if we broke.

[Amira]: How do we verify that?

[Maren]: You verify it the same way you verify any vendor claim — the DPA, the SOC 2 audit, and our willingness to answer specific technical questions from your CISO. We have the architecture diagrams and we have the test evidence. Priya can walk your CISO through both.

[Peter]: What happens when the model gets it wrong?

[Maren]: The model gets things wrong. Our product exists on the premise that a lawyer is in the loop. Every suggestion is a suggestion — a lawyer accepts it or rejects it. We track acceptance rates in a way that surfaces systematic errors so we can improve, but the model never autonomously changes a contract.

[Peter]: So the model is never the final word.

[Maren]: Correct. The lawyer is always the final word.

[Peter]: Okay. I have a closing question I ask every vendor who gets this far. What's the one thing you want us to stop doing?

[Darren]: That's the question I've been hoping you'd ask. If we work together, the thing I'd want Keating to stop doing is treating vendor selection as a zero-sum pricing exercise. This isn't a commodity. The value of Ellery to your team is proportional to how closely your playbooks and our product co-evolve. If this ends up as a transactional vendor relationship, we'll deliver a tool. If it ends up as a partnership, we'll deliver the system you actually want.

[Peter]: Good answer.

[Amira]: It's the right answer.

[Tessa]: Peter, Amira — thank you. I'll send a follow-up package by end of day with the materials we referenced. Darren will write you directly later this week.
