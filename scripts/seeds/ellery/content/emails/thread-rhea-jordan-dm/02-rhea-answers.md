---
key: msg-rhea-jordan-dm-rhea-answers
model: EmailMessage
thread: !ref thread-rhea-jordan-dm
user: !ref rhea
message_type: sent
sender: !ref rhea
to:
  - !ref jordan
subject: "Re: Ground truth labeling workflow"
received_at: !relative_day {offset: -3, hour: 15, tz: America/New_York}
---
<p>Jordan,</p>

<p>Good questions. Honest answers:</p>

<ol>
<li><strong>What "correct" means:</strong> I've been using the higher bar — "a competent in-house lawyer would accept this without revision." Not just semantic equivalence. The model can be semantically aligned and still be subtly wrong for the context (e.g., using a clause designed for SaaS in a professional services context). I should have said this explicitly earlier.</li>
<li><strong>Borderline cases:</strong> No formal partial credit yet. I've been using binary labels and adding a free-text note on the borderline cases, but that note isn't picked up by your eval script. We need a 3-label scheme: correct / borderline / wrong. I can reformat the label sheet.</li>
<li><strong>Explanation text:</strong> Not labeled separately. I've been treating it as context, not as an output to grade. If you think it should be graded independently, I can add a column.</li>
</ol>

<p>I'd vote for: do the 3-label scheme now, hold off on explanation text labeling until we have a prototype version that actually surfaces it to users. No point grading an output that doesn't exist yet.</p>

<p>Rhea</p>
