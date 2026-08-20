---
key: doc-research-synthesis
model: Document
title: "Redline Co-pilot — Research Synthesis (Draft)"
creator: !ref emma
sharing: organization
---

# Redline Co-pilot — Research Synthesis (Draft)

**Status:** In progress. Findings below are based on 4 of 6 sessions. Last two sessions next week; I'll update the doc after.

## Method

Six 60-minute semi-structured interviews with senior associates in commercial contracts or M&A practices at AmLaw 100 firms. Recruited through the Watershed network and one warm intro from Amira. Each session: walk-through of a recent redline, think-aloud on our current co-pilot prototype, and structured questions about current workflow frustrations.

## Participants (completed)

- **P1** — 5 YOE, commercial contracts, AmLaw 50 Chicago firm
- **P2** — 7 YOE, M&A, AmLaw 25 NY firm
- **P3** — 4 YOE, commercial contracts, AmLaw 75 Midwest firm (Keating-similar)
- **P4** — 6 YOE, commercial contracts, AmLaw 100 DC firm

Still to complete: P5 (M&A, AmLaw 10 NY), P6 (commercial contracts, AmLaw 150 West Coast).

## Findings so far *(in progress — will update)*

### 1. The first-pass redline is cognitively expensive

Every participant framed the first-pass redline as "the least interesting part of my day, but the part where I cannot afford to be wrong." They slow down because they are afraid of missing something, not because the individual decisions are hard. The cost is vigilance, not judgment.

**Implication:** we should not frame the product as "making redlines easier." We should frame it as "letting the lawyer stop being vigilant on the parts where their playbook already has an answer."

### 2. Trust is earned by being right on the things they already know

Every participant did the same thing with our prototype: they picked a clause they had a strong opinion about and watched what the co-pilot did. If the co-pilot's proposed redline matched what they would have written, trust was built. If it didn't, they wrote off the tool for the session.

**Implication:** the co-pilot's first 20 cited redlines per user matter more than its next 2,000. We need to prioritize accuracy on the high-frequency clauses (indemnity caps, termination, limitation of liability, DPA basics) above coverage breadth in a session.

### 3. Playbook fidelity > fluency

Three of four participants said a variation of "I would rather the co-pilot say 'I don't know' than invent a redline." Hallucinations that look confident got the strongest negative reactions. Two participants mentioned an existing tool by name (not ours) and specifically said it had lost their trust this way.

**Implication:** Leo's PRD is right to make the ground-truth audit first-class. It should also be visible to the individual lawyer during review, not just to the firm's innovation team.

### 4. The "what about the clauses it can't handle" question is alive

P3 specifically said: "If I still have to read every clause anyway because I can't tell which ones it handled, you haven't helped me." This maps to Maren's coverage-first memo almost exactly. She hadn't read the memo.

**Implication:** strong independent support for the coverage-as-GA-gate argument. The product fails if the lawyer can't trust that the co-pilot has opined on every relevant clause or flagged the ones it didn't.

### 5. Review surface preferences split on experience

The more senior the lawyer, the more they want a diff-style review with every change shown and easy reject. Junior-leaning participants liked a more curated "here are the 10 things we changed" summary view. We will need both.

## What Remains

Two sessions next week. Then I want to test two specific things: (1) whether coverage transparency (a "we redlined 92 of 100 clauses — here are the 8 we left to you" statement) changes trust, and (2) whether the Word-plugin UX beats the web app UX for senior associates.

## Appendices (redacted transcripts)

Session transcripts are in the research-raw folder, PII redacted by Rhea.
