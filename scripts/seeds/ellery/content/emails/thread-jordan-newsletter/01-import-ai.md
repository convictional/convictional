---
key: jordan-newsletter-01-import-ai
model: EmailMessage
thread: !ref thread-jordan-newsletter
user: !ref jordan
message_type: received
sender: "Import AI <weekly@importai.co>"
to:
  - !ref jordan
subject: "Import AI #401"
received_at: !relative_day {offset: -2, hour: 8, tz: America/New_York}
---
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,sans-serif;">
<tr><td style="background-color:#0f0f23;padding:20px 24px;">
<span style="color:#00d4ff;font-size:18px;font-weight:bold;">Import AI</span>
<span style="color:#7070a0;font-size:13px;display:block;margin-top:4px;">Issue #401 — Your weekly ML research digest</span>
</td></tr>
<tr><td style="padding:24px;color:#1d1d1d;font-size:14px;">

<p>Welcome back. This week: structured prediction for legal documents, alignment tax at inference time, and three papers on LLM evals that you should probably read before your next eval run.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<h2 style="font-family:Georgia,serif;font-size:17px;color:#0f0f23;">LLM-as-Judge: The Alignment Tax Is Real</h2>
<p>New paper from DeepMind shows that when you use a frontier LLM as an evaluation judge, the judge systematically prefers outputs that sound confident and fluent over outputs that are factually accurate — a finding that has obvious implications for anyone using LLM judges on professional-text generation tasks. The key takeaway: calibrate your judge against human annotators on at least 100 examples before trusting its scores.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<h2 style="font-family:Georgia,serif;font-size:17px;color:#0f0f23;">Structured Prediction on Legal Documents</h2>
<p>Three separate papers this week tackle structured extraction from contracts — specifically how to get models to emit structured JSON rather than freeform text for clause-type classification. Consensus finding: fine-tuning on domain-specific clause types beats prompting a larger model for this task, and the performance gap increases as you get to rarer clause types (e.g., specialty indemnification carve-outs).</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<h2 style="font-family:Georgia,serif;font-size:17px;color:#0f0f23;">This Week in Evals</h2>
<p>A useful summary post: BERTScore, BARTScore, and G-Eval compared across 9 generation tasks. G-Eval (LLM-as-judge with chain-of-thought) consistently outperforms the others on tasks where human judgment is about coherence and task-completion, not factual accuracy. For legal text, the factual accuracy dimension matters more than in most tasks — use G-Eval as one of several signals, not the only one.</p>

<hr style="border:none;border-top:1px solid #e1e4e8;margin:20px 0;">

<p style="font-size:12px;color:#888888;">Import AI &bull; <a href="#" style="color:#888888;">Unsubscribe</a> &bull; <a href="#" style="color:#888888;">View archive</a></p>
</td></tr>
</table>
