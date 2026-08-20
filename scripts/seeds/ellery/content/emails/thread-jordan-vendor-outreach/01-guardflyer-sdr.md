---
key: jordan-vendor-outreach-01-guardflyer-sdr
model: EmailMessage
thread: !ref thread-jordan-vendor-outreach
user: !ref jordan
message_type: received
sender: "Jenna Liu <jenna@guardflyer.co>"
to:
  - !ref jordan
subject: "LLM guardrails — 15-minute demo?"
received_at: !relative_day {offset: -6, hour: 10, tz: America/New_York}
---
<p>Hi Jordan,</p>

<p>I'm Jenna from Guardflyer. We build LLM guardrails for production AI applications — content filtering, hallucination detection, PII redaction, and output validation.</p>

<p>I noticed Ellery is doing legal-domain AI work. Legal applications tend to have two specific guardrail needs that come up a lot: (1) making sure the model doesn't confidently assert something that contradicts the contract being reviewed, and (2) preventing PII or confidential clause language from ending up in logs or training data.</p>

<p>We have a 15-minute demo that shows how to add our guardrails as a middleware layer — no retraining required, works with any inference provider.</p>

<p>Worth 15 minutes?</p>

<p>Jenna Liu<br>
<em>SDR, Guardflyer</em><br>
jenna@guardflyer.co</p>
