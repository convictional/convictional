---
key: msg-priya-arjun-residency-priya-note
model: EmailMessage
thread: !ref thread-priya-arjun-residency
user: !ref priya
message_type: sent
sender: !ref priya
to:
  - !ref arjun
subject: "Region-scoped storage — follow-up from the ADR"
sent_at: !relative_day {offset: -2, hour: 9, tz: America/New_York}
---
<p>Arjun,</p>

<p>Following up on Tuesday's ADR review. A few items I want to make sure we're aligned on before you proceed with implementation:</p>

<ol>
<li><strong>Routing layer.</strong> The ADR approves region-scoped storage and the EU fleet topology, but the routing decision — where we classify a document as EU vs. US — is still underspecified. My read is that we should classify at the tenant level, not the document level, to keep the implementation tractable. If a tenant has any EU-domiciled entity, all their data goes to the EU fleet. Can you confirm that's what you're building, and flag it if you think document-level classification is necessary for any customer we know of?</li>
<li><strong>Key management.</strong> I spoke with Harborweave this week and their model uses cross-region KMS API calls for the control plane. I think that's acceptable, but I want to confirm with Maren and outside counsel before we commit. Can you hold off on the key management implementation until I give the green light, probably early next week?</li>
<li><strong>Timeline.</strong> Maren committed a staging-ready environment to Keating in three weeks. Is that still realistic given these two open questions?</li>
</ol>

<p>Priya</p>
