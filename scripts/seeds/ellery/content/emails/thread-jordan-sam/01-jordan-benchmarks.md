---
key: jordan-sam-01-jordan-benchmarks
model: EmailMessage
thread: !ref thread-jordan-sam
user: !ref jordan
message_type: sent
sender: !ref jordan
to:
  - "Dr. Sam Oluwasegun <sam.oluwasegun@berkeley.edu>"
subject: "Re: Eval benchmark ideas"
received_at: !relative_day {offset: -5, hour: 10, tz: America/New_York}
---
<p>Sam,</p>

<p>Really glad you replied to my earlier note. Here's where we are and where I'm stuck:</p>

<p>We're building an eval harness for redline suggestion quality in contract review. The core task is: given a contract clause and a playbook rule, does the model's suggested redline (a) satisfy the rule and (b) preserve the semantic intent of the original clause? We have about 300 labeled examples from Rhea's manual annotations so far — real lawyer-approved redlines with the playbook rule they were responding to.</p>

<p>The issue is that our current eval metric (exact-match on key terms) has almost no signal. Two redlines that mean the same thing in contract law land as very different strings. We're looking at something more semantic — either LLM-as-judge with a well-constructed rubric, or a contrastive approach where we score agreement vs. disagreement on a structured rubric.</p>

<p>Have you seen any published benchmarks for this kind of legal text generation task? Even outside redlining — any NLG eval work on legal documents would help. I'm specifically trying to avoid building something from scratch that has known failure modes we'd only discover six months later.</p>

<p>Jordan</p>
