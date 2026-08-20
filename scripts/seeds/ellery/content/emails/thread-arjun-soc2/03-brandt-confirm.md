---
key: arjun-soc2-03-brandt-confirm
model: EmailMessage
thread: !ref thread-arjun-soc2
user: !ref arjun
message_type: received
sender: "Brandt Soh <brandt.soh@haldenrossi.com>"
to:
  - !ref arjun
  - !ref priya
subject: "Re: Evidence collection for CC6"
received_at: !relative_day {offset: -3, hour: 16, tz: America/New_York}
---
<p>Arjun,</p>

<p>The timestamped admin console export is fine for the terminated user reviews — just make sure it shows both the account disable date and the date of the offboarding event so we can show same-week remediation.</p>

<p>On EU residency: if you have the data-flow diagram by next Thursday I can include it as a supplemental scope item. The key thing I need to describe in the criteria is where EU customer data at rest vs. in transit lives, and that the encryption key management is region-isolated. If the staging deployment is still two weeks out, a design document plus the key management architecture decision is enough for Type I.</p>

<p>Thursday works for everything else. I'll send a secure upload link this afternoon.</p>

<p>Thanks,<br>
Brandt<br>
<em>Halden &amp; Rossi</em></p>
