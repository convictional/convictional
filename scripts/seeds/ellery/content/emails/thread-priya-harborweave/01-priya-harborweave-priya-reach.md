---
key: msg-priya-harborweave-priya-reach
model: EmailMessage
thread: !ref thread-priya-harborweave
user: !ref priya
message_type: sent
sender: !ref priya
to:
  - "Ivan Ostrowski <ivan@harborweave.com>"
subject: "EU region-scoped storage eval — Ellery"
sent_at: !relative_day {offset: -6, hour: 10, tz: America/New_York}
---
<p>Ivan,</p>

<p>We spoke at the Infra Summit in February — I mentioned we were looking at EU data residency work for a potential enterprise customer. That work is now active and I'm evaluating infrastructure options.</p>

<p>The scope: we need region-scoped storage and routing for customer contract data, so that documents classified as "EU" stay within eu-west-1 / eu-central-1 and don't cross the Atlantic. This is a contractual requirement, not just a best practice — we need to be able to attest to it in writing.</p>

<p>Key architectural questions I need answers on:</p>
<ol>
<li>Does Harborweave support per-tenant storage region configuration, or is it per-deployment?</li>
<li>How do you handle key management for cross-region customers where the control plane is US-based but data is EU-hosted?</li>
<li>Do you have existing customers in EU who've passed GDPR audits using your infrastructure?</li>
</ol>

<p>I'm not looking for a sales conversation right now — I'm looking for an honest technical eval. If your infrastructure can do this, I want to understand the implementation path and your reference customers. If it can't, I'd rather know now.</p>

<p>Priya<br>
<em>CTO, Ellery</em></p>
