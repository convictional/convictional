---
key: response
model: EmailMessage
thread: !ref thread-research-rhea
user: !ref rhea
message_type: received
sender: "Convictional Research <research@convictional.com>"
to:
  - !ref rhea
subject: "[Research] Where are our biggest playbook coverage gaps right now?"
received_at: !relative_day {offset: 0, hour: 9, tz: America/New_York}
---
<h1>[Research] Where are our biggest playbook coverage gaps right now?</h1>
<blockquote><p>Where are our biggest playbook coverage gaps right now?</p></blockquote>
<h2>Summary</h2>
<p>The most significant coverage gap is in Data Processing Agreements (DPAs), where only 54% of clause types have a defined playbook position and only 31% have a customer-preferred alternative. This gap is consequential because DPAs are required by every enterprise customer and are the primary legal blocker on the Keating &amp; Marsh deal.</p>
<h2>Key Findings</h2>
<h3>Coverage memo quantified the gap with current data</h3>
<p>Maren's Coverage-First Memo presented the DPA gap as the strongest argument for prioritizing coverage work over the redline co-pilot feature. The memo cited data provided by Rhea Patel: MSAs at 82% coverage, NDAs at 91%, and DPAs at only 54% — with specific zero-coverage clause types including LGPD, PIPL, cross-border transfer mechanisms beyond SCCs, and breach notification to third-party regulators. Rhea commented on the post confirming these as the thinnest areas and noting that PIPL is the hardest to address given limited authoritative ground truth.<sup><a href="seed:posts/post-coverage-memo">1</a></sup></p>
<h3>Coverage-First walk-through meeting surfaced the business stakes</h3>
<p>The Coverage-First Memo Walk-Through meeting confirmed that the DPA coverage gap is not just a quality metric — it is blocking the Keating deal. Amira Saleh's three DPA questions (sub-processors, data retention on termination, EU data residency) map directly to clause types where Ellery's playbook has incomplete or missing positions. The meeting ended with Darren asking the research question that redirected focus to Emma's sessions.<sup><a href="seed:meetings/mtg-soc2-readiness-review">2</a></sup></p>
<h3>Keating deal made coverage gaps urgent</h3>
<p>The Keating goal documents that SOC 2 and EU data residency are the technical blockers, but the DPA coverage gap is the legal blocker. Amira Saleh's detailed DPA questions in the maren-amira-legal email thread require coverage positions that do not currently exist in the playbook — particularly the EU sub-processor notification requirements and the data retention certification on termination.<sup><a href="seed:goals/keating">3</a></sup></p>
<h3>External validation confirms DPA complexity</h3>
<p>Tina Werner at Corvus Legal (an existing customer) confirmed that DPA audit rights and sub-processor notification windows are the two clauses that go to negotiation in every enterprise DPA. The absence of customer-preferred alternatives in these clause types means the current playbook cannot support a lawyer trying to advocate for their organization's standard position.<sup><a href="seed:email_threads/thread-rhea-tina">4</a></sup></p>
<hr>
<p><em>Convictional can make mistakes. Please verify any critical information independently.</em></p>
<p>You can provide feedback for this research by forwarding this email to decide@convictional.com with your comments</p>
<h3>References</h3>
<ol>
<li><a href="seed:posts/post-coverage-memo">Coverage-First Memo</a> — Post by Maren Kovacs</li>
<li><a href="seed:meetings/mtg-soc2-readiness-review">SOC 2 Readiness Review</a> — Meeting</li>
<li><a href="seed:goals/keating">Keating</a> — Goal</li>
<li><a href="seed:email_threads/thread-rhea-tina">DPA redline patterns at Corvus</a> — Email thread with Tina Werner (Corvus Legal)</li>
</ol>
