# Writing a candidate description

The CLI accepts your rewrite only if it improves the validation score, which comes from requests you never see. A rewrite that memorizes the training examples will be rejected; one that states the skill's job and boundaries more clearly will generalize.

## What to change

- **Missed requests** mean the description does not name the situations the skill exists for. Generalize from the requests to the intent behind them and name that intent in the user's vocabulary. If three missed requests all ask about backlog grooming, say the skill handles backlog and sprint work; pasting the requests in will not survive validation.
- **False triggers** mean the description claims ground that belongs elsewhere, or uses words that appear in unrelated requests. Narrow the claim, or state the boundary in plain words: what the skill is not for, and which neighboring skill is.
- **Collisions** list pairs of descriptions that share distinctive vocabulary. Make this skill's description distinctive on the axis that separates the two jobs, not just different words.
- **Rejected rewrites** have already failed on validation. Variants of them will fail too; change approach.
- **`when_to_use`** in the packet is joined to the description in the skill listing and stays as it is. Write the description so the two read as one entry, without repeating its trigger phrases.

## Shape

- Lead with what the skill does, then when to use it, including phrasings a user would actually type.
- Keep it to a few sentences and under the packet's `max_chars`. Together with `when_to_use` it must stay within the 1,536-character listing limit, or the CLI refuses it. Angle brackets are refused too.
- Change one skill at a time; the packet names which.

Reply with JSON only:

```json
{"description": "Your rewritten description."}
```
