---
key: arjun-keyvault-01-maya-intro
model: EmailMessage
thread: !ref thread-arjun-keyvault
user: !ref arjun
message_type: received
sender: "Maya Jansen <maya.jansen@keyvaultco.com>"
to:
  - !ref arjun
subject: "Re: KMS eval — EU region"
received_at: !relative_day {offset: -4, hour: 10, tz: America/New_York}
---
<p>Arjun,</p>

<p>Thanks for reaching out — this is exactly the kind of use case we built Keyvault for.</p>

<p>A few questions to make sure I spec the right eval environment:</p>

<ol>
  <li>Are you targeting AWS KMS with multi-region keys, or are you looking for a bring-your-own-KMS layer that sits above the cloud provider?</li>
  <li>What's the key rotation requirement — is 90-day rotation enough, or are you under a customer contractual obligation that specifies shorter?</li>
  <li>Do you need HSM backing for the root keys, or is software-backed OK for this stage?</li>
</ol>

<p>For EU data residency specifically: we support eu-west-1 and eu-central-1 with keys that never leave the region. Our envelope-encryption scheme means your application layer doesn't need to change — you swap the KMS endpoint in config and the rest is transparent.</p>

<p>Happy to do a 30-minute technical walkthrough this week if you want to see the key hierarchy before committing to an eval.</p>

<p>Best,<br>
Maya Jansen<br>
<em>Solutions Engineer, Keyvault Co.</em></p>
