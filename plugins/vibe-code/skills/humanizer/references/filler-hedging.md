# Filler and hedging (P23 to P26)

Padding that adds words without adding claims. P26 is a style-guide rule more than an AI tell and has no detector rule.

## P23. Filler phrases

Detector: phrases only.

| Before | After |
| --- | --- |
| "In order to achieve this goal" | "To achieve this" |
| "Due to the fact that it was raining" | "Because it was raining" |
| "At this point in time" | "Now" |
| "In the event that you need help" | "If you need help" |
| "The system has the ability to process" | "The system can process" |
| "It is important to note that the data shows" | "The data shows" |

## P24. Excessive hedging

Detector: stacked hedges only ("could potentially", "might possibly", "it could be argued"). A single "may" is honest uncertainty, not a tell.

Before:

> It could potentially possibly be argued that the policy might have some effect on outcomes.

After:

> The policy may affect outcomes.

## P25. Generic positive conclusions

Detector: phrases only.

Vague upbeat endings.

Before:

> The future looks bright for the company. Exciting times lie ahead as they continue their journey toward excellence. This represents a major step in the right direction.

After: cut the paragraph. End on the last concrete fact instead of a send-off. If the source states real plans, use those.

## P26. Hyphenated word pair overuse

Detector: no. The attributive/predicate distinction is standard style-guide advice, and a script flagging it would hit most edited prose.

Words to watch: `third-party`, `cross-functional`, `client-facing`, `data-driven`, `decision-making`, `well-known`, `high-quality`, `real-time`, `long-term`, `end-to-end`

AI hyphenates these uniformly, including in predicate position ("the report is high-quality"). Humans hyphenate inconsistently, typically only when the compound is attributive ("a high-quality report") and often dropping the hyphen otherwise ("the report is high quality"). Keep attributive hyphens; drop them when the compound follows the noun.

Before:

> The cross-functional team delivered a high-quality, data-driven report. The team is cross-functional, the report is high-quality, and the methodology is data-driven.

After:

> The cross-functional team delivered a high-quality, data-driven report. The team is cross functional, the report is high quality, and the methodology is data driven.
