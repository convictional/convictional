---
key: doc-eng-hiring-plan
model: Document
title: "Engineering Hiring Plan"
creator: !ref priya
sharing: organization
---

# Engineering Hiring Plan

Three hires in Q3: SRE, ML Engineer, Integrations Engineer. This doc covers the bar, ordering rationale, and loop shape for each.

## Ordering Rationale

SRE first because we are six weeks away from Keating's pilot environment needing real on-call coverage and scaled ingestion. Nobody on the team today owns production reliability as a first responsibility. Arjun has been paging himself at 2am and that is not a plan.

ML second because Jordan is the only person who touches evals, retrieval tuning, and the fine-tune pipeline. When Jordan takes PTO — which he will, because he is entitled to it — the redline quality curve stops moving. We need redundancy and we need someone who can own the eval harness full-time.

Integrations third because it is the most deal-shaped hire. The Keating deal assumes iManage and Okta integrations. Future enterprise deals will assume NetDocuments, SharePoint, and at least two more SSO providers. Arjun has been prototyping these but cannot own them long-term.

## The Bar

Staff-level engineers. Minimum five years production experience, at least two of those in an environment with real scale (10k+ req/sec, multi-region, 99.9%+ SLO). We are not hiring people who have only built prototypes.

For SRE specifically: must have incident commander experience, must have designed and run postmortem processes, must be fluent in Postgres tuning. Bonus: Kubernetes operator experience.

For ML: must have shipped an LLM eval harness in production. Must have strong opinions about retrieval metrics. Must have fine-tuned an open model end-to-end at least once.

For Integrations: must have built SSO and SCIM before. Must understand enterprise document management systems. Bonus: has integrated with iManage or NetDocuments specifically.

## Loop Shape

1. Phone screen with recruiter (30 min)
2. Technical screen with me or Jordan (60 min)
3. On-site: four 45-minute rooms
   - System design (Arjun)
   - Deep technical (me or Jordan)
   - Collaboration / past-work (Theo or me)
   - Founder fit (Darren or Maren)
4. Debrief same day. Decision within 48 hours.

No take-home exercises. We respect candidates' time.

## Sourcing

Watershed Partners has the CoS search. For engineering, we are going direct — me and Jordan working our networks plus inbound from the Series A announcement. If pipeline thins in two weeks, we engage an engineering-specific recruiter.
