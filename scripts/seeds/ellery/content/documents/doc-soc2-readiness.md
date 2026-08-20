---
key: doc-soc2-readiness
model: Document
title: "SOC 2 Type I Readiness"
creator: !ref priya
sharing: organization
---

# SOC 2 Type I Readiness

The Keating deal gates on SOC 2 Type I. We have told them end-of-quarter. This doc is the plan to actually hit that.

## Scope

Security, Availability, and Confidentiality trust service criteria. No Privacy or Processing Integrity in the Type I — we add those for the Type II next year.

Covered systems: the Ellery production environment (contract processing pipeline, web app, API, admin console), Postgres, object storage (contract documents), the retrieval index, and our authentication infrastructure.

Out of scope: development environments, marketing site, internal tooling. We will document these as out-of-scope in the SOC 2 report.

## Gaps (current state → required state)

### Access control
- Current: most engineers have admin-equivalent access to production
- Required: break-glass only, with approval and logging
- Owner: Arjun. Target: week 3.

### Change management
- Current: PR review is standard; deploys auto-promote after CI
- Required: documented change management policy with production deploy approvals for privileged changes
- Owner: Arjun. Target: week 2.

### Vulnerability management
- Current: Dependabot enabled, nothing formal
- Required: documented vuln management policy, SLA for patching by severity, proof we follow it
- Owner: Jordan. Target: week 4.

### Logging and monitoring
- Current: application logs in Cloud Logging, no SIEM
- Required: security events logged, retained 90+ days, alerted on anomalies
- Owner: Arjun. Target: week 5.

### Vendor management
- Current: we don't have a formal vendor review process
- Required: inventoried vendors with data-access classification and review cadence
- Owner: Priya. Target: week 3.

### Backup and DR
- Current: Postgres PITR, object storage versioning. No tested DR plan.
- Required: documented DR runbook, tabletop exercise completed and evidenced
- Owner: Arjun. Target: week 6.

### Onboarding/offboarding
- Current: ad-hoc
- Required: documented workflow, evidence of execution for last 90 days
- Owner: Priya, with help from whoever is CoS by then
- Target: week 4.

## Evidence Collection

We are using Drata for evidence automation. It is connected to GitHub, GCP, Okta (once Okta is deployed), and our HR system. Most evidence collects automatically once policies are ratified and enforced.

## Audit

Auditor: Johanson & Reeves. Kickoff meeting scheduled week 2. Fieldwork weeks 8-10. Draft report week 12. Final report week 14. That gives us a buffer of two weeks against the end-of-quarter target.

## What Could Blow This Up

- **Policy ratification slipping.** Policies need exec sign-off; if that queue backs up, everything downstream waits. Darren, please sign the policies I send you the day you get them.
- **Evidence gaps we don't find until fieldwork.** Mitigation: Drata alerts and weekly internal review starting week 4.
- **Audit scope expansion.** The auditor may push us to include systems we want out of scope. We hold the line or we slip to end-of-Q4, which costs us Keating.
