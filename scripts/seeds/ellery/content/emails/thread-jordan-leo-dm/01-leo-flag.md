---
key: jordan-leo-dm-01-leo-flag
model: EmailMessage
thread: !ref thread-jordan-leo-dm
user: !ref jordan
message_type: received
sender: !ref leo
to:
  - !ref jordan
subject: "Re: Prototype flag for Pam's team"
received_at: !relative_day {offset: -4, hour: 14, tz: America/New_York}
---
<p>Jordan,</p>

<p>Quick ask: can you flip the prototype flag on for Pam Watts's team at Ipso Wakely? She's confirmed as a design partner and Emma has the research session scheduled for Thursday. Pam specifically wants to try the redline suggestions on a real NDA before the session, not just a demo contract.</p>

<p>Two questions before you enable it:</p>
<ol>
  <li>Is there any rate limiting in place, or could they accidentally hammer the inference endpoint?</li>
  <li>Is the disclaimer ("AI-suggested — review before accepting") showing up correctly in the UI? Emma mentioned one of the sessions had the disclaimer missing and she flagged it as a usability concern.</li>
</ol>

<p>Leo</p>
