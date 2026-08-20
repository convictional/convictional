---
key: msg-rhea-jordan-dm-jordan-agreed
model: EmailMessage
thread: !ref thread-rhea-jordan-dm
user: !ref rhea
message_type: received
sender: !ref jordan
to:
  - !ref rhea
subject: "Re: Ground truth labeling workflow"
received_at: !relative_day {offset: -2, hour: 9, tz: America/New_York}
---
<p>Rhea,</p>

<p>3-label scheme makes sense. I'll update the eval script to accept correct / borderline / wrong and weight borderline at 0.5 for the aggregate score. That'll give Maren a cleaner number for the coverage memo — "borderlines" are worth tracking separately from outright errors.</p>

<p>Agree on holding explanation text. One thing at a time.</p>

<p>I'll send you the updated label template today.</p>

<p>Jordan</p>
