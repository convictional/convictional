---
key: msg-rhea-tina-tina-dpa-patterns
model: EmailMessage
thread: !ref thread-rhea-tina
user: !ref rhea
message_type: received
sender: "Tina Werner <tina@corvuslegal.com>"
to:
  - !ref rhea
subject: "DPA redline patterns at Corvus"
received_at: !relative_day {offset: -6, hour: 10, tz: America/New_York}
---
<p>Hi Rhea,</p>

<p>Happy to share what I can. You mentioned you're building out DPA playbook coverage and wanted to understand the patterns Corvus actually encounters in practice. Here's the honest picture:</p>

<p>The three clauses that go to negotiation in literally every DPA we sign:</p>
<ol>
<li><strong>Sub-processor notification windows.</strong> Everyone says 30 days, everyone asks for 10. We never accept anything over 15 anymore.</li>
<li><strong>Data subject request timeframes.</strong> GDPR says one month; US controllers sometimes push for 45-day alignment with CCPA. We standardized on 30 days globally and just hold the line.</li>
<li><strong>Audit rights language.</strong> Vendors always want to limit audits to third-party reports; we always want one direct audit right per 12-month period. This one goes to legal review about 40% of the time.</li>
</ol>

<p>If your playbook handles those three consistently, I think you'd cover probably 70% of what we encounter. The remaining 30% is sector-specific (financial data classifications, insurance regulatory overlays) and harder to generalize.</p>

<p>Good luck with the build. Let me know if you want me to share any of our standard DPA positions — I'd need to clear it with our GC first but it might be useful as ground truth.</p>

<p>Tina Werner<br>
<em>VP Legal Operations, Corvus Legal</em></p>
