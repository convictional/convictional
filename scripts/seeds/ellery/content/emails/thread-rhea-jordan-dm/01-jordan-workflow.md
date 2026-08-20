---
key: msg-rhea-jordan-dm-jordan-workflow
model: EmailMessage
thread: !ref thread-rhea-jordan-dm
user: !ref rhea
message_type: received
sender: !ref jordan
to:
  - !ref rhea
subject: "Ground truth labeling workflow"
received_at: !relative_day {offset: -4, hour: 11, tz: America/New_York}
---
<p>Rhea,</p>

<p>I'm refining the eval harness for the co-pilot prototype and need to nail down the labeling workflow before I can run the next benchmark batch. A few questions:</p>

<ol>
<li>When you label a redline as "correct," what are you actually checking — semantic equivalence to the playbook position, or something stronger like "a lawyer would accept this without revision"?</li>
<li>For borderline cases (e.g., the model suggests a clause that's directionally right but missing a carve-out), do you have a "partial credit" label, or is it binary?</li>
<li>Are you labeling the explanation text (the "why we suggest this") separately from the redline itself?</li>
</ol>

<p>The answers affect how I structure the eval scores, so I don't want to assume.</p>

<p>Jordan</p>
