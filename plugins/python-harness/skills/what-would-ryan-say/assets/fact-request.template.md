<task>
Gather facts about cluster {{CLUSTER_ID}} for a Python code review. Report what the code does, with a citation for every fact. Do not judge, rate, recommend or summarize quality; the reviewer who sent this decides what the facts mean.
</task>

<files>
Project root: {{absolute path of the reviewed project's root}}. Every path below, and every path you cite, is relative to it.

Cluster modules (read every line of each):
{{- path (N lines), one per cluster module}}

Tests that import these modules (read the parts that touch them):
{{- path, one per test, or "none"}}

Callers outside the review surface (read only the parts that use this cluster's names):
{{- path, one per dependent, or "none"}}
</files>

<questions>
Answer every question. When the code has nothing for a question, write the line `None found.` under its heading instead of a table.

M1 Mechanical facts. Call `collect_python_facts` with `paths` set to the cluster modules, `detail: full` and `budget: 20000`; read the document under `result`, and on `degraded: true` halve the `paths` list and call again. Give one row per fact it returns: cite the fact's `path:line`, quote that line, and state the fact's `kind`, `symbol` and detail fields as returned. For the kinds `comment` and `docstring`, give at most three rows per module and state that module's count for the kind.
M2 References. Call `map_python_calls` with `paths` set to the cluster modules, `detail: full` and `budget: 20000`; read the document under `result`, and on `degraded: true` halve the `paths` list and call again. Give one row per module, citing its first non-blank line, with `fan_in`, `fan_out`, `instability`, `public_symbols`, `function_count`, `max_function_statements`, `max_parameters` and `test_paths` as returned. Then give one row per name under `unreferenced`, citing the line that defines it.
Q1 State. Which fields, attributes and parameters are booleans, optionals, or strings later compared against literal values? Cite each declaration and every place a value, or a combination of values, is checked, assumed or set.
Q2 Ordering. Which operations must happen before others for the code to work (a method that must be called first, a flag that must be set)? Cite where the requirement is enforced or assumed, and each caller sequence that meets or skips it.
Q3 Resources. What is opened, acquired or started (files, connections, locks, sessions, subprocesses, tasks)? Cite where, where it is released, and whether release happens on every path.
Q4 Configuration. Which literal limits, sizes, timeouts, paths, names and environment reads appear? Cite every occurrence of each value, including repeats in other listed files.
Q5 Failure paths. For each public function, what happens on failure: what is raised, returned, caught, translated (with or without `from`) or swallowed?
Q6 Dependencies. What does each class or function construct internally (clients, clocks, stores, settings) instead of receiving it as an argument?
Q7 Tests. Which tests exercise each public function? Which tests patch, mock or import non-public names, and what do they assert? Does arrangement happen in fixtures or in the test body?
Q8 Callers. How do the listed callers use this cluster's public names: arguments passed, call order, anything done before or after each call?
Q9 Repetition. Which logic, checks or data transformations appear in more than one place? Cite every copy.
Q10 Boundaries. Where do untyped shapes (dicts, tuples, raw strings, `Any`) cross a function or module boundary, and where is input parsed or validated?
{{Wave 2 only: replace M1, M2 and Q1 to Q10 with the targeted questions, numbered T1, T2, ...}}
</questions>

<output_format>
For each question, a heading with its id (`## M1`, `## Q1`) and one table:

| Citation | Quote | Fact |
| --- | --- | --- |
| src/pkg/module.py:42 | `exact text copied from that line` | One neutral sentence about what the code does. |

One citation per row, as `path.py:line` or `path.py:start-end` relative to the project root, in the first column. The quote is copied character for character from the first cited line. Every table row needs a citation; a question with nothing to report gets `None found.` instead of a table. If the tool for M1 or M2 fails, write `Tool failed: <tool>: <the error text>` under that heading instead of a table. Nothing outside the headings, tables, `None found.` lines and `Tool failed:` lines.
</output_format>
