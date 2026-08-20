---
key: doc-coverage-memo
model: Document
title: "Coverage-First — A Counter-Memo"
creator: !ref maren
sharing: organization
---

# Coverage-First — A Counter-Memo

**Author:** Maren
**Context:** In response to Leo's Redline Co-pilot PRD v1.
**Recommendation at the top:** I agree with most of Leo's PRD. Here is what I think we should lock before we ship it.

## Summary

The PRD correctly identifies the product shape. It does not correctly weight the single biggest risk to our reputation with lawyers, which is **playbook coverage breadth.** I am asking us to make coverage a GA gate and to commit to a coverage metric that we report to customers.

## Why Coverage Is The Thing

A lawyer's first-pass redline is not "identify the clauses you have an opinion about and redline those." It is "go through the whole contract and make sure nothing is missing, misworded, or out-of-playbook, clause by clause." If our co-pilot handles 60% of the clauses in a typical commercial contract, the lawyer cannot trust it as a first-pass. They have to read the contract themselves anyway. In which case they've saved themselves 10 minutes on 60% of the clauses but paid for the tool.

If our co-pilot handles 92% of the clauses, they can actually accept its first pass and focus on the 8% plus whatever judgment calls the 92% surfaces. That changes the value proposition from "assistant" to "first-pass complete."

The difference between 60% and 92% is the entire product-market fit question. We have to get there before we GA.

## What I Propose

### 1. Make coverage the GA gate

Not "accuracy on the clauses we handle." Coverage. Percentage of clauses in a representative contract that the co-pilot produces a playbook-cited redline for.

Target: 90%+ on commercial contract types (MSA, NDA, SOW, DPA) for the first three firms we go live with.

If we aren't at 90% by the GA date, we slip.

### 2. Report coverage to customers

Publish it. Put it in the pilot mid-point review. "Your playbook covers X clauses; we produced cited redlines for Y%; here is the breakdown." Customers respect transparency. Competitors don't offer this. It becomes a moat.

### 3. Staff the coverage work

Rhea cannot own playbook breadth and depth for every new firm alone. I am going to ask Darren to move the second legal content analyst hire up in the sequence. If we land Keating without coverage, we lose the expansion path in month 9.

## Where I Agree With Leo

- Commercial contracts only for v1. Correct scope.
- Word plugin in v1.5, not v1. Correct sequencing.
- Ground-truth audit as a first-class feature. This is our differentiator; he is right to lead with it.
- M&A in v2. Correct.

## Where We Need To Talk

- The PRD frames "coverage" as a risk and a mitigation. I am saying it is not a risk. It is the product. If coverage is low the product doesn't work.
- The PRD is quiet on what happens to clauses the co-pilot can't redline. "Surface them to the lawyer for review" is the polite answer. The unpolite one is "the lawyer still has to redline them manually," which is exactly the value-extraction problem above.

## Ask

Let's take 30 minutes this Friday (Leo, me, Priya, Jordan, Darren) and decide: is coverage the GA gate or isn't it? I think it has to be.
