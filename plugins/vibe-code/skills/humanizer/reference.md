# Detection guidance

Read this before acting on detector hits or deciding that a passage needs rewriting. A clean human writer can hit several patterns without any AI involvement, so the job is to find clusters, not to delete every match.

## Reading the detector report

`scripts/detect_slop.py` prints one JSON object with a `documents` list. Each document has:

| Field | Meaning |
| --- | --- |
| `words` | Words in scanned prose (secondhand text excluded) |
| `hits_per_1000_words` | All hits normalized by length; compare drafts of the same text, not different texts |
| `rule_counts` | Hits per pattern ID |
| `clusters` | Paragraphs where at least `--cluster-threshold` distinct rules fired (default 3), keyed by the paragraph's first line |
| `hits` | Every match with pattern ID, name, reference file, line, column, paragraph, and excerpt |

Exit codes: 0 clean or no gate set, 1 when clustered paragraphs exceed `--fail-over N`, 2 when an input can't be read, 3 when python3 is older than 3.12.

How to weigh it:

- A cluster is the signal. Three or more distinct patterns in one paragraph almost always means a rewrite.
- An isolated hit is a question, not a verdict. Check it against the false-positive list below before touching it.
- Repeated hits of one rule (eight P07s, no other rules) usually mean a writer's tic or a domain where the word is literal ("crucial" in a medical note). Look before rewriting.
- Zero hits does not mean human. The detector only covers mechanical patterns; P10, P11, P12, P26 and P29 to P32 need a read, and so does passive voice under P13.
- Never report a percentage or an "AI likelihood". The script doesn't produce one and nothing in this skill supports one.

What the detector skips as secondhand text: frontmatter, fenced code, blockquotes, inline code, link targets, and anything inside straight or curly double quotes. A word that is being discussed rather than used belongs in one of those, which is why the reference files list watched words as inline code.

Deliberately excluded from the rules because they misfire on ordinary prose: `actually`, `key`, `valuable`, `fundamentally`, `features`, curly apostrophes, single triplets (P10), and predicate hyphens (P26).

## What not to flag

These are not reliable indicators on their own:

- **Perfect grammar and consistent style.** Many writers are professionals or have been edited. Polish does not equal AI.
- **Mixed casual and formal registers.** This often signals a person in a technical field, a young writer, or someone with neurodivergent prose habits, not a chatbot.
- **Bland or robotic prose.** AI prose has specific tells. Generic dryness without those tells is just dry writing.
- **Formal or academic vocabulary.** AI overuses specific fancy words (P07), not all fancy words. Don't flatten "ostensibly" or "constituent" just because they sound brainy.
- **Letter-style opening or closing on a comment.** Salutations and sign-offs predate ChatGPT by centuries.
- **Common transition words in isolation.** "Additionally", "moreover" and "consequently" are AI-coded only when piled up. One "however" is not a tell.
- **Curly quotes alone.** macOS, Word, Google Docs, and most CMSes curl quotes by default. They count only when stacked with other tells.
- **Em dashes alone.** Many editors and journalists use them often. They are evidence only when paired with formulaic, salesy rhythm. (The rewrite still removes them unless a voice sample says otherwise; this is about detection, not output.)
- **One short emphatic sentence.** Humans use clipped sentences to land a point. Flag staccato drama only when several short fragments appear in a row and inflate the tone.
- **"Honestly" or "look" mid-sentence.** Ordinary in casual writing. The tell is the standalone theatrical opener.
- **Unsourced claims.** Most of the web is unsourced. Missing citations prove nothing.
- **Correct, complex formatting.** Visual editors and templates produce clean output without any AI.
- **Secondhand text.** Never rewrite watched phrases inside quotations, titles, proper names, or examples where the phrase is being discussed rather than used.

When in doubt, look for clusters. A single em dash means nothing; em dashes plus rule-of-three plus "vibrant tapestry" plus a Conclusion section is a confession.

## Signs of human writing (preserve these)

When you see these, lean toward leaving the prose alone. They are evidence of a real person writing, and over-editing destroys what makes the piece sound human.

- **Specific, unusual, hard-to-fabricate detail.** A real address. A weird quote. "The lawyer who used to work upstairs from my dentist." LLMs round off specifics; humans hoard them.
- **Mixed feelings and unresolved tension.** "I think this is mostly good, but it bothers me, and I can't fully explain why." LLMs default to clean takes.
- **Dated, era-bound references.** Slang, memes, or in-jokes that map to a specific year and subculture. Models lag by a year or more.
- **First-person editorial choices the writer can defend.** If the writer can explain why they made a particular cut or used a particular word, that's a strong human signal.
- **Variety in sentence length.** Real writing alternates short and long. AI writing tends toward an even, mid-length cadence.
- **Genuine asides, parentheticals, or self-corrections.** "(I keep wanting to say 'almost' here, but it really was certain.)" Models rarely interrupt themselves like this.
- **Edits made before November 30, 2022.** ChatGPT's public launch. Anything older is, with very rare exceptions, not AI-written.

## Source

Based on [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), maintained by WikiProject AI Cleanup from observations of thousands of instances of AI-generated text. Its key insight: LLMs use statistical algorithms to guess what should come next, so the result tends toward the most statistically likely result that applies to the widest variety of cases.
