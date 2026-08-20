---
key: doc-redline-prd
model: Document
title: "Redline Co-pilot — PRD v1"
creator: !ref leo
sharing: organization
---

# Redline Co-pilot — PRD v1

**Status:** Draft, in review.
**Author:** Leo.
**Reviewers:** Maren, Priya, Jordan, Emma, Rhea.

## Problem

Lawyers spend a disproportionate share of their day on first-pass contract redlines that follow their firm's playbook. The work is necessary, but it is not where their judgment is most valuable. Existing AI tools in the category either (a) ignore the firm's playbook and produce generic markup, or (b) make things up. In both cases the lawyer spends as much time verifying as they would have spent redlining.

Our opportunity is to build a co-pilot that does the first-pass redline correctly against the firm's own playbook, cites every change to a provision, and is transparent when it doesn't know.

## Users

**Primary:** senior associate at an AmLaw 100-200 firm, commercial contracts or M&A practice. They have 4-8 years of experience, strong opinions about the firm's playbook, and are measured on matter cycle time.

**Secondary:** practice partner. Reviews the senior associate's work. Cares about quality and about client perception. Not a hands-on user of the co-pilot but a key stakeholder.

**Tertiary:** innovation/practice-ops lead. Owns tool rollout, training, and the "is this working" question. Not a user day-to-day but critical to adoption.

## What Redline Co-pilot Is

- A first-pass redline tool that takes a contract + the firm's playbook and produces marked-up changes in Word with comments citing the specific playbook provision for each change.
- A review surface where the lawyer sees every proposed change, accepts/rejects/edits inline, and the tool learns from those decisions.
- A ground-truth audit tool: every redline is compared against senior-reviewed baselines so we can show the firm exactly when and why the co-pilot is wrong.

## What Redline Co-pilot Isn't

- Not an authoring tool. We do not generate contracts from scratch.
- Not a negotiation tool. We don't predict counterparty moves.
- Not a playbook *authoring* tool. The firm maintains its playbooks. We ingest and respect them.
- Not a general legal research tool.

## Scope for v1

- **Matter types:** commercial contracts only (MSA, NDA, SOW, DPA). M&A in v2.
- **Document formats:** .docx ingestion and export. PDF import with OCR in v1.5.
- **Playbook formats:** structured (firm's own authoring in our format) and semi-structured (ingested from existing firm-authored docs via onboarding).
- **Review surface:** web app with Word plugin in v1.5.
- **Ground truth:** senior-associate-level review of every redline during pilot; formal audit reporting.

## Non-scope for v1

- Custom fine-tuning per firm (enterprise-tier only in v2)
- Outside-counsel/firm-to-firm workflows
- Matter intake and triage
- Post-signature contract lifecycle (separate product area)

## Risks

1. **Playbook coverage breadth.** If we can only redline 60% of the clauses in a typical MSA, the co-pilot falls short of "first-pass complete." Maren's counter-memo calls this out sharply. Mitigation: the coverage-first gating before GA.
2. **Hallucination in citations.** The worst failure mode is a confident citation to a playbook provision that doesn't say what we claim. Mitigation: retrieval-grounded citation validation + an auditor that flags any citation that cannot be verified.
3. **Word-plugin install friction.** If the enterprise IT review for the plugin is 6 months, our Word integration is pilot-bounded. Mitigation: web-first in v1, plugin in v1.5 on a separate deployment track.
4. **Competing procurement noise.** Harvey sells against us as "shallower but safer." Differentiation is our playbook fidelity and our ground-truth transparency.
