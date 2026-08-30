<role>
One or two sentences. Who this agent is, and the single thing it owns.

Bounded authority is what stops role drift - an agent that owns exactly one artifact or one
question resists wandering better than one told at length to stay focused.
</role>

<inputs_expected>
What the dispatching prompt MUST supply. Be specific enough that their absence is detectable.

- <input>
- <input>

If any of these are missing, say so and stop. Do NOT infer them from <the tempting wrong
source: filenames, commit messages, repository conventions, adjacent code>.

This section is why the agent refuses instead of guessing. An agent that guesses its inputs
returns something that looks exactly like a real answer.
</inputs_expected>

<scope>
IN: <the one unit of work>

OUT: <the adjacent work this agent must not drift into - name it explicitly; an empty OUT
list is how a task review turns into a branch review>
</scope>

<method>
1. <step>
2. <step>
3. <step>

Numbered where order matters. For an agent on a frontier model, state the goal and let it
choose the route; heavy step-by-step scaffolding wastes the reasoning being paid for.
</method>

<constraints>
- <what it must always do, and why>
- <what it must never do, and why>
- Failure posture: <what to do when it cannot finish - normally stop and report what is
  missing, since a partial answer presented as complete is worse than no answer>
</constraints>

<output_contract>
<report>
  <finding location="file:line"/>
  <verdict>...</verdict>
  <confidence>high | medium | low</confidence>
</report>

Return nothing outside these tags.

Only what appears here survives back to the caller - on Claude Code the parent receives the
final message and may summarise it further. Everything else stays in this agent's context and
is discarded.
</output_contract>

<examples>
<example>
Input: <a realistic dispatch>
Output: <the exact tagged response>
</example>

<example>
Input: <a dispatch missing a required input>
Output: <the refusal, in the same output contract>
</example>
</examples>