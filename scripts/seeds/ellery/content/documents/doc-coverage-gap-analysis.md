---
key: doc-coverage-gap-analysis
model: Document
title: "Coverage Gap Analysis — Top 5 Segments"
creator: !ref rhea
sharing: organization
---

# Coverage Gap Analysis — Top 5 Segments

**Author:** Rhea
**Context:** Data backing Maren's coverage-first memo. Where playbook coverage is thinnest today and by how much.

## Method

I sampled 25 representative contracts across five common commercial contract segments. For each contract, I tagged every substantive clause, then measured how many of those clauses our current playbook library (across the three customers + two pilot firms we have today) produces a cited redline for.

"Coverage" = (clauses with a playbook-cited redline) / (total substantive clauses). I'm excluding boilerplate like governing law where there is no redline to make.

## Summary Table

| Segment | Avg contract length | Avg substantive clauses | Current coverage |
|---|---|---|---|
| Master Services Agreement | ~18 pages | 48 | **72%** |
| Data Processing Agreement | ~12 pages | 34 | **81%** |
| Non-Disclosure Agreement | ~6 pages | 22 | **94%** |
| Statement of Work | ~8 pages | 28 | **68%** |
| Technology Licensing Agreement | ~22 pages | 61 | **54%** |

## Findings

### 1. We look good on NDAs, weak on MSAs

NDAs are narrow. There are maybe eight real negotiation points. We cover them well. Every firm we onboard can ride on the existing library with light tuning.

MSAs are where the pilot customers actually live. Average 48 substantive clauses. We cover 72% today. To get to Maren's 90% GA gate we need ~9 more cited clause types per firm, and they are not the same 9 across firms. Some firms care about source-code-escrow provisions, some don't. Some care about insurance endorsements, some don't. It is 9 clauses of real playbook work per firm, not one clause built once.

### 2. SOWs are worse than they look

68% sounds not-terrible but it is fragile. Most of the coverage is boilerplate acceptance language. The places where SOWs produce redline heat — change orders, milestone disputes, indemnity inheritance from the parent MSA — are exactly where we are weakest. Lawyers would feel this.

### 3. Tech licensing is currently out of reach

54% coverage. Tech licensing has more clause-level variation than MSA. Open-source provisions, audit rights, source code access, export compliance — all places we are thin. I don't think we should promise GA coverage on tech licensing this year.

### 4. The per-firm delta is the real problem

Within MSA coverage, two of our current three customers are at 68% and 77% respectively. Same segment, different firms, different playbooks, different gaps. Every new enterprise customer arrives with a unique 15-25% of playbook that we need to ingest and model.

## Recommendation

1. **MSA and DPA get GA-gated at 90%.** Achievable if we land the second content analyst in Q3 and commit 4 weeks per customer to playbook ingestion + modeling.
2. **SOW not GA-gated this year.** We offer it as "assisted" coverage with clear communication that specific clause types need human review.
3. **NDA ships with GA.** Already there.
4. **Tech licensing moved to H1 next year.** Scope for a separate project with dedicated content work.

## Staffing Implication

This is exactly what Maren's memo is about. I can own the second customer's MSA ingestion or the DPA coverage uplift. I cannot own both and be the GA gatekeeper for every new firm we sign. Hence the legal content analyst #2 hire.
