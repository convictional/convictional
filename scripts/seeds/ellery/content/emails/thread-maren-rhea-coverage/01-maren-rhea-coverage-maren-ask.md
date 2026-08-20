---
key: msg-maren-rhea-coverage-maren-ask
model: EmailMessage
thread: !ref thread-maren-rhea-coverage
user: !ref maren
message_type: sent
sender: !ref maren
to:
  - !ref rhea
subject: "Coverage memo — your numbers"
sent_at: !relative_day {offset: -5, hour: 9, tz: America/New_York}
---
<p>Rhea,</p>

<p>I'm writing the coverage memo today and I need the quantitative layer before I circulate it. Can you pull the following for me by end of day?</p>

<ol>
<li>Current playbook coverage by contract type — MSA, NDA, DPA, SOW, IP assignment, employment (not exhaustive, just what we have live). For each: how many clause categories does the playbook cover vs. how many we'd define as "complete" coverage?</li>
<li>Confidence distribution on the last 500 DPA reviews we ran for customers — what percentage of clauses got a high-confidence flag vs. returned uncertain or no-opinion?</li>
<li>Which clause categories generate the most customer override events? I want to show that coverage gaps aren't hypothetical — they're visible in override data.</li>
</ol>

<p>If you have a sense of which data points will be most compelling to Darren specifically, flag that. He responds to things that are measurable and actionable.</p>

<p>Maren</p>
