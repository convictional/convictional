---
key: doc-residency-adr
model: Document
title: "Architecture Decision — EU Data Residency (Region-Scoped Storage)"
creator: !ref arjun
sharing: organization
---

# ADR: EU Data Residency via Region-Scoped Storage

- **Status:** Accepted
- **Date:** This week
- **Owner:** Arjun
- **Reviewers:** Priya, Jordan, Darren

## Context

Keating & Marsh has offices and clients in the EU. Their CISO (Darius Haddad) has required that EU-origin matter data remain in EU-region storage and that our data processing be addressable under GDPR Article 28 terms. Without this, the deal is blocked at security review.

We currently run a single-region deployment in `us-central1`. All contract documents, retrieval indices, and LLM invocations happen in US infrastructure. This will not pass Darius's review.

We also expect similar requirements from at least three other pipeline accounts in Europe within the next six months.

## Options Considered

### Option A — Full multi-region active-active
Replicate every service across US and EU regions. Customer lands in whichever region their tenant is provisioned in. All services fully symmetric.

- Pros: strongest isolation, lowest latency for EU customers, best narrative.
- Cons: ~12 weeks of engineering work, significant cost uplift, every future feature must be built region-aware.

### Option B — Region-scoped storage, shared compute
Provision an EU-region Postgres instance, EU-region object storage bucket, and EU-region retrieval index per EU tenant. LLM calls route to EU-hosted inference endpoints. Keep non-tenant services (admin console, billing, analytics) in US-only.

- Pros: shippable in 4-6 weeks, passes the specific compliance requirement, scales to one-EU-tenant or many.
- Cons: compute is still global; requires careful tenant-aware routing; not every LLM provider supports EU hosting today.

### Option C — EU-hosted deployment for Keating only
Stand up a dedicated single-tenant Ellery instance in the EU for Keating.

- Pros: maximum isolation, simplest compliance story.
- Cons: operationally we'd be running a snowflake. Every bugfix deployed twice. Not sustainable past 2-3 EU customers.

## Decision

**Option B — Region-scoped storage, shared compute.**

It is the only option that is both shippable in the Keating deal window and doesn't create a snowflake deployment we have to babysit forever.

## Consequences

### Positive
- Unblocks Keating and the EU pipeline
- Creates a sustainable pattern for EU compliance going forward
- Lets us charge an EU-residency premium that covers the real costs

### Negative
- Shared compute means LLM invocations see EU-origin contract data, briefly, in US inference. We will disclose this in our DPA.
- Tenant-aware routing adds a layer of complexity that every backend engineer needs to be fluent with.
- Our retrieval index will need to be sharded per region, which increases operational surface area.

### Implementation plan (high-level)

1. Provision EU Postgres + object storage (week 1)
2. Add tenant-region flag to the organization model; thread through all storage writes (weeks 1-2)
3. EU-hosted LLM endpoint integration (week 3)
4. Region-aware retrieval indexing (weeks 3-4)
5. End-to-end test with a Keating-like test tenant (week 5)

Arjun owns execution. Priya owns review.
