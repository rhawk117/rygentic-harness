# Style patterns (P14 to P19)

Typography and Markdown habits. All six have detector rules, and all six are weak alone: see the false-positive list in reference.md before acting on a single hit.

## P14. Em dashes and en dashes: cut them

Detector: yes (em dash, en dash, and a spaced double hyphen).

The final rewrite contains no em dashes (U+2014) or en dashes (U+2013). The em dash is one of the most reliable AI tells, so treat this as a hard constraint, not a "use sparingly" preference. Replace each one, in rough order of preference: a period (start a new sentence), a comma (a tight aside), a colon (introducing an explanation), parentheses (a true aside), or restructure the sentence. Also catch spaced em dashes and double hyphens used the same way.

Before:

> The term is primarily promoted by Dutch institutions—not by the people themselves. You don't say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official documents.

After:

> The term is primarily promoted by Dutch institutions, not by the people themselves. You don't say "Netherlands, Europe" as an address, yet this mislabeling continues in official documents.

Before:

> The new policy — announced without warning — affects thousands of workers. The changes -- long overdue according to critics -- will take effect immediately.

After:

> The new policy, announced without warning, affects thousands of workers. The changes, long overdue according to critics, will take effect immediately.

The one exception: a user-provided writing sample that uses em dashes overrides this rule (see Voice calibration in SKILL.md). Match the sample's frequency instead of banning them.

## P15. Overuse of boldface

Detector: yes (three or more bold spans on one line).

Chatbots bold phrases mechanically.

Before:

> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and visual strategy tools such as the **Business Model Canvas (BMC)** and **Balanced Scorecard (BSC)**.

After:

> It blends OKRs, KPIs, and visual strategy tools like the Business Model Canvas and Balanced Scorecard.

## P16. Inline-header vertical lists

Detector: yes.

List items that open with a bolded header and a colon, each restating the header in the sentence that follows.

Before:

> - **User Experience:** The user experience has been significantly improved with a new interface.
> - **Performance:** Performance has been enhanced through optimized algorithms.
> - **Security:** Security has been strengthened with end-to-end encryption.

After:

> The update improves the interface, speeds up load times through optimized algorithms, and adds end-to-end encryption.

## P17. Title case in headings

Detector: yes (a capitalized minor word mid-heading, or four or more capitalized words in a row).

Chatbots capitalize every main word in a heading. Proper nouns and product names are exempt; a hit on a heading like "Google Cloud Run Jobs" is a false positive.

Before:

> Strategic Negotiations And Global Partnerships

After:

> Strategic negotiations and global partnerships

## P18. Emojis

Detector: yes.

Chatbots decorate headings and bullet points with emojis.

Before:

> 🚀 **Launch Phase:** The product launches in Q3
> 💡 **Key Insight:** Users prefer simplicity
> ✅ **Next Steps:** Schedule follow-up meeting

After:

> The product launches in Q3. User research showed a preference for simplicity. Next step: schedule a follow-up meeting.

## P19. Curly quotation marks

Detector: yes (curly double quotes only; curly apostrophes are too common to count).

ChatGPT emits curly quotes where the surrounding text uses straight ones.

Before:

> He said “the project is on track” but others disagreed.

After:

> He said "the project is on track" but others disagreed.
