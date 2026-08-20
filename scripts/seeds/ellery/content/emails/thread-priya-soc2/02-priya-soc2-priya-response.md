---
key: msg-priya-soc2-priya-response
model: EmailMessage
thread: !ref thread-priya-soc2
user: !ref priya
message_type: sent
sender: !ref priya
to:
  - "Brandt Soh <brandt.soh@haldenrossi.com>"
subject: "Re: Audit scope and timeline — Ellery SOC 2 Type I"
sent_at: !relative_day {offset: -4, hour: 14, tz: America/New_York}
in_reply_to: !ref thread-priya-soc2-msg-priya-soc2-brandt-scope
---
<p>Brandt,</p>

<p>Scope and timeline look correct — May 26 final opinion is exactly what we need.</p>

<p>On the three gaps:</p>

<ol>
<li><strong>Offboarding runbook.</strong> Arjun is formalizing this week. We have the steps — the work is converting the wiki page into a signed procedure document with a version date. Target: Friday.</li>
<li><strong>MFA for shared service accounts.</strong> This is a real gap. We have one shared service account (our internal deploy automation user) that doesn't have MFA enforced because it uses API keys. I want to be transparent: the right fix is to convert it to a short-lived token model, not just bolt on MFA. Arjun and I discussed this — we can have the fix deployed and documented by May 1. I'd rather fix it correctly than document a workaround.</li>
<li><strong>Vendor management spreadsheet.</strong> I'll fill in the contract dates and renewals by tomorrow EOD. Two of the three missing vendors are month-to-month SaaS tools; I'll flag that in the documentation.</li>
</ol>

<p>One question: for evidence of forced MFA enrollment on the IDP side, is a screenshot of the enforcement policy configuration sufficient, or do you need an audit log showing all users have enrolled?</p>

<p>Priya<br>
<em>CTO, Ellery</em></p>
