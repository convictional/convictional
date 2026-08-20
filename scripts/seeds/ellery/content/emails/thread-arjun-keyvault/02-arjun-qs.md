---
key: arjun-keyvault-02-arjun-qs
model: EmailMessage
thread: !ref thread-arjun-keyvault
user: !ref arjun
message_type: sent
sender: !ref arjun
to:
  - "Maya Jansen <maya.jansen@keyvaultco.com>"
subject: "Re: KMS eval — EU region"
received_at: !relative_day {offset: -4, hour: 15, tz: America/New_York}
---
<p>Maya,</p>

<p>Answers:</p>

<p><strong>1.</strong> We're on AWS. Ideally I'd stay on AWS KMS with multi-region keys rather than adding another vendor, but I'm open to the BYOK layer if the pricing model makes sense at our current scale (~50k encrypted documents, growing fast post-raise).</p>

<p><strong>2.</strong> Our customer contract doesn't specify rotation interval yet — we're setting the standard. 90-day rotation is fine for now; the main constraint is that eu-west/eu-central keys must be isolated from us-east keys, not shared in a multi-region key set where the primary is in the US.</p>

<p><strong>3.</strong> Software-backed is fine for Type I SOC 2. If Keating & Marsh needs HSM for their security questionnaire, we'll revisit, but I don't want to over-engineer the first iteration.</p>

<p>Yes to the 30-minute walkthrough — Thursday afternoon or Friday morning works on my end.</p>

<p>Arjun</p>
