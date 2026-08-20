---
key: arjun-keyvault-03-maya-confirm
model: EmailMessage
thread: !ref thread-arjun-keyvault
user: !ref arjun
message_type: received
sender: "Maya Jansen <maya.jansen@keyvaultco.com>"
to:
  - !ref arjun
subject: "Re: KMS eval — EU region"
received_at: !relative_day {offset: -4, hour: 17, tz: America/New_York}
---
<p>Arjun,</p>

<p>That makes sense — staying on native AWS KMS is the right call at your scale. The multi-region key setup with primary in eu-west-1 and no US replica is totally doable. The isolation guarantee is that AWS KMS never replicates key material to a region you haven't explicitly enabled, so as long as you don't add us-east-1 as a replica region, you're clean.</p>

<p>The thing to watch: if you have any Lambda functions or ECS tasks in us-east-1 that touch encrypted contract data, they'll need to call the eu-west-1 KMS endpoint directly. That's a routing change, not a key change — but it does mean your IAM policy needs cross-region KMS calls whitelisted. I'll walk through this in the demo.</p>

<p>Let's do <strong>Thursday at 3pm ET</strong>. I'll send a calendar invite this afternoon.</p>

<p>Maya<br>
<em>Keyvault Co.</em></p>
