---
key: jordan-sam-02-sam-response
model: EmailMessage
thread: !ref thread-jordan-sam
user: !ref jordan
message_type: received
sender: "Dr. Sam Oluwasegun <sam.oluwasegun@berkeley.edu>"
to:
  - !ref jordan
subject: "Re: Eval benchmark ideas"
received_at: !relative_day {offset: -4, hour: 15, tz: America/New_York}
---
<p>Jordan,</p>

<p>Good timing — I've been thinking about this exact problem for a NAACL submission we're working on.</p>

<p>The short answer: don't use exact-match for legal text generation. You know this, but the long answer matters too. The semantic gap in contract language isn't just paraphrase — a redline that moves an indemnification cap from "3x fees paid" to "direct damages not to exceed three times the annual fees" is the same clause, but string similarity is essentially zero.</p>

<p>What I'd recommend looking at:</p>
<ol>
  <li><strong>LLM-as-judge with a structured rubric</strong> — works well when you have 3-5 clear dimensions (e.g., "does this satisfy the playbook rule?", "does this change the economic terms?", "is this standard market language?"). The failure mode is prompt sensitivity; you'll want to calibrate the judge against your human annotations.</li>
  <li><strong>BERTScore with a legal fine-tune</strong> — there are a few legal-domain BERT variants; scores correlate better with human judgment than raw BERTScore for this kind of task.</li>
  <li><strong>Contrastive human evaluation</strong> — A/B between model redlines and human redlines, blind. Expensive but your ground truth for calibrating the automated eval.</li>
</ol>

<p>I'd also look at the ContractNLI paper (Koreeda &amp; Manning, EMNLP 2021) — it's not redlining but the NLI framing over contract clauses is close enough to be useful.</p>

<p>Happy to jump on a call if you want to walk through the rubric design.</p>

<p>Sam<br>
<em>UC Berkeley, NLP Group</em></p>
