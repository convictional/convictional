---
key: jordan-rhea-dm-02-rhea-response
model: EmailMessage
thread: !ref thread-jordan-rhea-dm
user: !ref jordan
message_type: received
sender: !ref rhea
to:
  - !ref jordan
subject: "Re: Ground truth for DPA redlines"
received_at: !relative_day {offset: -3, hour: 10, tz: America/New_York}
---
<p>Jordan,</p>

<p>Good catch. I've been labeling clause-level — I was following the original annotation guide and it says "assess the redline against the playbook rule for that clause." I didn't think about the structural side effects.</p>

<p>To be honest, the silent paragraph movement thing is a real failure mode in practice. If a lawyer misses that in a live review, that's a meaningful error. I think we need to flag it.</p>

<p>Yes to the annotation interface change — add the "scope of change" column. I'd suggest three values: <em>in-clause</em> (only touches the clause text), <em>cross-reference</em> (adds or modifies a reference to another clause), and <em>structural</em> (moves text between sections). That should cover 95% of cases.</p>

<p>How long would it take to re-annotate the existing DPA examples with the new dimension? I can do it but I want to scope the time before I commit.</p>

<p>Rhea</p>
