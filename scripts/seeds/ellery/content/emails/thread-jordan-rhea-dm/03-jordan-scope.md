---
key: jordan-rhea-dm-03-jordan-scope
model: EmailMessage
thread: !ref thread-jordan-rhea-dm
user: !ref jordan
message_type: sent
sender: !ref jordan
to:
  - !ref rhea
subject: "Re: Ground truth for DPA redlines"
received_at: !relative_day {offset: -2, hour: 9, tz: America/New_York}
---
<p>Rhea,</p>

<p>Love the three-value schema — that exactly matches what I was thinking. I'll push the annotation interface change today.</p>

<p>For re-annotation: the DPA set is 89 examples right now. Given the label is a new column (not changing any existing labels), I'd estimate 45-60 minutes of your time if you batch it. But it doesn't need to block the next eval run — I can hold the DPA results separately until we have the new dimension in, and publish the full-harness numbers with a note about the ongoing work.</p>

<p>One more thing: I want to add two "adversarial" DPA examples where the model changes the governing law clause without a playbook rule that requires it. Those would be structural-negative examples. Can you write those two? Just a synthetic contract snippet plus a playbook rule that does <em>not</em> address governing law, and the correct annotation would be that any governing law change is out of scope.</p>

<p>Jordan</p>
