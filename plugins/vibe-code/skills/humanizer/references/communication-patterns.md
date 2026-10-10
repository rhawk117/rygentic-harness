# Communication and rhetoric patterns (P20 to P22, P27 to P33)

Chatbot correspondence that leaks into content, plus the rhetorical moves models use to sound authoritative or dramatic. P29 to P32 need a reader.

## P20. Collaborative communication artifacts

Detector: phrases only.

Words to watch: `I hope this helps`, `Of course!`, `Certainly!`, `You're absolutely right!`, `Would you like...`, `Want me to...?`, `Should I continue?`, `let me know`, `here is a...`

Text meant as chatbot correspondence gets pasted as content.

Before:

> Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand on any section.

After:

> The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest.

## P21. Knowledge-cutoff disclaimers and speculative gap-filling

Detector: phrases only.

Words to watch: `as of [date]`, `Up to my last training update`, `While specific details are limited/scarce...`, `based on available information`, `not publicly available`, `maintains a low profile`, `keeps personal details private`, `prefers to stay out of the spotlight`, `likely [grew up/studied/began]`, `it is believed that`

Two related tells. Older models leave hard knowledge-cutoff disclaimers in the text. And when a model can't find a source, it writes a paragraph about not finding one, then invents plausible filler to cover the gap. For a private person the guess almost always lands on the same stock phrases ("maintains a low profile", "keeps personal details private"), none of it sourced. Say what isn't known, or cut the sentence; don't dress a guess up as fact.

Before (cutoff disclaimer):

> While specific details about the company's founding are not extensively documented in readily available sources, it appears to have been established sometime in the 1990s.

After:

> The company's founding date is not documented in the available sources.

Or cut the sentence. State a date only if a source provides one.

Before (speculative gap-fill):

> Information about her early life is not publicly available, suggesting she maintains a low profile and keeps personal details private. She likely grew up in a middle-class household, which shaped her later interest in education reform.

After:

> Her early life is not documented in the available sources.

Or omit the section.

## P22. Sycophantic or servile tone

Detector: phrases only.

Overly positive, people-pleasing language.

Before:

> Great question! You're absolutely right that this is a complex topic. That's an excellent point about the economic factors.

After:

> The economic factors you mentioned are relevant here.

## P27. Persuasive authority tropes

Detector: phrases only (`fundamentally` is excluded as too common).

Phrases to watch: `The real question is`, `at its core`, `in reality`, `what really matters`, `fundamentally`, `the deeper issue`, `the heart of the matter`

LLMs use these phrases to pretend they are cutting through noise to some deeper truth, when the sentence that follows usually restates an ordinary point with extra ceremony.

Before:

> The real question is whether teams can adapt. At its core, what really matters is organizational readiness.

After:

> The question is whether teams can adapt. That mostly depends on whether the organization is ready to change its habits.

## P28. Signposting and announcements

Detector: phrases only.

Phrases to watch: `Let's dive in`, `let's explore`, `let's break this down`, `here's what you need to know`, `now let's look at`, `without further ado`

LLMs announce what they are about to do instead of doing it. The meta-commentary slows the writing down and gives it a tutorial-script feel.

Before:

> Let's dive into how caching works in Next.js. Here's what you need to know.

After:

> Next.js caches data at multiple layers, including request memoization, the data cache, and the router cache.

## P29. Fragmented headers

Detector: no.

A heading followed by a one-line paragraph that restates the heading before the real content begins. It is a rhetorical warm-up that adds nothing.

Before:

> ## Performance
>
> Speed matters.
>
> When users hit a slow page, they leave.

After:

> ## Performance
>
> When users hit a slow page, they leave.

## P30. Diff-anchored writing

Detector: no.

Documentation or comments written as if narrating a change rather than describing the thing as it is. Unless the document is inherently version-scoped (changelogs, release notes, migration guides), it should read coherently without knowing what changed in the last commit.

Before:

> This function was added to replace the previous approach of iterating through all items, which caused O(n²) performance.

After:

> This function uses a hash map for O(1) lookups, avoiding the O(n²) cost of naive iteration.

## P31. Manufactured punchlines and staccato drama

Detector: no.

LLMs make every sentence land like a quotable closer, then stack short declarative fragments to manufacture drama. A single short sentence for emphasis is fine; a run of them sounds engineered.

Before:

> Then AlphaEvolve arrived. It had no preference for symmetry. No aesthetic prior. No nostalgia for human taste. The old rules were gone.

After:

> AlphaEvolve changed the search because it did not favor symmetry or human-looking designs. That made some of the older assumptions less useful.

## P32. Aphorism formulas

Detector: no.

Words to watch: `X is the Y of Z`, `X becomes a trap`, `X is not a tool but a mirror`, `the language of`, `the currency of`, `the architecture of`

LLMs turn ordinary claims into reusable aphorisms that sound profound without adding precision. Replace the formula with the concrete claim it gestures at.

Before:

> Symmetry is the language of trust. Efficiency becomes a trap when teams forget the human layer.

After:

> Symmetric layouts often feel more predictable to users. Teams can over-optimize workflows and miss how people actually use them.

## P33. Conversational rhetorical openers

Detector: yes, at sentence start only.

Phrases to watch: `Honestly?`, `Look,`, `Here's the thing`, `The thing is`, `Let's be honest`, `Real talk`, when used as standalone hooks or fake-candid pauses before an ordinary point.

The tell is the theatrical pause-and-reveal: a one-word question or aside, then the "real" answer. A person being honest usually just says the thing.

Before:

> Is it worth the price? Honestly? It depends on how often you'll use it.

After:

> Whether it's worth the price depends on how often you'll use it.
