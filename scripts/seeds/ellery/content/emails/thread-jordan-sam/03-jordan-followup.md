---
key: jordan-sam-03-jordan-followup
model: EmailMessage
thread: !ref thread-jordan-sam
user: !ref jordan
message_type: sent
sender: !ref jordan
to:
  - "Dr. Sam Oluwasegun <sam.oluwasegun@berkeley.edu>"
subject: "Re: Eval benchmark ideas"
received_at: !relative_day {offset: -4, hour: 17, tz: America/New_York}
---
<p>Sam,</p>

<p>This is incredibly helpful. The ContractNLI reference is exactly what I needed — I had seen the dataset but hadn't made the connection to how we'd use the NLI framing as an intermediate eval step before the full generation quality score.</p>

<p>I'm going to try option 1 first (LLM-as-judge with structured rubric) — we have about 300 human-labeled examples from our legal content analyst which should be enough to calibrate the judge before I commit to it. If the correlation with human judgment is below 0.7 I'll revisit.</p>

<p>Would love a call. Let me find a time and send something your way — maybe next week after we have a first run of the new eval? I'd be curious whether the rubric dimensions I land on match what you've seen in your research.</p>

<p>Jordan</p>
