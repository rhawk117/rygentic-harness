# Content patterns (P01 to P06)

Patterns in what the text claims rather than how it phrases it. The detector catches the stock phrases; deciding whether a claim is puffery still needs a read of the sentence.

## P01. Significance, legacy, and broader trends

Detector: phrases only.

Words to watch: `stands/serves as`, `is a testament/reminder`, `a vital/significant/crucial/pivotal/key role/moment`, `underscores/highlights its importance/significance`, `reflects broader`, `symbolizing its ongoing/enduring/lasting`, `contributing to the`, `setting the stage for`, `marking/shaping the`, `represents/marks a shift`, `key turning point`, `evolving landscape`, `focal point`, `indelible mark`, `deeply rooted`

LLM writing puffs up importance by adding statements about how arbitrary aspects represent or contribute to a broader topic.

Before:

> The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. This initiative was part of a broader movement across Spain to decentralize administrative functions and enhance regional governance.

After:

> The Statistical Institute of Catalonia was established in 1989, part of a wider decentralization of administrative functions in Spain.

## P02. Notability and media coverage

Detector: phrases only.

Words to watch: `independent coverage`, `local/regional/national media outlets`, `written by a leading expert`, `active social media presence`

LLMs hit readers over the head with claims of notability, often listing sources without context.

Before:

> Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence with over 500,000 followers.

After:

> Her views have been cited in The New York Times and the BBC.

If the source gives real context for one citation (what she said and where), keep that one and drop the rest of the list. Don't invent the context to make the trimmed version sound better.

## P03. Superficial analyses with -ing endings

Detector: yes, when the participle follows a comma.

Words to watch: `highlighting/underscoring/emphasizing...`, `ensuring...`, `reflecting/symbolizing...`, `contributing to...`, `cultivating/fostering...`, `encompassing...`, `showcasing...`

Chatbots tack present participle phrases onto sentences to add fake depth.

Before:

> The temple's color palette of blue, green, and gold resonates with the region's natural beauty, symbolizing Texas bluebonnets, the Gulf of Mexico, and the diverse Texan landscapes, reflecting the community's deep connection to the land.

After:

> The temple is painted blue, green, and gold, colors meant to evoke Texas bluebonnets and the Gulf of Mexico.

## P04. Promotional and advertisement-like language

Detector: phrases only.

Words to watch: `boasts a`, `vibrant`, `rich` (figurative), `profound`, `enhancing its`, `showcasing`, `exemplifies`, `commitment to`, `natural beauty`, `nestled`, `in the heart of`, `groundbreaking` (figurative), `renowned`, `breathtaking`, `must-visit`, `stunning`

LLMs have serious problems keeping a neutral tone, especially for cultural heritage topics.

Before:

> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and stunning natural beauty.

After:

> Alamata Raya Kobo is a town in the Gonder region of Ethiopia.

## P05. Vague attributions and weasel words

Detector: phrases only.

Words to watch: `Industry reports`, `Observers have cited`, `Experts argue`, `Some critics argue`, `several sources/publications` (when few are cited)

Chatbots attribute opinions to vague authorities without specific sources.

Before:

> Due to its unique characteristics, the Haolai River is of interest to researchers and conservationists. Experts believe it plays a crucial role in the regional ecosystem.

After:

> Researchers and conservationists study the Haolai River for its unusual characteristics.

If a real source exists, name it. Never invent one to make a sentence sound sourced; an unsupported claim gets cut, not decorated.

## P06. Outline-like challenges and outlook sections

Detector: phrases only.

Words to watch: `Despite its... faces several challenges...`, `Despite these challenges`, `Challenges and Legacy`, `Future Outlook`

Many LLM-generated articles include a formulaic challenges section that ends on resilience.

Before:

> Despite its industrial prosperity, Korattur faces challenges typical of urban areas, including traffic congestion and water scarcity. Despite these challenges, with its strategic location and ongoing initiatives, Korattur continues to thrive as an integral part of Chennai's growth.

After:

> Korattur has recurring traffic congestion and water shortages.

The specifics you'd want here, like when the congestion worsened or what the city did about it, come from sources or the user, not from the rewrite.
