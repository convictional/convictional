---
key: msg-maren-rhea-coverage-rhea-numbers
model: EmailMessage
thread: !ref thread-maren-rhea-coverage
user: !ref maren
message_type: received
sender: !ref rhea
to:
  - !ref maren
subject: "Re: Coverage memo — your numbers"
received_at: !relative_day {offset: -4, hour: 17, tz: America/New_York}
in_reply_to: !ref thread-maren-rhea-coverage-msg-maren-rhea-coverage-maren-ask
labels: [inbox]
---
<p>Maren,</p>

<p>Numbers below. I've also flagged the ones I think will land hardest with Darren.</p>

<p><strong>Coverage by contract type (complete = all clause categories flagged with ≥80% confidence):</strong></p>
<ul>
<li>NDA — 78% complete. Strongest playbook we have.</li>
<li>MSA — 61% complete. Decent on limitation of liability and IP ownership, weak on operational SLAs and termination-for-convenience triggers.</li>
<li>SOW — 44% complete. Works for simple fixed-fee SOWs; falls apart on milestone-based or change-order-heavy engagements.</li>
<li>DPA — <strong>29% complete.</strong> This is the gap. Sub-processor change notifications, DSR timelines, and lawful basis clauses all return uncertain or no-opinion at high rates.</li>
<li>IP Assignment — 52% complete. Mostly works for standard employee agreements; weak on contractor/work-for-hire edge cases.</li>
</ul>

<p><strong>DPA confidence distribution (last 500 reviews):</strong></p>
<ul>
<li>High-confidence flag: 31% of clauses</li>
<li>Uncertain / low-confidence: 41% of clauses</li>
<li>No opinion returned: 28% of clauses</li>
</ul>

<p><strong>Top override categories (customer-visible overrides, past 90 days):</strong></p>
<ol>
<li>DPA sub-processor language — 47 overrides (by far the highest)</li>
<li>MSA SLA definitions — 31 overrides</li>
<li>DPA data retention terms — 28 overrides</li>
</ol>

<p>The number Darren will care about: <strong>76% of DPA clauses return uncertain or no-opinion.</strong> That's not a minor gap; that's a playbook that doesn't exist for a contract type our customers are actively running through the platform at increasing volume.</p>

<p>Rhea</p>
