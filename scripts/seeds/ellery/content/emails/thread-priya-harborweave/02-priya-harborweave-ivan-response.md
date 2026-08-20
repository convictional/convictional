---
key: msg-priya-harborweave-ivan-response
model: EmailMessage
thread: !ref thread-priya-harborweave
user: !ref priya
message_type: received
sender: "Ivan Ostrowski <ivan@harborweave.com>"
to:
  - !ref priya
subject: "Re: EU region-scoped storage eval — Ellery"
received_at: !relative_day {offset: -5, hour: 15, tz: America/New_York}
in_reply_to: !ref thread-priya-harborweave-msg-priya-harborweave-priya-reach
labels: [inbox]
---
<p>Priya,</p>

<p>I appreciate the directness — let me match it.</p>

<p><strong>Per-tenant vs. per-deployment:</strong> Per-tenant region config is supported and in production for three customers. You define the region preference at tenant creation time; it's enforced at the storage layer and audit-logged. The control plane remains US-based (us-east-1) but all data operations for EU-tagged tenants are routed to the EU fleet and we have a contractual data residency commitment we've had audited.</p>

<p><strong>Key management:</strong> This is the trickier question. Our default is AWS KMS per-tenant CMKs co-located with the data. For EU customers, the CMKs live in eu-west-1. The control plane accesses them via cross-region KMS API calls, which means key requests technically traverse the AWS backbone between regions. Some customers are fine with this (the keys don't move, only the API call). Some are not. If your customer requires that key management is also EU-resident end-to-end, you'd need to run a separate EU control plane instance — we support it but it's a larger implementation scope.</p>

<p><strong>GDPR audit references:</strong> Yes. I can connect you with our infrastructure team lead at one of those customers — they passed a GDPR data mapping audit using our infrastructure last year. Would that be useful?</p>

<p>Ivan Ostrowski<br>
<em>Solutions Engineer, Harborweave</em></p>
