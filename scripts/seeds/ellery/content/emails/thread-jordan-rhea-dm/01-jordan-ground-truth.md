---
key: jordan-rhea-dm-01-jordan-ground-truth
model: EmailMessage
thread: !ref thread-jordan-rhea-dm
user: !ref jordan
message_type: sent
sender: !ref jordan
to:
  - !ref rhea
subject: "Re: Ground truth for DPA redlines"
received_at: !relative_day {offset: -3, hour: 9, tz: America/New_York}
---
<p>Rhea,</p>

<p>Quick question before I kick off the next eval run: for the DPA annotations you've been doing — are you labeling at the clause level or the sub-clause level? I realized when I was looking at the output yesterday that we have a few examples where the model's redline is correct for the clause as a whole but technically wrong at the sub-clause level (e.g., it rephrases the liability limitation correctly but it also silently moves the notice requirement to a different paragraph).</p>

<p>If you're only reviewing clause-level correctness, that would explain why our eval scores look better than they should on the DPA set. I want to know before I publish the benchmark numbers anywhere.</p>

<p>Also — do you want me to add a column to the annotation interface for "scope of the change" (clause-level vs. structural)? It's a 30-minute change on my end.</p>

<p>Jordan</p>
