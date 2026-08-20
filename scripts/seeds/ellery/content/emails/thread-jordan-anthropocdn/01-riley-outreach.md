---
key: jordan-anthropocdn-01-riley-outreach
model: EmailMessage
thread: !ref thread-jordan-anthropocdn
user: !ref jordan
message_type: received
sender: "Riley Maddox <riley@anthropocdn.co>"
to:
  - !ref jordan
subject: "Re: Inference pricing at scale"
received_at: !relative_day {offset: -6, hour: 10, tz: America/New_York}
---
<p>Jordan,</p>

<p>Thanks for reaching back out. To answer the question you had from our last exchange: yes, we support EU-region inference routing. Our eu-west-1 and eu-central-1 inference endpoints are GA, and we can configure model routing such that EU-tagged requests never leave the EU network boundary — relevant for your GDPR / data-residency requirements.</p>

<p>On pricing at scale: we do tiered volume pricing starting at 10M tokens/month. Given what you described about the redline co-pilot use case (document-length contexts, batch and interactive modes), the biggest variable in your cost model will be whether you run batch eval jobs at off-peak or always-on. I can model out both scenarios if you share rough token estimates.</p>

<p>Are you on a timeline for the pilot decision? I want to make sure you have what you need before you're forced to lock in a model provider on short notice.</p>

<p>Riley Maddox<br>
<em>Account Executive, Anthropocdn</em><br>
riley@anthropocdn.co</p>
