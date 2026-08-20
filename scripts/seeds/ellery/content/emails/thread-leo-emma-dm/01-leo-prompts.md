---
key: msg-leo-research-prompts
model: EmailMessage
thread: !ref thread-leo-emma-dm
user: !ref leo
message_type: sent
sender: !ref leo
to:
  - !ref emma
subject: "Research prompts — v2"
sent_at: !relative_day {offset: -5, hour: 22, tz: America/New_York}
---
<p>Emma,</p>

<p>Revised version of the research prompts based on what came up in the design review. Three additions:</p>

<ol>
<li>I want to specifically probe how reviewers handle <em>conflicting signals</em> — when the co-pilot suggestion contradicts a prior manual edit. That's the failure mode I'm most worried about for design partners.</li>
<li>Add a scenario where the playbook hasn't been updated for six months. Does the reviewer trust the suggestion more or less than a fresh playbook? That's the trust degradation question we haven't answered.</li>
<li>At the end of every session: "If this tool saved you one hour per review, would you use it?" I know it's leading, but I want the baseline number for the roadmap argument.</li>
</ol>

<p>I know prompt 3 is borderline leading — if you want to reframe it, go ahead. You're the researcher. Just capturing my intent.</p>

<p>Leo</p>
