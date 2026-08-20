---
key: msg-maren-amira-legal-maren-response
model: EmailMessage
thread: !ref thread-maren-amira-legal
user: !ref maren
message_type: sent
sender: !ref maren
to:
  - "Amira Saleh <amira.saleh@keatingmarsh.com>"
subject: "Re: DPA scoping for the pilot agreement"
sent_at: !relative_day {offset: -3, hour: 14, tz: America/New_York}
in_reply_to: !ref thread-maren-amira-legal-msg-maren-amira-legal-amira-initial
---
<p>Amira,</p>

<p>These are exactly the right questions to work through now. Let me take them in order.</p>

<p><strong>1. Sub-processors.</strong> We maintain a registry — I'll attach it to this message. Current list is 11 processors (AWS, OpenAI, Pinecone, and 8 others). Country-of-processing is documented for each. We update the list with 30-day advance notice to customers, which is standard under GDPR Art. 28(2) and should work for your template. If your DPA requires direct-notification opt-out rights, we can accommodate that — we've done it for two other customers.</p>

<p><strong>2. Data retention.</strong> 30-day deletion with written certification is workable. We don't retain any customer matter data post-termination — our analytics are computed on anonymized, aggregated signals derived at ingestion time and don't require retaining the underlying documents. The cert language we'd propose: we delete customer content within 30 days of term and certify in writing within 45 days. I can redline your standard language when we're at that stage.</p>

<p><strong>3. EU data residency.</strong> This is the real question. Priya's team has a region-scoped architecture spike in progress right now — I'm not going to over-promise on a timeline we haven't fully closed, but our current working target is staging-ready within three weeks. What I can commit to contractually today is a data processing commitment with an EU-residency milestone obligation: if we don't hit the milestone by a specified date, you have a fee-abatement right. That's the structure two other enterprise customers have accepted when they needed the contractual commitment before the capability was live.</p>

<p>Does any of that give you what you need to brief Doug? Happy to jump on a 30-minute call this week — I can bring our CTO if the residency architecture is something Doug's team wants to hear directly.</p>

<p>Maren<br>
<em>Cofounder &amp; Head of Legal Product<br>
Ellery</em></p>
