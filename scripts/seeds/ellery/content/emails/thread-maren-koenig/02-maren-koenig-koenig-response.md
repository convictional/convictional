---
key: msg-maren-koenig-koenig-response
model: EmailMessage
thread: !ref thread-maren-koenig
user: !ref maren
message_type: received
sender: "Professor Ira Koenig <ikoenig@columbialaw.edu>"
to:
  - !ref maren
subject: "Re: AI-assisted redline — an ethics question"
received_at: !relative_day {offset: -6, hour: 11, tz: America/New_York}
in_reply_to: !ref thread-maren-koenig-msg-maren-koenig-maren-question
labels: [inbox]
---
<p>Maren,</p>

<p>You've identified something real, and I think the fact that you're asking it is a good sign.</p>

<p>The standard of care argument is less settled than it probably should be. The current professional responsibility framework — competence under Rule 1.1, supervision under Rules 5.1/5.3 — doesn't contemplate AI assistants specifically, but the ABA's 2023 formal opinion on generative AI (Opinion 512) says a lawyer may use AI so long as they maintain "independent professional judgment." The key word is "independent."</p>

<p>Your cognitive framing concern is real and it's been documented in the decision-making literature. There's a concept called <em>automation bias</em> — the tendency to over-rely on automated suggestions, particularly under time pressure. A junior associate seeing a confident AI-generated redline doesn't just accept or reject it; they're doing something harder to model: updating their own thinking in the presence of a confident prior. If the AI is usually right, the rational response to a suggestion is to accept it more quickly — which is also, precisely, when the AI's error modes are most dangerous.</p>

<p>My honest take: the ethical risk isn't in the feature itself. It's in the product design. A feature that makes it <em>harder</em> to bypass or override suggestions, or that presents confidence scores without surfacing the basis for that confidence, creates the malpractice exposure you're worried about. A feature that requires the lawyer to articulate <em>why</em> they're accepting a suggestion — or that presents competing positions rather than a single recommendation — replicates the supervision-and-judgment loop that Rule 5.1 is trying to protect.</p>

<p>You might find this paper useful: Calo &amp; Rosenblat (2017) on algorithmic decision-making and the cognitive mechanisms of automation bias. Not legal-tech specific, but the underlying mechanism is the same.</p>

<p>Happy to talk through this more if you want a sounding board at a later stage.</p>

<p>Ira</p>
