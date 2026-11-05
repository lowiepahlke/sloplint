# sloplint

A linter for copy that sounds like ChatGPT wrote it. English and Dutch.

Paste in a cold email, a LinkedIn post or a landing page and it tells you which lines give it away: "I hope this email finds you well", "it's not just X, it's Y", "Fast. Simple. Effective.", "unlock", "seamless", "[Your Name]". Each finding comes with the line it's on and what to do instead.

It's one Python file with no dependencies and no API calls. It runs in milliseconds, gives the same answer every time, and never sends your text anywhere.

## Try it

```bash
git clone https://github.com/lowiepahlke/sloplint.git
cd sloplint
python sloplint.py examples/slop-email.txt --format email
```

Python 3.7 or newer. Nothing to install.

## What it catches

Here's [examples/slop-email.txt](examples/slop-email.txt), a cold email any model would happily write:

```
Hi Sarah,

I hope this email finds you well! I came across your salon and was truly impressed by your commitment to excellence.

In today's fast-paced digital landscape, it's not just about having a website — it's about creating a seamless experience. Our innovative, cutting-edge solutions empower businesses like yours to unlock new growth and elevate their brand.

Fast. Simple. Effective.

Let me know if you have any questions. I'd be happy to chat!

Best regards,
[Your Name]
```

sloplint's verdict (trimmed, the full run has 24 findings):

```
sloplint: 78 words, 12 sentences, 7 paragraphs, lang=en, format=email
VERDICT: REWRITE  (density 69.23 pts/100w, 8 hard tell(s), 24 finding(s))

[3]      em-dash              1 dash(es) in short copy: use a period, comma or parentheses
[3]   L3 throat-clearing      throat-clearing / faux insight / engagement bait: delete it and start one sentence later  "I hope this email finds you"
[3]   L5 contrast-frame       contrast frame (not just X, but Y): say the second half only  "not just about having a website — it's"
[3]   L9 canned-closer        customer-service sign-off or fake-profound closer: end on the last concrete point instead  "Let me know if you have any questions"
[3]  L12 chatbot-leak         chatbot leakage: this text was pasted from a model, remove the wrapper  "[Your Name]"
[2]   L3 fake-personalization reflected personalization opener readers now filter out: name their problem in one plain sentence instead  "I came across your"
[2]      staccato             three consecutive fragments (Fast. Simple. Done.): merge into one sentence  "Fast. Simple. Effective."
[2]   L5 ai-word              AI vocabulary: replace with the plain word or the specific fact  "seamless"
...
```

And here's [examples/human-email.txt](examples/human-email.txt), the same pitch with an actual observation and a number in it:

```
Hi Sarah,

Your booking page asks for a phone number before it shows open slots. I tried it on my phone last night and gave up at that step, and I bet some of your clients do too.

We moved the slots above the form for a salon in Utrecht in March. Online bookings went from 31 to 52 a month.

Want me to send you a screenshot of how theirs looks now?

Sam
```

```
VERDICT: PASS  (density 0.0 pts/100w, 0 hard tell(s), 0 finding(s))
rhythm: mean 10.6w, sd 7.0, burstiness 0.66 (aim 0.5+), shortest 1w, longest 23w, 0% start with The/This/It
specificity: 80% of longer sentences carry a number, name, quote, date or first-person detail (aim 40%+)
```

There's a Dutch example too: [examples/slop-nl.txt](examples/slop-nl.txt). Language is detected automatically, or force it with `--lang en` / `--lang nl`.

## The checks

| Group | Examples |
|---|---|
| Hard tells | "it's not X, it's Y" and "niet alleen X, maar ook Y", "Here's the thing", "I hope this email finds you well", "Hope this helps", "Aarzel niet", leftover `[Your Name]`, em dashes in short copy |
| Vocabulary | delve, seamless, unlock, elevate, landscape, cruciaal, naadloos, naar een hoger niveau, plus puffery ("a testament to") and weasel sources ("studies show") |
| Structure | "Fast. Simple. Done." fragments, "The result? Chaos.", rule-of-three lists, colon reveals |
| Rhythm | sentence lengths that never vary, runs of same-length sentences, one-line-per-paragraph LinkedIn posts |
| Specificity | how many sentences carry a number, name, date, quote or first-person detail |
| Formatting | bold-stem bullet lists, emoji bullets, hashtags, Title Case headings, mixed curly and straight quotes |
| Length | word limits per format: a reply over 70 words or an email over 180 gets flagged |

Every finding has a severity from 1 to 3. The verdict comes from severity points per 100 words:

| Verdict | When |
|---|---|
| PASS | under 1.5 points per 100 words and no severity-3 finding |
| REVIEW | 1.5 to 4 points, or exactly one severity-3 finding |
| REWRITE | over 4 points, two or more severity-3 findings, or three or more severity-2+ findings in a text under 250 words |

## Options

```
python sloplint.py FILE [--format FORMAT] [--lang auto|en|nl] [--json]
```

- `FILE`: a text or Markdown file, or `-` to read from stdin.
- `--format`: changes length limits and which rules apply. `reply`, `answer` (default), `email`, `dm`, `post`, `x`, `landing`, `ad`, `long`. Lists, semicolons and em dashes are only penalised hard in the short formats.
- `--json`: machine-readable output with every finding, its line and the rhythm stats.

Exit codes are 0 for PASS, 1 for REVIEW and 2 for REWRITE, so you can fail a CI job or a pre-commit hook on copy that needs work:

```bash
python sloplint.py landing/hero.md --format landing || echo "rewrite the hero"
```

From Python:

```python
from sloplint import lint

result = lint(open("draft.txt", encoding="utf-8").read(), fmt="email")
print(result["verdict"], len(result["findings"]))
```

## With an LLM

Have your model write the draft, run sloplint on it, and give the findings back with "fix these and nothing else". Repeat until it passes. Running the check outside the model matters: a model asked to review its own writing tends to approve it.

## What it can't do

It's a smoke alarm, not a judge. It matches patterns, so:

- A PASS doesn't mean the copy is good. Text can be clean and still say nothing. Read it out loud before you send it.
- It will flag some words a human used on purpose. If "robust" is the right word for your bridge, keep it.
- The specificity score counts "I", "we" and "our" as personal detail, so generic text written in first person can score higher than it deserves.
- It only knows English and Dutch. Other languages get the English rules.

The word lists reflect what reads as AI-written in 2024 to 2026. That shifts, so pull requests with new tells (with an example sentence) are welcome.

## License

MIT
